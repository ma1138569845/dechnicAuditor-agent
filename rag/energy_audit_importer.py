#!/usr/bin/env python3
"""
Energy audit report multi-level importer.
Extract PDF -> three-tier chunks (summary/chapter/paragraph) -> Qwen embedding -> Qdrant.
"""
import os, re, sys, uuid
from collections import OrderedDict
from typing import Optional
import pymupdf

from pathlib import Path

from rag.config import qdrant_client_kwargs, reports_collection

COLLECTION = reports_collection()
BATCH_SIZE = 10

# ── 分类规则（共享模块） ──
from tools.energy_audit.institution_classifier import classify_institution


# ── 章节提取 ──
CHAPTER_PATTERN = re.compile(r"第(\d+(?:\.\d+)?)\s*章\s*(.*)")
SECTION_PATTERN = re.compile(r"(\d+\.\d+)\s+(.+)")


# 封面取名：单位名的"可信尾巴"。
# ★2026-09-20 补：原白名单只有 医院/中心/局/学校/大学/学院/委/馆，
#   缺「厅/部/办/处/所」→「山东省科学技术厅」被漏掉，反而抓到人员表里的
#   「…科技服务中心…」（含"中心"）。这是 DOCX 入库时实测出来的。
UNIT_NAME_TAIL_RE = re.compile(
    r"(?:医院|中心|学校|大学|学院|局|厅|部|办|处|所|站|馆|宫|园|社|院|公司|集团|委员会)$"
)
# 目录行尾巴：点线/制表符/多个空格 + 页码。DOCX 的目录是「章名<TAB>页码」（无点线），
# 只认 `...` 会把整份目录当正文章节标题（实测省厅那批 17 个"章节"里 8 个是目录行）。
TOC_TAIL_RE = re.compile(r"(?:[\t.．·…\u2026]{1,}|\s{2,})\d{1,3}\s*$")


# 审计类型启发式（2026-09-21）：原先 `build_chunks` 把 audit_type 写死成"公共机构"，
# 于是工业企业/公共建筑报告在**按审计类型过滤的向量检索**里会被漏掉（实测 21 份里
# 永锋纺织被标成公共机构）。报告入库时文件是**平铺**进 kb 根的，路径带不出类型，
# 只能从文件名判；因此这里**取保守策略**：只在高置信词命中时才改判，其余回退
# "公共机构"。要根治得让入库保留相对子目录（目录名即类型）或加显式参数。
_AUDIT_TYPE_HINTS = (
    ("工业企业", ("工业", "公司", "厂", "纺织", "钢铁", "化工", "水泥",
                "造纸", "矿业", "制造", "冶炼")),
    ("公共建筑", ("公共建筑",)),
)


def infer_audit_type_from_name(filename: str) -> str:
    """按文件名判审计类型；判不出回退"公共机构"（历史默认）。"""
    name = filename or ""
    for audit_type, hints in _AUDIT_TYPE_HINTS:
        if any(h in name for h in hints):
            return audit_type
    return "公共机构"


def _iter_document_pages(path: str) -> list:
    """把文档切成"页文本"列表。

    ★2026-09-20 新增 DOCX 支持：报告库管道原先只吃 PDF（`pymupdf.open`），
    而本地成稿目录里有 10 份是 .docx（省厅那批 / 济南大学 / 省法院），
    直接入会失败。这里对 .docx 用 python-docx 按**文档顺序**抽段落与表格，
    再按约 2400 字合成"伪页"——只为让下面"前两页取单位名、前 5 页取目录"
    这两条启发式仍成立，不改动任何按行处理的逻辑。

    PDF 分支与改动前完全等价（同一句 `page.get_text()`）。
    """
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        doc = pymupdf.open(path)
        try:
            return [doc[i].get_text() for i in range(doc.page_count)]
        finally:
            doc.close()
    if suffix == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = Document(path)
        blocks = []
        for child in document.element.body.iterchildren():
            tag = str(getattr(child, "tag", ""))
            if tag.endswith("}p"):
                blocks.append(Paragraph(child, document).text)
            elif tag.endswith("}tbl"):
                table = Table(child, document)
                for row in table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        blocks.append("\t".join(cells))
        pages, current = [], ""
        for block in blocks:
            current = f"{current}\n{block}" if current else block
            if len(current) >= 2400:
                pages.append(current)
                current = ""
        if current:
            pages.append(current)
        return pages
    raise ValueError(f"extract_pdf_structure 不支持的文件类型：{suffix}（支持 .pdf / .docx）")


