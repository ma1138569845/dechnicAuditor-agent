"""本地同类参考报告库。

仿写生成时按审计类型 + 机构类别，从默认文件夹选取同类型报告，
再按「第X章」切出对应正文。Qdrant RAG 是下一层兜底，不在本模块。

默认目录（高 → 低）:
  1. 显式参数 reference_dir
  2. 环境变量 EA_REFERENCE_DIR
  3. Hermes config.yaml → energy_audit.imitate.reference_dir
  4. 包内 config.yaml → imitate.reference_dir
  5. {HERMES_HOME}/rag/report  （与 wiki / data 同级）

推荐布局::

    {HERMES_HOME}/rag/report/
      {省份}/{地市}/{区县}/{审计类型}/*.docx

    例: rag/report/山东/烟台/经济技术开发区/公共机构/某某法院能源审计报告.docx

检索先按区县 → 地市 → 省份收窄，再在同地区内按审计类型 / 机构类别打分。
文件名含地名时，即使未按目录分层也能匹配。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.energy_audit.institution_classifier import classify_institution

AUDIT_TYPES: Tuple[str, ...] = ("公共机构", "公共建筑", "工业企业")
GEO_TAG_KEYS: Tuple[str, ...] = ("province", "city", "district")
# ★2026-09-20 加 .pdf：此前只认 docx/doc/md/txt，导致 7 份正式成稿（含法院母版
#   `日照市岚山区人民法院能源审计报告.pdf`、学校 3 份、医院 1 份、检察院 1 份、
#   工业企业 1 份）**对仿写参考库完全不可见**。
#   注：README.md 等说明文件由 `_is_reference_report()` 按文件名排除，不靠扩展名。
_REPORT_SUFFIXES = {".docx", ".doc", ".pdf", ".md", ".txt"}
# 不是参考报告的说明性/台账文件（按文件名排除）
_NON_REPORT_NAMES = {"readme.md", "index.md", "log.md", "说明.md", "ingest_log.json"}
_CHAPTER_LINE = re.compile(r"第\s*([一二三四五六七八\d]+)\s*章")
_CN_NUM = "一二三四五六七八"
_MIN_PLACE_LEN = 2


def _hermes_report_dir() -> Path:
    """Profile-aware default: {HERMES_HOME}/rag/report."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()) / "rag" / "report"
    except Exception:
        override = os.environ.get("HERMES_HOME")
        if override:
            return Path(override) / "rag" / "report"
        return Path.home() / ".hermes" / "rag" / "report"


def _non_blank(value) -> bool:
    return value is not None and str(value).strip() != ""


def _config_reference_dir() -> Optional[str]:
    try:
        from tools.energy_audit.db_config import _from_hermes_config, _from_local_config
    except Exception:
        return None
    return (
        os.environ.get("EA_REFERENCE_DIR")
        or _from_hermes_config("imitate", "reference_dir")
        or _from_local_config("imitate", "reference_dir")
    )


def resolve_reference_dir(reference_dir: Optional[str] = None) -> Path:
    """解析参考报告根目录。不因目录尚未创建而失败。"""
    raw = (reference_dir or "").strip() or _config_reference_dir() or ""
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            try:
                from tools.energy_audit._paths import PROJECT_ROOT
                path = PROJECT_ROOT / path
            except Exception:
                path = Path.cwd() / path
        return path.resolve()

    return _hermes_report_dir().expanduser().resolve()


def infer_audit_type(path: Path, filename: str = "") -> str:
    """从路径分段或文件名推断审计类型，缺省公共机构。"""
    blob = "/".join(path.parts) + " " + (filename or path.name)
    for audit_type in AUDIT_TYPES:
        if audit_type in blob:
            return audit_type
    return "公共机构"


def _location_blob(path: Path, filename: str = "") -> str:
    return "/".join(str(p) for p in path.parts) + " " + (filename or path.name)


