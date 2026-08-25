#!/usr/bin/env python3
"""章节段落仿写流水线（独立于 Word 报告生成）。

旧编排 run_pipeline.py → agent_xiaocheng(tags) → search_for_chapter() 仿写
已从 rest_generate 管线移除。本模块把它收敛成一个可单独调用的新功能：

  1. 按项目加载 AuditProject（本地 data.json，缺失则从 PG 采集）
  2. 按章节 / 机构类型 / 具体类型检索同类参考报告
  3. 分析参考文本的段落结构（标题、角色、修辞手法）
  4. Agent 按该结构 + 本项目真实数据仿写
  5. 输出仿写段落（不写入 .docx）

用法:
    from tools.energy_audit.imitate_pipeline import run_imitate
    result = run_imitate("莘县县政府", chapter="第3章", section="3.1 机构职责")

    python -m tools.energy_audit.imitate_pipeline --project 莘县县政府 --chapter 第3章
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401
from tools.energy_audit.project_data import (
    AuditProject,
    BuildingInfo,
    EnergyYearly,
    Equipment,
    load_project,
    shared_office_metering_sentence,
)


class ProjectNotFoundError(LookupError):
    """本地与 PG 都找不到该项目。"""


CHAPTER_CONTEXTS: Dict[str, str] = {
    "第1章": "能源审计执行概要",
    "第2章": "公共机构基本情况",
    "第3章": "能源资源管理状况",
    "第4章": "能源计量及统计状况",
    "第5章": "能源资源消费消耗指标分析",
    "第6章": "用能系统分析",
    "第7章": "节能效果与节能潜力",
    "第8章": "审计结论",
}

_CN_NUM = "一二三四五六七八九十"
_CHAPTER_ALIAS: Dict[str, str] = {}
for _i in range(1, 9):
    _key = f"第{_i}章"
    _CHAPTER_ALIAS[_key] = _key
    _CHAPTER_ALIAS[str(_i)] = _key
    _CHAPTER_ALIAS[f"第{_i}"] = _key
    _CHAPTER_ALIAS[f"chapter{_i}"] = _key
    _CHAPTER_ALIAS[f"ch{_i}"] = _key
    if _i <= 10:
        _CHAPTER_ALIAS[f"第{_CN_NUM[_i - 1]}章"] = _key
        _CHAPTER_ALIAS[f"{_CN_NUM[_i - 1]}"] = _key

_HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,4}\s+"
    r"|第[一二三四五六七八九十\d]+章\s*"
    r"|\d+(?:\.\d+)+\s+"
    r"|[一二三四五六七八九十]+[、.．]\s*"
    r")(.+)$",
    re.M,
)
_HEADING_LINE_RE = re.compile(
    r"^(?:#{1,4}\s+.+|第[一二三四五六七八九十\d]+章.*|\d+(?:\.\d+)+\s+\S+|[一二三四五六七八九十]+[、.．]\s+\S+)"
)
_TABLE_LINE_RE = re.compile(r"^\|.+\|", re.M)
_FENCE_RE = re.compile(r"^```(?:\w+)?\n|\n```$", re.M)

_PATTERN_RULES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("依据引用", re.compile(r"根据[《「]?[^，。\n]{2,40}")),
    ("图表引用", re.compile(r"(?:由|见|如)(?:表|图)\s*[\d.\-]+")),
    ("同比分析", re.compile(r"(同比|较上年|较前一年|增减率|增长了|降低了)")),
    ("结论收束", re.compile(r"(综上所述|由此可见|总体来看|综上分析|总体而言)")),
    ("职责分工", re.compile(r"(领导小组|管理机构|岗位职责|责任部门)")),
    ("目标方针", re.compile(r"(管理目标|管理方针|考核|节能目标)")),
)


# ============================================================
# 1. 章节归一化
# ============================================================

def _merge_section(*parts: str) -> str:
    return " ".join(dict.fromkeys(p.strip(" ：:、-") for p in parts if p and str(p).strip()))


def normalize_chapter(raw: str, section: str = "") -> Tuple[str, str]:
    """把「3」「第三章」「3.1 机构职责」归一成 (第3章, 小节说明)。"""
    leftover = (section or "").strip()
    text = (raw or "").strip()
    if not text:
        return "", leftover

    compact = re.sub(r"\s+", "", text)
    compact_l = compact.lower()
    if compact in _CHAPTER_ALIAS:
        return _CHAPTER_ALIAS[compact], leftover
    if compact_l in _CHAPTER_ALIAS:
        return _CHAPTER_ALIAS[compact_l], leftover

    # 3.1 / 3.1.2 机构职责 — 必须先于单独的「3」匹配
    m_dot = re.match(r"^([1-8])\.(\d+(?:\.\d+)*)\s*(.*)$", text)
    if m_dot:
        chapter = f"第{m_dot.group(1)}章"
        dotted = f"{m_dot.group(1)}.{m_dot.group(2)}"
        return chapter, _merge_section(dotted, m_dot.group(3), leftover)

    m_ch = re.match(r"^第([1-8一二三四五六七八])章\s*(.*)$", text)
    if m_ch:
        n = m_ch.group(1)
        if n in _CN_NUM:
            n = str(_CN_NUM.index(n) + 1)
        return f"第{n}章", _merge_section(m_ch.group(2), leftover)

    return text, leftover


# ============================================================
# 2. 加载项目数据
# ============================================================

def resolve_tags(project: AuditProject, overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """检索标签：项目字段为底，调用方覆盖非空值。"""
    base = project.base
    tags = {
        "audit_type": base.unit_type or "公共机构",
        "institution_category": base.institution_category or "",
        "specific_type": base.specific_type or "",
    }
    for key, value in (overrides or {}).items():
        if value and str(value).strip():
            tags[key] = str(value).strip()
    return {k: v for k, v in tags.items() if v}


def load_project_data(project_name: str, refresh_from_pg: bool = False) -> AuditProject:
    """优先读本地已采集项目；缺失或要求刷新时走 PG 采集。"""
    name = (project_name or "").strip()
    if not name:
        raise ProjectNotFoundError("project_name 不能为空")

    if not refresh_from_pg:
        project = load_project(name)
        if project and (project.base.unit_name or project.base.name):
            return project

    from tools.energy_audit.pg_collector import build_and_save_project

    project = build_and_save_project(name)
    if not project or not (project.base.unit_name or project.base.name):
        raise ProjectNotFoundError(f"未找到项目：{name}")
    return project


# ============================================================
# 3. 检索参考报告
# ============================================================

def retrieve_references(
    chapter: str,
    tags: Dict[str, str],
    context: str = "",
    top_k: int = 5,
    search_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """按章节 + 机构标签检索参考报告。先带 chapter 过滤，空结果再放宽。"""
    search = search_fn
    if search is None:
        from rag.rag_search import search_reports
        search = search_reports

    query = " ".join(
        p for p in (
            tags.get("audit_type", ""),
            tags.get("institution_category", ""),
            tags.get("specific_type", ""),
            chapter,
            context,
        ) if p
    ).strip() or chapter

    tagged = dict(tags)
    if chapter:
        tagged["chapter"] = chapter

    try:
        results = search(query, tagged, top_k)
    except TypeError:
        results = search(query, tagged)

    if results and results.get("results"):
        return results

    try:
        relaxed = search(query, tags, top_k)
    except TypeError:
        relaxed = search(query, tags)
    return relaxed or {"results": [], "source": "none", "count": 0}


# ============================================================
# 4. 段落结构分析
# ============================================================

_CLOSING_LINE_RE = re.compile(r"^(综上所述|由此可见|总体来看|综上分析|总体而言)")


def _heading_text(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,4}\s+", "", line)
    return line.strip()


def _split_sections(text: str) -> List[Dict[str, str]]:
    lines = text.splitlines()
    sections: List[Dict[str, str]] = []
    current_heading = ""
    buf: List[str] = []

    def _flush():
        body = "\n".join(buf).strip()
        if current_heading or body:
            sections.append({"heading": current_heading, "text": body})

    for line in lines:
        stripped = line.strip()
        if _HEADING_LINE_RE.match(stripped):
            _flush()
            current_heading = _heading_text(line)
            buf = []
        elif _CLOSING_LINE_RE.match(stripped):
            _flush()
            current_heading = "小结"
            buf = [line]
        else:
            buf.append(line)
    _flush()
    return sections or [{"heading": "", "text": text.strip()}]


def _summarize_section(text: str, limit: int = 80) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    return compact[:limit] + ("…" if len(compact) > limit else "")


def _infer_role(section: Dict[str, str], index: int, total: int) -> str:
    heading = section.get("heading", "")
    text = section.get("text", "")
    blob = f"{heading}\n{text}"
    if re.search(r"(领导小组|管理机构|岗位职责|责任部门)", heading):
        return "机构职责"
    if re.search(r"(管理目标|管理方针|考核|节能目标)", heading):
        return "目标方针"
    if heading == "小结" or re.search(r"(综上所述|由此可见|总体来看|综上)", heading):
        return "小结"
    if _TABLE_LINE_RE.search(blob):
        return "数据呈现"
    if re.search(r"(同比|较上年|增减率)", blob):
        return "对比分析"
    if re.search(r"(领导小组|管理机构|岗位职责|责任部门)", blob):
        return "机构职责"
    if re.search(r"(管理目标|管理方针|考核|节能目标)", blob):
        return "目标方针"
    if re.search(r"(综上所述|由此可见|总体来看|综上)", blob) or (index == total - 1 and total > 1):
        return "小结"
    if index == 0:
        return "概述"
    return "正文叙述"


def _detect_patterns(text: str) -> List[str]:
    found: List[str] = []
    for label, pattern in _PATTERN_RULES:
        if pattern.search(text) and label not in found:
            found.append(label)
    return found


def analyze_paragraph_structure(reference_texts: Sequence[str]) -> Dict[str, Any]:
    """从参考报告文本抽出可仿写的段落结构。"""
    combined = "\n\n".join(t.strip() for t in reference_texts if t and str(t).strip())
    if not combined:
        return {
            "heading_count": 0,
            "paragraph_count": 0,
            "has_tables": False,
            "headings": [],
            "outline": [],
            "rhetorical_patterns": [],
            "outline_text": "（无参考文本，按该章节常规结构撰写）",
        }

    headings = [_heading_text(m.group(0)) for m in _HEADING_RE.finditer(combined)]
    sections = _split_sections(combined)
    outline = []
    for i, sec in enumerate(sections):
        heading = sec["heading"] or f"段落{i + 1}"
        outline.append({
            "index": i + 1,
            "heading": heading,
            "role": _infer_role(sec, i, len(sections)),
            "summary": _summarize_section(sec["text"]),
        })

    paragraphs = [p for p in re.split(r"\n\s*\n", combined) if p.strip()]
    patterns = _detect_patterns(combined)
    outline_lines = ["写作顺序："]
    for item in outline:
        outline_lines.append(f"{item['index']}. [{item['role']}] {item['heading']}")
        if item["summary"]:
            outline_lines.append(f"   要点：{item['summary']}")
    if patterns:
        outline_lines.append("需沿用的写法：" + "、".join(patterns))
    if _TABLE_LINE_RE.search(combined):
        outline_lines.append("参考中含表格：仿写时保留表位，用本项目数据填表或标注「（此处插表）」。")

    return {
        "heading_count": len(headings),
        "paragraph_count": len(paragraphs),
        "has_tables": bool(_TABLE_LINE_RE.search(combined)),
        "headings": headings,
        "outline": outline,
        "rhetorical_patterns": patterns,
        "outline_text": "\n".join(outline_lines),
    }


# ============================================================
# 5. 抽取本项目可写入段落的事实
# ============================================================

def _fmt_bool(flag) -> str:
    if flag in (1, True, "1", "有", "是"):
        return "有"
    if flag in (0, False, "0", "无", "否"):
        return "无"
    return "未填写"


def _energy_lines(years: Sequence[EnergyYearly]) -> List[str]:
    lines = []
    for ey in sorted(years, key=lambda x: x.year or 0):
        parts = []
        mapping = (
            ("电", ey.electricity_kwh, "kWh"),
            ("水", ey.water_m3, "m³"),
            ("天然气", ey.natural_gas_m3, "m³"),
            ("热", ey.heating_energy_heat_gj, "GJ"),
            ("汽油", ey.petrol_kg, "kg"),
            ("柴油", ey.diesel_kg, "kg"),
        )
        for label, val, unit in mapping:
            if val:
                qty = f"{val:.2f}".rstrip("0").rstrip(".")
                parts.append(f"{label} {qty} {unit}")
        if parts:
            lines.append(f"- {ey.year}年：" + "，".join(parts))
    return lines


def _building_lines(buildings: Sequence[BuildingInfo]) -> List[str]:
    lines = []
    for b in buildings:
        bits = [b.name or "未命名"]
        if b.area:
            bits.append(f"{b.area:g} m²")
        if b.function:
            bits.append(b.function)
        if b.floors:
            bits.append(b.floors)
        elif b.up_floor or b.down_floor:
            bits.append(f"地上{b.up_floor}层/地下{b.down_floor}层")
        lines.append("- " + "，".join(bits))
    return lines


def extract_project_facts(project: AuditProject, chapter_key: str) -> Dict[str, Any]:
    """按章节裁剪本项目事实，供仿写 prompt 使用。"""
    b = project.base
    facts: Dict[str, Any] = {
        "unit_name": b.unit_name,
        "unit_short": b.unit_short or b.unit_name,
        "address": b.address,
        "institution_category": b.institution_category,
        "specific_type": b.specific_type,
        "people_count": b.people_count,
        "building_area": b.building_area,
        "building_count": len(project.buildings),
        "audit_start": b.audit_start,
        "audit_end": b.audit_end,
        "basic_situation": b.basic_situation,
    }
    md: List[str] = [
        f"单位：{b.unit_name}",
        f"机构类型：{b.institution_category or '未填写'} / {b.specific_type or '未填写'}",
    ]
    if b.address:
        md.append(f"地址：{b.address}")
    if b.people_count:
        md.append(f"用能人数：{b.people_count}")
    if b.building_area:
        md.append(f"建筑面积：{b.building_area:g} m²")

    if chapter_key in ("第1章", "第2章"):
        if b.basic_situation:
            md.append(f"基本情况：{b.basic_situation}")
        if b.admin_affiliation:
            md.append(f"行政归属：{b.admin_affiliation}")
        if project.buildings:
            md.append(f"建筑（{len(project.buildings)}栋）：")
            md.extend(_building_lines(project.buildings))

    if chapter_key == "第3章":
        mg = project.management
        md.append(f"管理机构：{mg.management_org or '未填写'}")
        md.append(f"管理方针：{mg.management_policy or '未填写'}")
        md.append(f"管理目标：{mg.management_goals or '未填写'}")
        md.append(f"节能荣誉：{mg.honors or '未填写'}")
        if project.energy_saving:
            es = sorted(project.energy_saving, key=lambda x: x.statistical_year or 0, reverse=True)[0]
            md.append(f"节能管理统计年：{es.statistical_year or '未填写'}")
            md.append(f"能源管理制度：{_fmt_bool(es.energy_management)}")
            if es.energy_pain_points:
                md.append(f"能源利用痛点：{es.energy_pain_points}")
            md.append(f"节能奖项：{_fmt_bool(es.has_awards)}" + (f"（{es.award_name}）" if es.award_name else ""))
            if es.other_measures:
                md.append(f"其他节能措施：{es.other_measures}")

    if chapter_key == "第4章":
        mt = project.metering
        md.append(f"能耗监测系统：{_fmt_bool(mt.has_monitoring_system)}")
        md.append(f"分项计量：{_fmt_bool(mt.has_separate_metering)}")
        md.append(f"分户计量：{_fmt_bool(mt.has_household_metering)}")
        md.append(f"分户缴费：{_fmt_bool(mt.has_household_payment)}")
        shared_line = shared_office_metering_sentence(mt.has_shared_office, project.shared_offices)
        if shared_line:
            md.append(shared_line)
        md.append(f"电表/水表/气表/热表：{mt.electric_meters}/{mt.water_meters}/{mt.gas_meters}/{mt.heat_meters}")
        md.append(f"照明插座独立计量：{_fmt_bool(mt.independent_light_socket)}")
        md.append(f"动力用电独立计量：{_fmt_bool(mt.independent_power)}")
        md.append(f"空调用电独立计量：{_fmt_bool(mt.independent_aircon)}")
        md.append(f"特殊用电独立计量：{_fmt_bool(mt.independent_special)}")
        if mt.independent_other_special:
            md.append(f"其他特殊用电独立计量：{mt.independent_other_special}")
        md.append(f"施工用电独立计量：{_fmt_bool(mt.independent_construction_elec)}")
        md.append(f"施工用水独立计量：{_fmt_bool(mt.independent_construction_water)}")

    if chapter_key in ("第5章", "第7章", "第8章"):
        energy_lines = _energy_lines(project.energy_yearly)
        if energy_lines:
            md.append("年度能耗：")
            md.extend(energy_lines)
        else:
            md.append("年度能耗：未采集")
        if project.indicators:
            md.append("预计算指标：" + json.dumps(project.indicators, ensure_ascii=False)[:800])

    if chapter_key == "第6章":
        if project.equipment:
            md.append(f"设备（{len(project.equipment)}台）：")
            grouped: Dict[str, List[Equipment]] = {}
            for eq in project.equipment:
                grouped.setdefault(eq.category or "其他", []).append(eq)
            for cat, items in grouped.items():
                md.append(f"- {cat}：{len(items)}台")
                for eq in items[:8]:
                    spec = f"（{eq.spec}）" if eq.spec else ""
                    meter = f"，独立计量：{eq.independent_metering}" if eq.independent_metering else ""
                    desc = f"（{eq.independent_metering_desc}）" if eq.independent_metering_desc else ""
                    md.append(f"  · {eq.name}{spec} × {eq.quantity or 1}{meter}{desc}")
        else:
            md.append("设备清单：未采集")

    facts["facts_markdown"] = "\n".join(md)
    return facts


# ============================================================
# 6. Agent 仿写
# ============================================================

def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = _FENCE_RE.sub("", t).strip()
    return t


def _fallback_imitate(
    unit_name: str,
    chapter: str,
    section: str,
    structure: Dict[str, Any],
    facts_md: str,
) -> str:
    title = f"{unit_name}{chapter}"
    if section:
        title += f" {section}"
    lines = [f"{title}（按参考结构组织的草稿，LLM 不可用）", ""]
    outline = structure.get("outline") or []
    if outline:
        lines.append("建议段落结构：")
        for item in outline:
            lines.append(f"{item['index']}. {item['heading']}（{item['role']}）")
        lines.append("")
    lines.append("本项目可用数据：")
    lines.append(facts_md or "（无结构化数据）")
    return "\n".join(lines)


def imitate_paragraph(
    *,
    unit_name: str,
    chapter: str,
    section: str,
    structure: Dict[str, Any],
    facts_md: str,
    reference_excerpt: str,
    llm_fn: Optional[Callable[..., Optional[str]]] = None,
) -> Tuple[str, str]:
    """返回 (paragraph, writer) ，writer 为 'llm' 或 'fallback'。"""
    fn = llm_fn
    if fn is None:
        from tools.energy_audit.llm_client import imitate_from_structure
        fn = imitate_from_structure

    try:
        text = fn(
            unit_name=unit_name,
            chapter=chapter,
            section=section,
            outline_text=structure.get("outline_text", ""),
            project_facts=facts_md,
            reference_excerpt=reference_excerpt,
        )
    except TypeError:
        text = fn(unit_name, chapter, section, structure.get("outline_text", ""), facts_md, reference_excerpt)
    except Exception:
        text = None

    if text and str(text).strip():
        return _strip_fences(str(text)), "llm"
    return _fallback_imitate(unit_name, chapter, section, structure, facts_md), "fallback"


# ============================================================
# 7. 编排入口
# ============================================================

def run_imitate(
    project_name: str,
    chapter: str,
    *,
    section: str = "",
    institution_category: str = "",
    specific_type: str = "",
    audit_type: str = "",
    extra_context: str = "",
    top_k: int = 5,
    refresh_from_pg: bool = False,
    project: Optional[AuditProject] = None,
    search_fn: Optional[Callable[..., dict]] = None,
    llm_fn: Optional[Callable[..., Optional[str]]] = None,
) -> Dict[str, Any]:
    """执行仿写流水线，返回结构化结果。"""
    chapter_key, section_key = normalize_chapter(chapter, section)
    if not chapter_key:
        return {"ok": False, "error": "chapter 不能为空", "paragraph": ""}

    try:
        proj = project or load_project_data(project_name, refresh_from_pg=refresh_from_pg)
    except ProjectNotFoundError as e:
        return {"ok": False, "error": str(e), "paragraph": ""}
    except Exception as e:
        return {"ok": False, "error": f"加载项目失败：{e}", "paragraph": ""}

    overrides = {
        "institution_category": institution_category,
        "specific_type": specific_type,
        "audit_type": audit_type,
    }
    tags = resolve_tags(proj, overrides)
    context = " ".join(
        p for p in (section_key, extra_context, CHAPTER_CONTEXTS.get(chapter_key, "")) if p
    ).strip()

    try:
        rag = retrieve_references(chapter_key, tags, context=context, top_k=top_k, search_fn=search_fn)
    except Exception as e:
        rag = {"results": [], "source": "error", "count": 0, "error": str(e)}

    hits = list(rag.get("results") or [])
    ref_texts = [str(h.get("text") or "") for h in hits if h.get("text")]
    structure = analyze_paragraph_structure(ref_texts)
    facts = extract_project_facts(proj, chapter_key)
    excerpt_parts = []
    for i, h in enumerate(hits[:top_k], 1):
        excerpt_parts.append(
            f"参考{i} [{h.get('filename', '')} / {h.get('chapter', '')}]\n{h.get('text', '')}"
        )
    excerpt = "\n\n---\n\n".join(excerpt_parts)

    paragraph, writer = imitate_paragraph(
        unit_name=facts.get("unit_name") or project_name,
        chapter=chapter_key,
        section=section_key,
        structure=structure,
        facts_md=facts.get("facts_markdown", ""),
        reference_excerpt=excerpt,
        llm_fn=llm_fn,
    )

    sources = [
        {
            "filename": h.get("filename", ""),
            "chapter": h.get("chapter", ""),
            "score": h.get("score"),
            "tags": h.get("tags") or {},
        }
        for h in hits
    ]

    return {
        "ok": True,
        "paragraph": paragraph,
        "writer": writer,
        "chapter": chapter_key,
        "section": section_key,
        "tags": tags,
        "structure": structure,
        "sources": sources,
        "reference_source": rag.get("source", "none"),
        "reference_count": len(hits),
        "project": {
            "unit_name": facts.get("unit_name"),
            "institution_category": facts.get("institution_category"),
            "specific_type": facts.get("specific_type"),
        },
        "notice": (
            None if hits else "未检索到同类参考报告，已按章节常规结构与本项目数据生成草稿。"
        ),
    }


def result_to_jsonable(result: Dict[str, Any]) -> Dict[str, Any]:
    """确保返回值可 json.dumps（测试/REST 共用）。"""
    out = {}
    for k, v in result.items():
        if is_dataclass(v):
            out[k] = asdict(v)
        else:
            out[k] = v
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="按参考报告段落结构仿写指定章节")
    parser.add_argument("--project", required=True, help="被审计单位 / 项目名称")
    parser.add_argument("--chapter", required=True, help="章节，如 第3章 / 3 / 3.1")
    parser.add_argument("--section", default="", help="小节，如 3.1 机构职责")
    parser.add_argument("--institution-category", default="", help="覆盖机构大类，如 党政机关")
    parser.add_argument("--specific-type", default="", help="覆盖具体类型，如 法院")
    parser.add_argument("--audit-type", default="", help="覆盖审计类型")
    parser.add_argument("--context", default="", help="额外检索上下文")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--refresh", action="store_true", help="强制从 PG 重新采集")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)

    result = run_imitate(
        args.project,
        args.chapter,
        section=args.section,
        institution_category=args.institution_category,
        specific_type=args.specific_type,
        audit_type=args.audit_type,
        extra_context=args.context,
        top_k=args.top_k,
        refresh_from_pg=args.refresh,
    )
    if args.json:
        print(json.dumps(result_to_jsonable(result), ensure_ascii=False, indent=2))
    else:
        if not result.get("ok"):
            print(f"[错误] {result.get('error')}")
            return 1
        print(result.get("paragraph") or "")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