def extract_pdf_structure(pdf_path: str) -> dict:
    """
    提取报告的结构化信息（**支持 .pdf 与 .docx**，函数名沿用历史叫法）:
    Returns: {
        "filename": str,
        "file_path": str,
        "file_type": str,
        "unit_name": str, "auditor": str,
        "full_text": str,
        "toc": [(ch_num, ch_title, page), ...],
        "chapters": [(ch_num, ch_title, text), ...],
        "standards": [str, ...],
    }
    """
    pages = _iter_document_pages(pdf_path)
    filename = os.path.basename(pdf_path)
    full_pages = []

    unit_name = ""
    auditor = ""
    toc_items = []  # (ch_num, ch_title, page)
    chapter_texts = OrderedDict()
    standards = []
    current_chapter = "前言"
    current_chapter_text = []

    # 提取所有文本
    for i, text in enumerate(pages):
        full_pages.append(text)

        # 提取单位名称（前两页）
        if i <= 1 and not unit_name:
            for line in text.split("\n"):
                line = line.strip()
                # 表格行（含制表符）不是单位名：人员的「组长 科技服务中心 …」
                # 和表头「机构名称 山东省市场监督管理局」都是从这儿误抓的
                if not line or "\t" in line:
                    continue
                cand = re.sub(r"能源审计报告\s*$", "", line).strip()
                if not cand or "能源审计报告" in cand or "同方德诚" in cand \
                        or "机构信息" in cand or "审计机构" in cand:
                    continue
                if len(cand) < 4 or len(cand) > 30:
                    continue
                # 按"可信尾巴"判：单位名以 厅/局/医院/学校… 结尾
                if UNIT_NAME_TAIL_RE.search(cand):
                    unit_name = cand
                    break

        # 提取审计机构
        if not auditor and "同方德诚" in text:
            auditor = "同方德诚（山东）科技股份公司"

        # 提取目录
        if i <= 5:  # 目录在前几页
            for line in text.split("\n"):
                match = CHAPTER_PATTERN.search(line)
                if match and not line.strip().startswith("第1 章"):
                    ch_num = match.group(1)
                    # 去掉页码、点号和多余空白
                    ch_title_raw = line[line.index("章")+1:].strip()
                    ch_title = re.sub(r"(?:[\t.．·…\u2026]{1,}|\s{2,})\d*\s*$", "",
                                      ch_title_raw).strip()
                    if ch_title:
                        if not any(t[0] == ch_num and t[1] == ch_title for t in toc_items):
                            toc_items.append((ch_num, ch_title, None))

        # 提取标准引用
        std_matches = re.findall(r"[（(]([A-Z]+(?:/\w+)*\s+\d+[.\d]*-?\d*)[）)]", text)
        for s in std_matches:
            if s not in standards and len(s) > 3:
                standards.append(s)

        # 章节分割 - 检测正文中的章节标题
        lines = text.split("\n")
        for j, line in enumerate(lines):
            line_clean = line.strip()
            # 正文中的章节标题：以"第X 章"或"第X章"开头
            # 排除目录中的长行（带页码点号），排除正文中碰巧以"第X"开头的长句
            ch_match = CHAPTER_PATTERN.match(line_clean)
            if ch_match:
                ch_title_tail = ch_match.group(2).strip()
                has_dots = "..." in line_clean or "…" in line_clean
                # 目录行判据：点线（PDF）或 制表符/多空格 + 页码（DOCX 的表格化目录）
                is_toc_line = bool(TOC_TAIL_RE.search(line_clean)) or \
                    (has_dots and len(line_clean) > 20)
                is_short = len(line_clean) < 40
                if is_toc_line:
                    continue        # 目录行既不进正文、也不当章节起点
                # 必须是短行（章节标题行）
                if not is_short:
                    if current_chapter and line_clean:
                        current_chapter_text.append(line_clean)
                    continue
                # 保存上一章
                if current_chapter_text:
                    chapter_texts[current_chapter] = "\n".join(current_chapter_text)
                # 构建章节名
                ch_num = ch_match.group(1)
                if ch_title_tail:
                    current_chapter = f"第{ch_num}章 {ch_title_tail}"
                else:
                    # 只有"第X 章"无标题文字，尝试从下一行获取标题
                    next_line = lines[j+1].strip() if j+1 < len(lines) else ""
                    # 如果下一行不是空行且不含"第"和"章"，当作章节标题
                    if next_line and "第" not in next_line and "章" not in next_line \
                            and len(next_line) < 50 and not next_line.startswith("同方"):
                        current_chapter = f"第{ch_num}章 {next_line}"
                    else:
                        current_chapter = f"第{ch_num}章"
                current_chapter_text = [line_clean]

            if current_chapter and line_clean:
                current_chapter_text.append(line_clean)

    # 保存最后一章
    if current_chapter_text:
        chapter_texts[current_chapter] = "\n".join(current_chapter_text)

    # 去重合并：同编号的"第X章"（无标题）和"第X章 XXXX"（有标题）合并
    merged = OrderedDict()
    short_chapters = {}  # ch_num -> text
    for ch_title, ch_text in chapter_texts.items():
        m = CHAPTER_PATTERN.match(ch_title)
        if m:
            ch_num = m.group(1)
            ch_tail = m.group(2).strip()
            if not ch_tail:
                # 无标题的短章节，暂存
                short_chapters[ch_num] = ch_text
                continue
        merged[ch_title] = ch_text
    # 把短章节内容追加到对应完整章节
    for ch_num, short_text in short_chapters.items():
        found = False
        for ch_title in merged:
            if ch_title.startswith(f"第{ch_num}章 ") and CHAPTER_PATTERN.match(ch_title).group(2).strip():
                merged[ch_title] = merged[ch_title] + "\n" + short_text
                found = True
                break
        if not found:
            merged[f"第{ch_num}章"] = short_text

    chapter_texts = merged

    # 合并全文本（去掉页眉 "同方德诚"）
    full_text = "\n".join(full_pages)
    full_text = re.sub(r"同方德诚[（(]山东[）)]科技股份公司\s*", "", full_text)

    return {
        "filename": filename,
        "file_path": pdf_path,
        "file_type": Path(filename).suffix.lower().lstrip("."),
        "unit_name": unit_name,
        "auditor": auditor,
        "full_text": full_text,
        "toc": toc_items,
        "chapters": list(chapter_texts.items()),
        "standards": standards,
    }