def place_in_text(place: str, text: str) -> bool:
    """地名是否出现在路径或文件名中（允许省/市/区后缀互认）。"""
    needle = (place or "").strip()
    hay = text or ""
    if len(needle) < _MIN_PLACE_LEN or not hay:
        return False
    if needle in hay:
        return True
    variants = {needle}
    for suffix in (
        "特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区",
        "经济技术开发区", "高新技术产业开发区", "技术开发区", "开发区",
        "自治州", "地区", "自治区", "盟", "省", "市", "区", "县", "旗",
    ):
        if needle.endswith(suffix) and len(needle) - len(suffix) >= _MIN_PLACE_LEN:
            variants.add(needle[: -len(suffix)])
        else:
            variants.add(needle + suffix)
    return any(item in hay for item in variants if len(item) >= _MIN_PLACE_LEN)


def _city_consistent(city: str, district: str, blob: str) -> bool:
    """区县命中时，若已知地市，要求路径/文件名也含该市，或区县名本身已含市名。

    避免「经济技术开发区」这种通用区县名把青岛的报告算进烟台。
    """
    if not city:
        return True
    if place_in_text(city, blob):
        return True
    return bool(district) and (city in district or place_in_text(city, district))


def geo_match_level(path: Path, tags: Dict[str, str], filename: str = "") -> str:
    """返回 district / city / province / none。更细的层级优先。"""
    blob = _location_blob(path, filename or path.name)
    district = (tags.get("district") or "").strip()
    city = (tags.get("city") or "").strip()
    province = (tags.get("province") or "").strip()
    if district and place_in_text(district, blob) and _city_consistent(city, district, blob):
        return "district"
    if city and place_in_text(city, blob):
        return "city"
    if province and place_in_text(province, blob):
        return "province"
    return "none"


def infer_places_from_text(text: str) -> Dict[str, str]:
    """从单位名或地址里抽出地市 / 区县（有则填，不强行猜省）。"""
    blob = text or ""
    city = ""
    district = ""
    m_zone = re.search(
        r"([\u4e00-\u9fff]{2,12}(?:经济技术开发区|高新技术产业开发区|技术开发区|开发区|新区))",
        blob,
    )
    if m_zone:
        district = m_zone.group(1)
    m_city = re.search(r"([^\s省市区县旗0-9]{2,8})市", blob)
    if m_city:
        city = m_city.group(1)
        rest = blob[m_city.end():]
        if not district:
            m_dist = re.search(r"([\u4e00-\u9fff]{1,8}[区县旗])", rest)
            if m_dist:
                district = m_dist.group(1)
    if not district:
        m_dist = re.search(r"([\u4e00-\u9fff]{2,8}[区县旗])", blob)
        if m_dist:
            district = m_dist.group(1)
    return {"city": city, "district": district}


def score_reference(path: Path, tags: Dict[str, str]) -> int:
    """地理优先，再审计类型 / 机构类别。类型不符扣分。"""
    filename = path.name
    category, specific = classify_institution(filename)
    audit_type = infer_audit_type(path, filename)
    score = 0
    level = geo_match_level(path, tags, filename)
    if level == "district":
        score += 16
    elif level == "city":
        score += 12
    elif level == "province":
        score += 8
    elif any((tags.get(k) or "").strip() for k in GEO_TAG_KEYS) and level == "none":
        score -= 6
    wanted_type = (tags.get("audit_type") or "").strip()
    if wanted_type:
        if audit_type == wanted_type:
            score += 4
        else:
            score -= 4
    wanted_cat = (tags.get("institution_category") or "").strip()
    if wanted_cat:
        # ★2026-09-20：类别**不符要扣分**（原来只在相符时 +3、不符不扣）
        #   → 医疗查询里"济南大学/省人社厅"与"岚山人民医院"同为 0 分，按文件名排序时
        #   反而把不相关的排到前面。现在不符 -6，确保相符者永远优先。
        if category == wanted_cat:
            score += 3
        else:
            score -= 6
    wanted_spec = (tags.get("specific_type") or "").strip()
    if wanted_spec:
        if specific == wanted_spec:
            score += 2
        else:
            score -= 3
    return score


