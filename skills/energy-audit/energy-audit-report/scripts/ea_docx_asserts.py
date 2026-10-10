#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ea_docx_asserts.py — 能源审计报告 .docx/.pdf 交付断言器（脚本化装配方案 T0）。

用法:
    python ea_docx_asserts.py <报告.docx> [--pdf <报告.pdf>] [--expect k=v ...] [--json out.json]

硬检查（任一失败 → exit 1）:
    zip_ok            docx 可解包
    toc_field         document.xml 含 TOC 域（instrText 含 'TOC'）
    update_fields     word/settings.xml 含 <w:updateFields>
    header_watermark  前置/正文两节页眉均含 EAWatermark（DrawingML 水印）
    header_divider    正文节页眉含 w:pBdr 底边线；前置节页眉不得含边框
    footer_page       正文节页脚含 PAGE 域
    footer_plain      正文节页脚为纯数字（无「—」或其它文字）
    header_no_vml     页眉无 VML 水印（禁 v:textpath）
    section_split     节数=2（前置节/正文节；2026-09-22 分节）
    prebody_clean     前置节：无页脚引用、页眉无文字、无边框（仅水印）
    body_numbering    正文节含 <w:pgNumType w:start="1"/>（页码从 1 重起）
    toc_no_self_ref   目录未自收录（目录区不重复出现「目录」字样，启发式）
    no_flat_formula   无公式压平残留（已知形态清单）
    no_writer_markers 无写作标记残留（写作参考/数据参考/逐月参考/[FORMULA）
    ch5_narrative     第5章分析叙述段计数 ≥ 15（防「只有图表无文字」，2026-09-20 新增）
    ch5_531_leadin    5.3.1 表前结构：定义段（统计报告期内）＋式中＋引表句（如表5），
                      且「式中」与特殊用能注各恰 1 次（2026-10-08 新增，P1 只告警不阻断）
    ch2_22_structure  2.2 表前结构：须含「全院合计」（面积汇总）与「建筑面积」（逐栋段必填项）
                      （2026-10-10 新增，P1 只告警不阻断）
    --pdf 时另加 2 项:
    pdf_prebody_clean 正文前页面无页眉文字、无页脚数字
    pdf_footer_seq    正文页脚数字序列连续（从 1 起）

度量（总是输出）: oMath / captions / tables / drawings / media_files / ch5_body_paras
                  building_tables / building_tables_cols（建筑基本信息表数量与各表列数）
                  pages / prebody_pages / header_pages / footer_pages（需 --pdf；后三者=正文口径）
--expect 键: pages（容差 ±2）/ oMath / captions / tables / drawings / media_files
"""
import argparse
import json
import re
import sys
import zipfile

from lxml import etree

MARKERS = ["写作参考", "数据参考", "逐月参考", "[FORMULA"]
FLAT_FORMULAS = ["Ejrcn=E", "Eja=ED", "Er=EP", "Vuc=Vk", "Egnm=Egn"]
# P1（2026-10-08 定）：只报告/告警，不阻断装配
P1_NONBLOCKING = {"ch5_531_leadin", "ch2_22_structure"}
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".emf", ".wmf", ".tif", ".tiff")
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def visible_text(doc_xml: str) -> str:
    x = re.sub(r"<w:tab[^>]*/>", " ", doc_xml)
    x = re.sub(r"<w:br[^>]*/>", " ", x)
    return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", x))


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def count_captions(doc_xml: str) -> int:
    """图注计数：按段落拼接全部 w:t 后判定（Word 保存会重排 run 分割，
    不能用单 w:t 正则，否则收尾后计数误报 0）。"""
    n = 0
    for m in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        if re.match(r"图\d+\.\d+", re.sub(r"\s+", "", t)):
            n += 1
    return n


def ch5_narrative_count(doc_xml: str) -> int:
    """第5章分析叙述段计数（2026-09-20 新增）：剔表格/标题/图注表题后，≥12 字段落数。

    区间 = 正文中最后一次「第5章」标题之后、其后首个「第6章」标题之前
    （目录区条目早于正文标题，天然被排除）。"""
    x = re.sub(r"<w:tbl[ >].*?</w:tbl>", " ", doc_xml, flags=re.S)
    paras = []
    for m in re.finditer(r"<w:p[ >].*?</w:p>", x, re.S):
        t = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", m.group(0)))
        paras.append(re.sub(r"\s+", "", t))
    idx5 = None
    for i, t in enumerate(paras):
        if t.startswith("第5章"):
            idx5 = i
    if idx5 is None:
        return 0
    idx6 = len(paras)
    for j in range(idx5 + 1, len(paras)):
        if paras[j].startswith("第6章"):
            idx6 = j
            break
    n = 0
    for t in paras[idx5 + 1:idx6]:
        if len(t) < 12:
            continue
        if re.match(r"^\d+\.\d+", t):       # 小节标题
            continue
        if re.match(r"^[图表]\s*\d", t):     # 图注/表题
            continue
        n += 1
    return n


def ch5_531_leadin_ok(doc_xml: str):
    """5.3.1 表格前结构（2026-10-08 定，形态基准＝莘县行政审批服务局样板）。

    区间 = 正文「5.3.1」标题 → 其后第一张表。要求同时具备：
      ① 定义段（含「统计报告期内」）② 符号段（含「式中」）③ 引表句（含「如表5」）
    防重复：区间内「式中」恰 1 次、特殊用能注恰 1 条。
    分级 P1：只报告，不阻断装配。
    """
    blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", doc_xml, re.S)

    def _ptext(b: str) -> str:
        return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", b))

    cands = [i for i, b in enumerate(blocks)
             if b.startswith("<w:p") and "5.3.1" in norm(_ptext(b))]
    if not cands:
        return False, "未找到含 5.3.1 的段落"
    head = None
    for i in cands:
        m = re.search(r'w:pStyle[^>]*w:val="([^"]*)"', blocks[i])
        style = m.group(1) if m else ""
        if "eading" in style or "标题" in style:
            head = i
            break
    if head is None:                      # 退路：取最后一个（目录条目在前）
        head = cands[-1]
    texts, j = [], head + 1
    while j < len(blocks) and not blocks[j].startswith("<w:tbl"):
        texts.append(_ptext(blocks[j]))
        j += 1
    if j >= len(blocks):
        return False, "5.3.1 之后未找到数据表"
    region = norm("".join(texts))
    miss = []
    if "统计报告期内" not in region:
        miss.append("缺定义段（未含「统计报告期内」）")
    if "式中" not in region:
        miss.append("缺符号段（未含「式中」）")
    if "如表5" not in region:
        miss.append("缺引表句（未含「如表5…所示：」）")
    if region.count("式中") > 1:
        miss.append("「式中」出现 %d 次（应 1 次，疑脚本公式与写作层公式重复）" % region.count("式中"))
    # 特殊用能注按「段」计、不挑措辞：段落以「注：」开头且提到「特殊用能」或「特定功能」。
    # 车库注（只提车库）与项目特有的数据缺口注（如供暖未计量）都不计入。
    n_note = sum(1 for t in texts
                 if "注：" in norm(t) and ("特殊用能" in norm(t) or "特定功能" in norm(t)))
    if n_note != 1:
        miss.append("特殊用能注 %d 条（应恰 1 条）" % n_note)
    if miss:
        return False, "；".join(miss)
    return True, ""


def ch2_22_structure_ok(doc_xml: str):
    """2.2 建筑物概况 表前结构（2026-10-10 定，选项②）。

    区间 = 正文「2.2 …建筑物概况」标题 → 其后第一张表。要求：
      ① 含「全院合计」（面积汇总必须独立成句，不得并进总览段或省略）
      ② 含「建筑面积」（逐栋详情段的必填字段）
    分级 P1：只报告，不阻断装配。
    """
    blocks = re.findall(r"<w:p[ >].*?</w:p>|<w:tbl>.*?</w:tbl>", doc_xml, re.S)

    def _ptext(b: str) -> str:
        return "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", b))

    head = None
    for i, b in enumerate(blocks):
        if not b.startswith("<w:p"):
            continue
        m = re.search(r'w:pStyle[^>]*w:val="([^"]*)"', b)
        style = (m.group(1) if m else "") or ""
        if style.lower().startswith("toc"):        # 目录缓存条目不算正文标题
            continue
        t = norm(_ptext(b))
        if t.startswith("2.2") and "建筑物概况" in t:
            head = i
            break
    if head is None:
        return False, "未定位到 2.2 建筑物概况 标题"
    texts, j = [], head + 1
    while j < len(blocks) and not blocks[j].startswith("<w:tbl"):
        texts.append(_ptext(blocks[j]))
        j += 1
    if j >= len(blocks):
        return False, "2.2 之后未找到建筑表"
    region = norm("".join(texts))
    miss = []
    if "全院合计" not in region:
        miss.append("缺面积汇总句（未含「全院合计」）")
    if "建筑面积" not in region:
        miss.append("逐栋段缺必填项「建筑面积」")
    if miss:
        return False, "；".join(miss)
    return True, ""


def building_tables_info(doc_xml: str):
    """建筑基本信息表检测（2026-09-20 新增）：返回各建筑表「首行列数」列表。

    识别：前 3 行内出现「建筑名称/建筑物名称」（兼容「项目 | 内容」旧表头形态）。
    用途：building_tables / building_tables_cols 度量（结构合规性由 V3 负责 P1 检查）。
    """
    cols = []
    for tm in re.finditer(r"<w:tbl[ >].*?</w:tbl>", doc_xml, flags=re.S):
        tbl = tm.group(0)
        rows = re.findall(r"<w:tr[ >].*?</w:tr>", tbl, flags=re.S)[:3]
        if not rows:
            continue
        n_cols = 0
        hit = False
        for k, tr in enumerate(rows):
            tcs = re.findall(r"<w:tc[ >].*?</w:tc>", tr, flags=re.S)
            if not tcs:
                continue
            if k == 0:
                n_cols = len(tcs)
            first = "".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", tcs[0]))
            if ("建筑名称" in first) or ("建筑物名称" in first):
                hit = True
        if hit:
            cols.append(n_cols)
    return cols


def section_hf_map(z):
    """按 sectPr 顺序返回每节的页眉/页脚部件名（含 sectPr 原文）。

    映射链：w:headerReference / w:footerReference → r:id → word/_rels/document.xml.rels。
    """
    root = etree.fromstring(z.read("word/document.xml"))
    rid_map = {}
    try:
        rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
        for rel in rels:
            rid_map[rel.get("Id")] = rel.get("Target")
    except KeyError:
        pass
    out = []
    for sp in root.findall(".//%ssectPr" % W_NS):
        entry = {"header": [], "footer": [], "xml": etree.tostring(sp, encoding="unicode")}
        for tag, key in (("headerReference", "header"), ("footerReference", "footer")):
            for ref in sp.findall("%s%s" % (W_NS, tag)):
                tgt = (rid_map.get(ref.get(R_NS + "id")) or "").lstrip("/")
                if tgt and not tgt.startswith("word/"):
                    tgt = "word/" + tgt
                if tgt:
                    entry[key].append(tgt)
        out.append(entry)
    return out


def sections_detail(z):
    """按 document 顺序切节，返回 [{orient, text, tables}]。

    tables = [[[cell, ...], ...], ...]（每个表一个行列表）。
    用于核对「附录2 唯一横向节」与「7 列 + 合计行」（2026-09-28 新增）。
    """
    root = etree.fromstring(z.read("word/document.xml"))
    body = root.find(W_NS + "body")
    out = []
    cur = {"text": [], "tables": []}

    def _close(sect_pr):
        orient = "portrait"
        if sect_pr is not None:
            pg = sect_pr.find(W_NS + "pgSz")
            if pg is not None:
                w = int(pg.get(W_NS + "w") or 0)
                h = int(pg.get(W_NS + "h") or 0)
                if pg.get(W_NS + "orient") == "landscape" or (w and h and w > h):
                    orient = "landscape"
        cur["orient"] = orient
        out.append(dict(cur))

    for child in body:
        tag = child.tag
        if tag == W_NS + "p":
            cur["text"].append("".join(t.text or "" for t in child.iter(W_NS + "t")))
            pr = child.find(W_NS + "pPr")
            if pr is not None and pr.find(W_NS + "sectPr") is not None:
                _close(pr.find(W_NS + "sectPr"))
                cur = {"text": [], "tables": []}
        elif tag == W_NS + "tbl":
            rows = []
            for tr in child.findall(W_NS + "tr"):
                rows.append(["".join(t.text or "" for t in tc.iter(W_NS + "t"))
                             for tc in tr.findall(W_NS + "tc")])
            cur["tables"].append(rows)
    _close(body.find(W_NS + "sectPr"))
    return out


# 2026-10-08：单位括号统一全角；比对时做括号归一，半角/全角都认（向后兼容旧稿）
APX2_HEAD_COLS = ["月份", "水量（m³）", "水费（元）", "水单价（元/m³）",
                  "电量（kWh）", "电费（元）", "电单价（元/kWh）"]


def _norm_paren(s: str) -> str:
    return (s or "").replace("(", "（").replace(")", "）").strip()

# 正文禁忌（2026-09-28）：不得出现 snake_case 形态的英文字段名与 markdown 反引号。
# 只看小写+下划线（如 water_saving_fixture_replacement），避免误伤设备型号/编号
# （YSEZEZS45CKE/22、GB/T 29149-2012）与附件名（report_2024）。
_FIELDNAME_RE = re.compile(r"[a-z]{4,}_[a-z]{3,}")


def _apx2_section(sect_detail):
    """返回附录2 所在节（判定口径：该节文本含「附录2：…」且不含其它「附录N：」标题）。"""
    for sec in sect_detail:
        text = "\n".join(sec["text"])
        if "附录2：" in text and not any(
                f"附录{n}：" in text for n in ("1", "3", "4", "5", "6", "7")):
            return sec
    return None


def _apx2_landscape_ok(sect_detail) -> bool:
    """唯一横向节 = 附录2 节（其它节必须纵向）。"""
    land = [s for s in sect_detail if s.get("orient") == "landscape"]
    if len(land) != 1:
        return False
    apx2 = _apx2_section(sect_detail)
    return apx2 is not None and apx2.get("orient") == "landscape"


_APX_NUM_RE = re.compile(r"^附录\s*\d+\s*[:：]")
_APX2_RE = re.compile(r"^附录\s*2\s*[:：]")


def _chapter_pagebreak_ok(doc_xml: str) -> tuple[bool, str]:
    """大章节另起一页（2026-09-29 用户定）：H1（第1~8章、「附录：」总页）与附录区段的
    「附录N：」H2 **必须带 `<w:pageBreakBefore/>`**（段落属性，不用手工分页符）。

    同时防"重复分页造成空白页"：**附录2** 已由横向分节符另起一页，**不得**再设分页。
    """
    missing: list[str] = []
    dup: list[str] = []
    prev_sect = False      # 上一段是否带 w:sectPr（= 分节符 → 本段位于新页之首）
    for m in re.finditer(r"<w:p[ >].*?</w:p>", doc_xml, re.S):
        seg = m.group(0)
        st = re.search(r'<w:pStyle w:val="([^"]+)"', seg)
        sect_here = "<w:sectPr" in seg
        if not st:
            prev_sect = sect_here
            continue
        style = st.group(1)
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", seg)).strip()
        has_brk = "pageBreakBefore" in seg
        if style == "Heading1":
            if not has_brk:
                missing.append(text[:24] or "(H1 空标题)")
        elif style == "Heading2" and _APX_NUM_RE.match(text):
            if _APX2_RE.match(text):
                if has_brk:
                    dup.append(text[:24])
            elif not has_brk and not prev_sect:
                # 紧跟分节符（新页）的附录标题无需再设 pageBreakBefore —— 分节符本身即另起一页，
                # 重复设反而可能多出空白页（实测：附录3 由"切回纵向"的分节符另起一页）。
                missing.append(text[:24])
        prev_sect = sect_here
    why = []
    if missing:
        why.append(f"未设分页 {len(missing)} 处：{'、'.join(missing[:4])}")
    if dup:
        why.append(f"附录2 重复设分页（会多空白页）：{'、'.join(dup[:2])}")
    return (not missing and not dup), "；".join(why)


def _apx2_table_ok(sect_detail) -> bool:
    """附录2 节内每张**逐月表**（表头首列=月份）：7 列固定列序（允许追加 1 列天然气）+ 合计行。

    附录2 内还可能有"三年能源资源消耗及费用汇总表"（表头首列=项目、列为年份），
    该表不受 7 列约束，只要列数 ≥3 即可。
    """
    apx2 = _apx2_section(sect_detail)
    if apx2 is None or not apx2["tables"]:
        return False
    monthly = 0
    for rows in apx2["tables"]:
        head = [c.strip() for c in (rows[0] if rows else [])]
        if not head:
            return False
        if head[0] != "月份":                 # 汇总表等：不套 7 列口径
            if len(head) < 3:
                return False
            continue
        monthly += 1
        if len(head) not in (7, 8):
            return False
        for want, got in zip(APX2_HEAD_COLS, head):
            if _norm_paren(want) != _norm_paren(got):
                return False
        if not any(r and r[0].strip() == "合计" for r in rows):
            return False
    return monthly > 0


def run(docx: str, pdf: str = None):
    z = zipfile.ZipFile(docx)
    znames = z.namelist()
    doc = z.read("word/document.xml").decode("utf-8", "ignore")
    settings = z.read("word/settings.xml").decode("utf-8", "ignore") if "word/settings.xml" in znames else ""
    headers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/header\d+\.xml", n)}
    footers = {n: z.read(n).decode("utf-8", "ignore") for n in znames if re.fullmatch(r"word/footer\d+\.xml", n)}
    media = [n for n in znames if n.startswith("word/media/") and n.lower().endswith(IMG_EXT)]
    sec_maps = section_hf_map(z)
    sect_detail = sections_detail(z)

    instrs = re.findall(r"<w:instrText[^>]*>([^<]*)</w:instrText>", doc)
    text = visible_text(doc)
    tn = norm(text)
    ch5_n = ch5_narrative_count(doc)
    c531_ok, c531_why = ch5_531_leadin_ok(doc)
    c222_ok, c222_why = ch2_22_structure_ok(doc)
    bldg_cols = building_tables_info(doc)
    i = tn.find("目录")
    self_ref = False
    if i >= 0:
        # 剔除未缓存占位的"（打开文档…）"文本（R7 形态带前置"目录"，构建器形态
        # "目录"在括号内）；仅当剔除后仍出现"目录"时才判为自收录（历史 bug 形态）。
        seg = re.sub(r"(目录)?（打开文档[^）]*）", "", tn[i + 2:i + 900])
        j = seg.find("目录")
        if j >= 0:
            self_ref = True
    toc_state = "placeholder" if "（打开文档" in tn else "cached"
    pre_map = sec_maps[0] if sec_maps else {"header": [], "footer": [], "xml": ""}
    # 2026-09-28：附录2 另有横向/纵向节，正文节固定为第 2 节，不再是「最后一节」
    body_map = sec_maps[1] if len(sec_maps) > 1 else {"header": [], "footer": [], "xml": ""}
    pre_hdr = "".join(headers.get(n, "") for n in pre_map["header"])
    body_hdr = "".join(headers.get(n, "") for n in body_map["header"])
    body_ftr = "".join(footers.get(n, "") for n in body_map["footer"])

    checks = {
        "zip_ok": True,
        "toc_field": any("TOC" in s for s in instrs),
        "update_fields": "updateFields" in settings,
        "header_watermark": ("EAWatermark" in pre_hdr) and ("EAWatermark" in body_hdr),
        "header_divider": ("w:pBdr" in body_hdr and "w:bottom" in body_hdr) and ("pBdr" not in pre_hdr),
        "footer_page": "PAGE" in body_ftr,
        "footer_plain": ("PAGE" in body_ftr) and ("—" not in body_ftr),
        "header_no_vml": not any("v:textpath" in h for h in headers.values()),
        "section_split": len(sec_maps) >= 2,
        "prebody_clean": (not pre_map["footer"]) and ("能源审计报告" not in pre_hdr) and ("pBdr" not in pre_hdr),
        "body_numbering": ("w:pgNumType" in body_map["xml"]) and ("w:start=\"1\"" in body_map["xml"]),
        "toc_no_self_ref": not self_ref,
        "no_flat_formula": not [p for p in FLAT_FORMULAS if p in text],
        "no_writer_markers": not [m for m in MARKERS if m in text],
        "ch5_narrative": ch5_n >= 15,
        # 5.3.1 表格前结构（定义段/式中/引表句/注唯一）——P1，不阻断
        "ch5_531_leadin": c531_ok,
        # 2.2 表前结构（全院合计 + 逐栋建筑面积）——P1，不阻断
        "ch2_22_structure": c222_ok,
        "apx2_landscape": _apx2_landscape_ok(sect_detail),
        "apx2_table": _apx2_table_ok(sect_detail),
        "no_field_names": not _FIELDNAME_RE.findall(text) and "`" not in text,
        # 大章节/附录另起一页（2026-09-29 用户定）：见 _chapter_pagebreak_ok
        "chapter_new_page": _chapter_pagebreak_ok(doc)[0],
        # 2026-09-29 用户定：正文引语一律中文全角引号；ASCII 直引号判不合格
        "cn_quotes": '"' not in text,
    }
    details = {}
    flat = [p for p in FLAT_FORMULAS if p in text]
    marks = [m for m in MARKERS if m in text]
    if flat:
        details["no_flat_formula"] = flat
    if marks:
        details["no_writer_markers"] = marks
    if ch5_n < 15:
        details["ch5_narrative"] = "第5章叙述段仅 %d 段（需 ≥ 15）" % ch5_n
    if not checks["section_split"]:
        details["section_split"] = "sectPr 数=%d（期望 ≥2：前置/正文）" % len(sec_maps)
    if not checks["apx2_landscape"]:
        land = [i + 1 for i, s in enumerate(sect_detail) if s.get("orient") == "landscape"]
        details["apx2_landscape"] = (
            "横向节=%s（期望恰好 1 个且为附录2）；附录2 节定位=%s"
            % (land or "无", "命中" if _apx2_section(sect_detail) else "未命中"))
    if not checks["apx2_table"]:
        apx2 = _apx2_section(sect_detail)
        if apx2 is None:
            details["apx2_table"] = "未定位到附录2 节"
        else:
            details["apx2_table"] = "附录2 表头/合计行不符（需 7 列固定列序 + 合计行）；实测表头=%s" % (
                [c.strip() for c in (apx2["tables"][0][0] if apx2["tables"] else [])],)
    if not checks["no_field_names"]:
        details["no_field_names"] = (
            "正文出现英文字段名或反引号：%s（数据来源只留在审核记录/data_sources，"
            "正文改写成中文事实）" % (_FIELDNAME_RE.findall(text)[:5],))
    if not checks["cn_quotes"]:
        n_ascii = text.count('"')
        details["cn_quotes"] = (
            "正文含 %d 个 ASCII 直引号（应为 0）；引语一律用中文全角引号“”"
            "（见 report-format-spec.md《正文禁忌》，2026-09-29 用户定）" % n_ascii)
    if not checks["chapter_new_page"]:
        details["chapter_new_page"] = _chapter_pagebreak_ok(doc)[1]
    if not c531_ok:
        details["ch5_531_leadin"] = c531_why
    if not c222_ok:
        details["ch2_22_structure"] = c222_why
    if not checks["prebody_clean"]:
        why = []
        if pre_map["footer"]:
            why.append("前置节含页脚引用 %s" % pre_map["footer"])
        if "能源审计报告" in pre_hdr:
            why.append("前置节页眉含文字")
        if "pBdr" in pre_hdr:
            why.append("前置节页眉含边框")
        details["prebody_clean"] = "；".join(why) or "未知"
    if not checks["body_numbering"]:
        details["body_numbering"] = "正文节缺 w:pgNumType start=1"
    if not checks["footer_plain"]:
        details["footer_plain"] = "正文节页脚含破折号或缺失 PAGE 域"

    metrics = {
        "toc_state": toc_state,
        "oMath": len(re.findall(r"<m:oMath(?![A-Za-z])", doc)),
        "captions": count_captions(doc),
        "tables": len(re.findall(r"<w:tbl[ >]", doc)),
        "ch5_body_paras": ch5_n,
        "building_tables": len(bldg_cols),
        "building_tables_cols": ",".join(str(c) for c in bldg_cols) or "-",
        "drawings": len(re.findall(r"<w:drawing[ >]", doc)),
        "media_files": len(media),
    }
    if pdf:
        import fitz
        d = fitz.open(pdf)
        n = d.page_count
        metrics["pages"] = n

        def _bottom_digit(page):
            """页脚带（底部 66pt）唯一行且为纯数字 → 页码；否则 None。"""
            h = page.rect.height
            lines = []
            for b in page.get_text("dict").get("blocks", []):
                for l in b.get("lines", []):
                    txt = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                    if txt:
                        lines.append((l["bbox"][3], txt))
            cand = [(y1, tx) for y1, tx in lines if y1 >= h - 66]
            if len(cand) == 1 and re.fullmatch(r"\d+", cand[0][1]):
                return int(cand[0][1])
            return None

        def _top_has_header(page):
            band = "".join(w[4] for w in page.get_text("words") if w[1] < 60)
            return "能源审计报告" in re.sub(r"\s+", "", band)

        nums = [_bottom_digit(d[j]) for j in range(n)]
        tops = [_top_has_header(d[j]) for j in range(n)]
        first = next((j for j in range(n) if nums[j] == 1), None)
        if first is None:
            checks["pdf_footer_from_1"] = False
            details["pdf_footer_from_1"] = "未找到页脚为「1」的正文首页（页码从 1 未生效？）"
            metrics["prebody_pages"] = "-"
            metrics["header_pages"] = "-"
            metrics["footer_pages"] = "-"
        else:
            metrics["prebody_pages"] = first
            pre_bad = []
            for j in range(first):
                if tops[j]:
                    pre_bad.append("p%d 顶部带页眉文字" % (j + 1))
                if nums[j] is not None:
                    pre_bad.append("p%d 含页脚数字 %s" % (j + 1, nums[j]))
            checks["pdf_prebody_clean"] = not pre_bad
            if pre_bad:
                details["pdf_prebody_clean"] = "；".join(pre_bad[:6])
            body_pages = n - first
            hf = sum(1 for j in range(first, n) if tops[j])
            ff = sum(1 for j in range(first, n) if nums[j] == j - first + 1)
            metrics["header_pages"] = "%d/%d" % (hf, body_pages)
            metrics["footer_pages"] = "%d/%d" % (ff, body_pages)
            checks["pdf_footer_seq"] = (ff == body_pages)
            if ff != body_pages:
                bad = [("p%d" % (j + 1), nums[j]) for j in range(first, n)
                       if nums[j] != j - first + 1][:6]
                details["pdf_footer_seq"] = "断点: %s" % bad
    return checks, metrics, details


def main() -> int:
    try:                                   # 详情里可能含 m³ 等非 GBK 字符，避免打印崩掉掩盖结果
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="能源审计报告交付断言器")
    ap.add_argument("docx")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--expect", action="append", default=[], help="k=v，可重复；pages 容差 ±2")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    try:
        checks, metrics, details = run(args.docx, args.pdf)
    except Exception as exc:  # 解包失败等
        print("[FAIL] zip_ok — %s" % exc)
        if args.json_out:
            json.dump({"docx": args.docx, "passed": False, "error": str(exc)},
                      open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return 1

    exp_fail = []
    for e in args.expect:
        k, _, v = e.partition("=")
        k, v = k.strip(), v.strip()
        got = metrics.get(k)
        if got is None:
            exp_fail.append("%s: 无度量值（需要 --pdf？）" % k)
            continue
        try:
            if k == "pages":
                ok = abs(int(got) - int(v)) <= 2
            else:
                ok = int(got) == int(v)
        except (TypeError, ValueError):
            ok = False
        if not ok:
            exp_fail.append("%s: got %s expect %s" % (k, got, v))

    warned = [k for k, v in checks.items() if not v and k in P1_NONBLOCKING]
    failed = [k for k, v in checks.items() if not v and k not in P1_NONBLOCKING] + \
             ["expect:" + f for f in exp_fail]

    for k, v in checks.items():
        tag = "[OK]" if v else ("[WARN]" if k in P1_NONBLOCKING else "[FAIL]")
        d = ""
        if k in details:
            d = " — %s" % details[k]
        print("%s %s%s" % (tag, k, d))
    for f in exp_fail:
        print("[FAIL] expect %s" % f)
    print("-- metrics --")
    for k, v in metrics.items():
        print("  %s = %s" % (k, v))

    if args.json_out:
        json.dump({
            "docx": args.docx, "pdf": args.pdf,
            "checks": checks, "details": details, "metrics": metrics,
            "failed": failed, "passed": not failed,
        }, open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if warned:
        print("[WARN] %d 项 P1 告警（不阻断）：%s" % (len(warned), "、".join(warned)))
    print("[%s] %d 检查失败" % ("PASS" if not failed else "FAIL", len(failed)))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