# ── 构建三层 chunks ──
# ═══════════════════════════════════════════════════════════════
# WeKnora-style protected patterns — prevent splitting inside
# formulas, tables, code blocks, images, and links.
# ═══════════════════════════════════════════════════════════════

_PROTECTED_PATTERNS = {
    "formula_block": re.compile(r'\$\$[^$]+\$\$', re.DOTALL),       # LaTeX display math
    "formula_inline": re.compile(r'\$[^$\n]+\$'),                     # LaTeX inline math
    "code_block": re.compile(r'```[^`]*```', re.DOTALL),              # fenced code
    "markdown_table": re.compile(r'^\|.+\|[\s\S]*?\n\s*\n', re.MULTILINE),  # MD tables
    "markdown_image": re.compile(r'!\[[^\]]*\]\([^)]+\)'),           # images
    "markdown_link": re.compile(r'\[[^\]]+\]\([^)]+\)'),              # links
}

_CHUNK_TYPE_PATTERNS = {
    "formula": re.compile(r'\$\$|\$[^$\n]+\$|\\begin\{|\\frac|\\sum|\\int', re.IGNORECASE),
    "table": re.compile(r'^\|[-|]+\|$|[─-╿]{3,}', re.MULTILINE),  # markdown + unicode table borders
    "code": re.compile(r'```|def |function |class |import |package |#include', re.IGNORECASE),
    "data_grid": re.compile(r'(^\s*[\d.,%]+\s+){3,}', re.MULTILINE),  # dense numeric data
    "standard_ref": re.compile(r'GB\s*\d+|GB/T\s*\d+|ISO\s*\d+|DL\s*\d+', re.IGNORECASE),
}