def list_reference_files(root: Path) -> List[Path]:
    """列出根目录及类型子目录下的**报告成稿**文件（排除 README 等说明文件）。"""
    if not root.exists() or not root.is_dir():
        return []
    files: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _REPORT_SUFFIXES:
            continue
        if path.name.lower() in _NON_REPORT_NAMES:
            continue
        # 规格/标准类文件不属于"同类成稿"（2026-09-20：标准已迁去 rag/standards/，
        # 这里再加一道保险，防止再次混放）
        if any(k in str(path) for k in ("定额标准", "能耗限额", "能耗定额", "设计标准")):
            continue
        # 副本/重复文件不入库
        if any(k in path.stem for k in (" - 副本", "副本", "copy", "(1)")):
            continue
        files.append(path)
    return sorted(files)


def _normalize_chapter_label(label: str) -> str:
    text = re.sub(r"\s+", "", label or "")
    m = _CHAPTER_LINE.search(text)
    if not m:
        return text
    n = m.group(1)
    if n in _CN_NUM:
        n = str(_CN_NUM.index(n) + 1)
    try:
        n = str(int(n))
    except ValueError:
        pass
    return f"第{n}章"


def _extract_plain_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".docx", ".doc"}:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text and p.text.strip())
    if suffix == ".pdf":
        # ★2026-09-20 新增：正式成稿有相当一部分是 PDF（法院母版/学校/医院/工业企业），
        #   此前直接返回 ""，这些报告对仿写链完全不可见。
        try:
            import fitz  # PyMuPDF，与 rag/energy_audit_importer.py 同一依赖
        except ImportError:
            return ""
        try:
            with fitz.open(str(path)) as doc:
                return "\n".join(
                    page.get_text("text") for page in doc
                )
        except Exception:
            return ""
    return ""


def chunk_report_text(text: str, filename: str = "") -> List[Dict[str, str]]:
    """把报告全文按「第X章」切开。"""
    chunks: List[Dict[str, str]] = []
    current_chapter = "封面"
    buf: List[str] = []

    def _flush():
        body = "\n".join(buf).strip()
        if body:
            chunks.append({"chapter": current_chapter, "text": body, "filename": filename})

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _CHAPTER_LINE.search(line) and len(line) < 80:
            _flush()
            current_chapter = line[:60]
            buf = [line]
        else:
            buf.append(line)
    _flush()
    return chunks


def chunk_report_file(path: Path) -> List[Dict[str, str]]:
    try:
        text = _extract_plain_text(path)
    except Exception:
        return []
    return chunk_report_text(text, filename=path.name)


def _chapter_matches(chunk_label: str, wanted: str) -> bool:
    if not wanted:
        return True
    return _normalize_chapter_label(chunk_label) == _normalize_chapter_label(wanted)


def _geo_pool(ranked: List[Tuple[int, Path]], tags: Dict[str, str]) -> Tuple[List[Tuple[int, Path]], str]:
    """区县 → 地市 → 省份 逐步放宽；都没有再退回全部。"""
    steps: List[Tuple[str, frozenset]] = []
    if (tags.get("district") or "").strip():
        steps.append(("district", frozenset({"district"})))
    if (tags.get("city") or "").strip():
        steps.append(("city", frozenset({"district", "city"})))
    if (tags.get("province") or "").strip():
        steps.append(("province", frozenset({"district", "city", "province"})))
    for label, accepted in steps:
        pool = [(s, p) for s, p in ranked if geo_match_level(p, tags) in accepted]
        if pool:
            return pool, label
    return ranked, "none"