def _detect_chunk_type(text: str) -> str:
    """Detect primary content type of a text chunk."""
    scores = {}
    for ctype, pattern in _CHUNK_TYPE_PATTERNS.items():
        matches = pattern.findall(text)
        scores[ctype] = len(matches)
    if not scores or max(scores.values()) == 0:
        return "text"
    return max(scores, key=scores.get)


def _protect_text(text: str) -> tuple[str, dict]:
    """Replace protected blocks with placeholder markers so splitting never cuts through them.
    Returns (masked_text, placeholder_map)."""
    placeholders = {}
    counter = [0]
    masked = text

    for pattern_name, pattern in _PROTECTED_PATTERNS.items():
        def _replacer(m, pname=pattern_name, cnt=counter):
            key = f"__PROTECTED_{pname}_{cnt[0]}__"
            cnt[0] += 1
            placeholders[key] = m.group(0)
            return f"\n{key}\n"
        masked = pattern.sub(_replacer, masked)

    return masked, placeholders


def _restore_text(masked: str, placeholders: dict) -> str:
    """Restore protected blocks from placeholders."""
    restored = masked
    for key, value in placeholders.items():
        restored = restored.replace(key, value)
    return restored


def _smart_split(text: str, max_chars: int = 800) -> list[str]:
    """Split text into chunks, respecting protected blocks and natural boundaries.
    Splits at paragraph breaks (double newlines), then sentence breaks within oversized paragraphs."""
    # Protect special content first
    masked, placeholders = _protect_text(text)

    # Split paragraphs at double newline (natural boundary)
    paragraphs = [p.strip() for p in masked.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= max_chars:
            current = current + "\n\n" + para
        else:
            if current:
                chunks.append(_restore_text(current, placeholders))
            # If single paragraph is too long, split at sentence boundaries
            if len(para) > max_chars:
                sentences = re.split(r'(?<=[。！？.!?])\s*', para)
                current = ""
                for sent in sentences:
                    if not sent.strip():
                        continue
                    if len(current) + len(sent) <= max_chars:
                        current = (current + sent).strip() if current else sent
                    else:
                        if current:
                            chunks.append(_restore_text(current, placeholders))
                        current = sent
            else:
                current = para

    if current:
        chunks.append(_restore_text(current, placeholders))

    return chunks


# 单条切片字符上限。嵌入模型（DashScope text-embedding-v3）单条输入上限 8192 token，
# 中文近似 1 字 1 token，这里按字符留足余量。
# ★2026-09-20 加：实测 `省法院报告0620.docx` / `省人社厅能源审计报告0620.docx` /
#   `山东永锋纺织有限公司能源审计报告.pdf` 三份整份入库失败，报
#   `Range of input length should be [1, 8192]`——根因是 `_smart_split` 对
#   "超过 max_chars 且没有句读的整块文本"（典型是整页表格）会原样返回一整块。
MAX_CHUNK_CHARS = 3000


def _split_oversized(text: str, max_chars: int = MAX_CHUNK_CHARS,
                     overlap: int = 200) -> list[str]:
    """超长文本按字符窗口硬切（带重叠）。只用于兜底，正常切片走 _smart_split。"""
    if len(text) <= max_chars:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        parts.append(text[start:end])
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return parts


def build_chunks(structure: dict) -> list[dict]:
    """
    返回三层 chunk 列表:
    L1: 1个 summary chunk
    L2: N个 chapter chunks
    L3: M个 paragraph chunks（带保护模式 + 内容类型标记）
    每个 chunk 带统一元数据 + chunk_type 标记 + 前后关系索引。
    """
    cat, spec_type = classify_institution(
        structure["filename"], structure.get("unit_name", "")
    )

    chunks = []
    base_meta = {
        "filename": structure["filename"],
        "file_path": structure.get("file_path", ""),
        "file_type": structure.get("file_type", ""),
        "audit_type": infer_audit_type_from_name(structure["filename"]),
        "institution_category": cat,
        "specific_type": spec_type,
        "unit_name": structure.get("unit_name", ""),
        "auditor": structure.get("auditor", ""),
    }

    # ── L1: 摘要 chunk ──
    toc_text = "\n".join(
        f"第{ch_num}章 {ch_title}" for ch_num, ch_title, _ in structure["toc"]
    )
    std_text = "\n".join(f"  - {s}" for s in structure["standards"])
    summary_content = f"""# {structure['unit_name']} 能源审计报告摘要

**单位名称：** {structure['unit_name']}
**机构类型：** {cat} - {spec_type}
**审计机构：** {structure.get('auditor', '未知')}

## 目录结构
{toc_text if toc_text else '（未提取到目录）'}

## 引用标准
{std_text if std_text else '（未提取到标准）'}
"""
    chunks.append({
        **base_meta,
        "type": "summary",
        "chapter": "",
        "text": summary_content,
        "chunk_type": "summary",
        "chunk_index": 0,
    })

    # ── L2: 章节级 chunks ──
    for ch_title, ch_text in structure["chapters"]:
        # 跳过"前言"（封面信息，非实际章节）
        if ch_title in ("前言", "目录"):
            continue
        # 取该章前800字作为章节摘要
        # 过滤掉表格数据行（很多数字/纯数字行）
        lines = ch_text.split("\n")
        summary_lines = []
        for line in lines:
            line = line.strip()
            # 跳过纯数字行、过短行、仅含特殊字符的行
            if not line or re.match(r"^[\d\s.,%\s]+$", line):
                continue
            summary_lines.append(line)
            if len("".join(summary_lines)) > 800:
                break
        chapter_summary = "\n".join(summary_lines)

        chunk_idx = len(chunks)
        chunks.append({
            **base_meta,
            "type": "chapter",
            "chapter": ch_title,
            "text": f"# {ch_title}\n\n{chapter_summary}",
            "chunk_type": "chapter",
            "chunk_index": chunk_idx,
        })

    # ── L3: 段落级 chunks（带保护模式 + 智能分块 + 内容类型标记） ──
    all_paragraph_chunks = []
    for ch_title, ch_text in structure["chapters"]:
        if ch_title in ("前言", "目录"):
            continue
        # Use smart split to protect formulas/tables/code from being cut
        para_texts = _smart_split(ch_text, max_chars=800)
        for para_text in para_texts:
            if len(para_text.strip()) < 10:
                continue
            chunk_type = _detect_chunk_type(para_text)
            all_paragraph_chunks.append({
                "chapter": ch_title,
                "text": para_text.strip(),
                "chunk_type": chunk_type,
            })

    # Add neighbor + parent references (WeKnora-style linked chunks)
    for i, pc in enumerate(all_paragraph_chunks):
        chunk_entry = {
            **base_meta,
            "type": "paragraph",
            "chapter": pc["chapter"],
            "text": pc["text"],
            "chunk_type": pc.get("chunk_type", "text"),
            "chunk_index": i,
        }
        if i > 0:
            chunk_entry["prev_chunk_id"] = f"chunk_{i-1}"
        if i < len(all_paragraph_chunks) - 1:
            chunk_entry["next_chunk_id"] = f"chunk_{i+1}"
        # Link paragraph to parent chapter
        chapter_idx = None
        for j, c in enumerate(chunks):
            if c.get("type") == "chapter" and c.get("chapter") == pc["chapter"]:
                chapter_idx = j
                break
        if chapter_idx is not None:
            chunk_entry["parent_chunk_id"] = f"chunk_{chapter_idx}"
        chunks.append(chunk_entry)

    # ── 收尾兜底：把仍超长的切片切开（见 MAX_CHUNK_CHARS 处的实测说明）──
    #    对正常切片是**空操作**（已入库的 14 份没有超长切片，切分结果不变），
    #    只影响 _smart_split 漏网的整块长文本。
    final: list[dict] = []
    for c in chunks:
        text = str(c.get("text") or "")
        if len(text) <= MAX_CHUNK_CHARS:
            final.append(c)
            continue
        parts = _split_oversized(text)
        for part in parts:
            piece = dict(c)
            piece["text"] = part
            piece["oversized_split"] = len(parts)
            final.append(piece)
    for i, c in enumerate(final):
        c["chunk_index"] = i
    return final


# ── 向量化 + 写入 Qdrant ──
def embed_and_store(chunks: list[dict], collection_name: str, progress_callback=None):
    """使用 Qwen 向量化并写入 Qdrant"""
    import time
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct, VectorParams, Distance
    from rag.embedding import embed_texts

    qdrant = QdrantClient(**qdrant_client_kwargs(timeout=60))

    # 确保集合存在（1024维）
    try:
        qdrant.get_collection(collection_name)
    except Exception:
        qdrant.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
        print(f"创建集合: {collection_name}")

    total = len(chunks)
    print(f"共 {total} 个 chunks，开始向量化...")

    for i in range(0, total, BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]

        vectors = embed_texts(texts)

        points = []
        for j, chunk in enumerate(batch):
            payload = {
                k: v for k, v in chunk.items() if k not in ("text", "point_id")
            }
            payload["text"] = chunk["text"]
            # Honour a caller-assigned deterministic point id (KB vectorization
            # passes uuid5 per doc+index so re-runs overwrite in place).
            points.append(PointStruct(
                id=str(chunk.get("point_id") or uuid.uuid4()),
                vector=vectors[j],
                payload=payload,
            ))

        qdrant.upsert(collection_name=collection_name, points=points)
        done = min(i + len(batch), total)
        print(f"  [{done}/{total}] {batch[0]['filename'][:40]}...", flush=True)
        if progress_callback:
            progress_callback(done, total)
        time.sleep(0.1)  # 避免限速

    print(f"完成！集合 {collection_name} 当前点数: {qdrant.get_collection(collection_name).points_count}")


# ── 主入口 ──
def main():
    import glob

    pdf_dir = sys.argv[1] if len(sys.argv) > 1 else os.getenv("ENERGY_AUDIT_PDF_DIR", "E:/工作目录/能源审计/审计报告")
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf"))

    if not pdf_files:
        print(f"目录 {pdf_dir} 下没有 PDF 文件")
        return

    print(f"找到 {len(pdf_files)} 个 PDF 文件")
    all_chunks = []

    for pdf_path in pdf_files:
        fname = os.path.basename(pdf_path)
        print(f"\n处理: {fname}")
        try:
            structure = extract_pdf_structure(pdf_path)
            chunks = build_chunks(structure)
            print(f"  → {len(chunks)} chunks (L1:1, L2:{len(structure['chapters'])}, L3:{len(chunks)-1-len(structure['chapters'])})")
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            continue

    print(f"\n总计 {len(all_chunks)} chunks，开始向量化并写入 Qdrant...")
    embed_and_store(all_chunks, COLLECTION)

    # 汇总
    from collections import Counter
    cats = Counter(c["institution_category"] for c in all_chunks)
    types = Counter(c["type"] for c in all_chunks)
    print("\n=== 导入完成 ===")
    print(f"总 chunks: {len(all_chunks)}")
    print(f"按类型: {dict(types)}")
    print(f"按机构: {dict(cats)}")


if __name__ == "__main__":
    main()