def search_local_references(
    chapter: str,
    tags: Optional[Dict[str, str]] = None,
    top_k: int = 5,
    reference_dir: Optional[str] = None,
    root: Optional[Path] = None,
) -> dict:
    """按地区（区县→地市→省份）再按类型检索本地同类报告章节。

    返回形状与 ``rag.rag_search.search_reports`` 对齐：
    ``{results, source, count}``。
    """
    tags = dict(tags or {})
    root = Path(root) if root is not None else resolve_reference_dir(reference_dir)
    files = list_reference_files(root)
    if not files:
        return {"results": [], "source": "local_folder", "count": 0, "reference_dir": str(root)}

    ranked: List[Tuple[int, Path]] = []
    for path in files:
        ranked.append((score_reference(path, tags), path))
    ranked.sort(key=lambda item: (-item[0], item[1].name))

    wanted_type = (tags.get("audit_type") or "").strip()
    wanted_cat = (tags.get("institution_category") or "").strip()

    # ★2026-09-20：**先按「审计类型 + 机构类别」硬过滤，再做地理收窄**。
    #   原实现是"地理收窄后若没有同类，就退回全部（含 score<=0 的不相关成稿）"——
    #   实测「医疗」查询会返回"济南大学/省人社厅/省司法厅"的片段且 score=0，
    #   属"检索失败被当成有结果"。现在没有同类就如实返回空 + note，由上层降级。
    typed: List[Tuple[int, Path]] = []
    for score, path in ranked:
        if wanted_type and infer_audit_type(path, path.name) != wanted_type:
            continue
        if wanted_cat and classify_institution(path.name)[0] != wanted_cat:
            continue
        typed.append((score, path))

    if not typed:
        return {
            "results": [],
            "source": "local_folder",
            "count": 0,
            "reference_dir": str(root),
            "geo_scope": "none",
            "note": (f"本地参考库没有同类型成稿（要求 审计类型={wanted_type or '不限'}、"
                     f"机构类别={wanted_cat or '不限'}）。**不要用不相关报告充当参考**；"
                     f"请降级到向量检索，或如实标注无同类参考。"),
        }

    typed, geo_scope = _geo_pool(typed, tags)

    results: List[dict] = []
    seen = set()
    for score, path in typed:
        if path in seen:
            continue
        seen.add(path)
        chunks = chunk_report_file(path)
        picked = [c for c in chunks if _chapter_matches(c.get("chapter", ""), chapter)]
        if chapter and not picked:
            continue
        for chunk in picked or chunks[:1]:
            category, specific = classify_institution(path.name)
            results.append({
                "filename": path.name,
                "path": str(path),
                "chapter": chunk.get("chapter", ""),
                "text": (chunk.get("text") or "")[:6000],
                "score": float(score),
                "tags": {
                    "audit_type": infer_audit_type(path, path.name),
                    "institution_category": category,
                    "specific_type": specific,
                    "geo_scope": geo_scope,
                    "geo_level": geo_match_level(path, tags),
                },
            })
            if len(results) >= max(1, int(top_k or 5)):
                return {
                    "results": results,
                    "source": "local_folder",
                    "count": len(results),
                    "reference_dir": str(root),
                    "geo_scope": geo_scope,
                }

    return {
        "results": results,
        "source": "local_folder",
        "count": len(results),
        "reference_dir": str(root),
        "geo_scope": geo_scope,
    }


def describe_reference_dir(reference_dir: Optional[str] = None) -> Dict[str, object]:
    root = resolve_reference_dir(reference_dir)
    files = list_reference_files(root)
    by_type = {t: 0 for t in AUDIT_TYPES}
    for path in files:
        by_type[infer_audit_type(path, path.name)] = by_type.get(infer_audit_type(path, path.name), 0) + 1
    return {
        "reference_dir": str(root),
        "exists": root.exists(),
        "file_count": len(files),
        "by_type": by_type,
    }
