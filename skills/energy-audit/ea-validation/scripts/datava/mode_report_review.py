"""V3 REPORT_REVIEW — 报告生成后审查。

三条主线：
    跨章数据一致性  第2章面积 vs 第5章面积、第4章能耗 vs 第5章能耗、与 data.json 对齐
    章节完整性      1~8章齐备、1.6省级规章≥3条、第6章动态H3、第8章平铺结论
    格式规范        字体/字号/行距/缩进/对齐/表格行高（对齐 tools/energy_audit/format_spec.py 的 FormatSpec）

产出：report_review.json + report_review.txt
存在 P0 时进程以退出码 2 结束，上游据此 kanban_block。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .common import (
    SEV_P0,
    SEV_P1,
    SEV_P2,
    Finding,
    ReviewResult,
    build_result,
    fmt_num,
    project_data_path,
    project_dir,
    read_json,
    safe_float,
    with_artifacts,
    write_json,
    write_text,
)

MODE = "REPORT_REVIEW"

EXPECTED_CHAPTERS: Tuple[int, ...] = tuple(range(1, 9))
MIN_PROVINCE_RULES = 3
MIN_CHAPTER6_H3 = 3
MIN_TABLES = 5
AREA_TOLERANCE_PCT = 1.0
ENERGY_TOLERANCE_PCT = 1.0
FORMAT_SAMPLE_LIMIT = 3
BODY_MIN_CHARS = 24  # 短于此长度的段落视为表题/图注，不参与正文格式判定

# 合规占位登记表（可选）：<项目>/missing_items.json
# 结构：{"items":[{"field":"beds_count","label":"床位数","location":"5.3.4","reason":"…"}]}
# 命中登记的占位按 P1 记录（如实呈现数据缺失），未登记的仍按 P0 阻塞。
MISSING_REGISTRY_FILE = "missing_items.json"

# 图注/表题（居中），不参与正文对齐/行距/缩进判定；字号与加粗不判
# （format-spec 与装配脚本对图注字号表述不一致，避免制造新的矛盾）
RE_CAPTION = re.compile(r"^(图|表|附表)\s*\d+\s*[.\-–—]\s*\d+")
RE_TABLE_CAPTION = re.compile(r"^(表|附表)\s*\d+\s*[.\-–—]\s*\d+")
RE_APPENDIX2_TABLE_CAPTION = re.compile(r"^附表\s*2\s*[.\-–—]\s*\d+")
# 合法无表号的表（来源：封面三张信息表由装配脚本直写）
CAPTIONLESS_ALLOWED = {
    "能源审计机构信息表", "能源审计组人员名单", "能源审计配合人员名单",
}

# 第5章「写作参考」类数据表（2026-09-20 新增专项检查）：规范 5.1 无表，
# 参考数据只以文字行保留；若被渲染进正文 → P1（此前以「无表题豁免」身份长期漏检）
CH5_REF_TABLES = {
    "能源消费结构", "能源消费结构表", "逐年能耗对比", "逐年能源消费对比",
}
FMT_CAPTION = {"align": 1}
KIND_LABELS = {
    "h1": "一级标题",
    "h2": "二级标题",
    "h3": "三级标题",
    "body": "正文",
    "caption": "图注/表题",
}


def is_appendix2_table(blocks: Sequence["Block"], index: int) -> bool:
    """判断题注为附表2-x的横向宽表；该类表按装配规则使用 0.8cm 行高。"""
    if index <= 0:
        return False
    for block in reversed(blocks[:index]):
        if block.kind == "tbl":
            return False
        if block.kind == "p" and block.text.strip():
            return bool(RE_APPENDIX2_TABLE_CAPTION.match(block.text.strip()))
    return False

REQUIRED_TABLES: Tuple[str, ...] = (
    "能源审计机构信息表",
    "能源审计组人员名单",
    "能源审计配合人员名单",
)

PLACEHOLDERS: Tuple[Tuple[str, str], ...] = (
    ("【待补充】", "待补充占位符"),
    ("【XX", "XX 占位符"),
    ("YYYY年M月", "日期占位符"),
    ("待LLM生成", "LLM 占位符"),
    ("TODO", "TODO 标记"),
)

# 对齐 tools/energy_audit/format_spec.py 的 FormatSpec
FMT_BODY = {"font": "宋体", "size": 12.0, "line_spacing": 1.5, "indent_pt": 24.0, "align": 3}
FMT_H1 = {"font": "宋体", "size": 15.0, "bold": True, "align": 1}
FMT_H2 = {"font": "宋体", "size": 14.0, "bold": True, "align": 0}
FMT_H3 = {"font": "宋体", "size": 12.0, "bold": True, "align": 0}
TABLE_ROW_HEIGHT_EMU = 363600  # Cm(1.01)
TABLE_ROW_HEIGHT_TOL = 12000

_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

RE_CHAPTER = re.compile(r"^第\s*([0-9]+|[一二三四五六七八九])\s*章")
RE_H2 = re.compile(r"^(\d+)\.(\d+)(?![.\d])")
RE_H3 = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
# 2026-09-29：增加"建筑面积与数字之间的连接词"捕获组（第 1 组），用于排除**标准条文阈值**。
_RE_AREA = (
    r"(?:总?建筑面积|建筑总面积)([^0-9]{0,16})([0-9][0-9,]*(?:\.[0-9]+)?)\s*(万)?\s*"
    r"(?:m2|m²|平方米|㎡)"
)
RE_AREA = re.compile(_RE_AREA)

# 面积阈值语：引标准条文时常见「建筑面积不低于 20000m² 且采用集中空调的公共建筑，应设置…」，
# 其中数字是**标准阈值**、不是本项目面积陈述。实测（2026-09-29）：7.1 引 GB 55015-2021 第 3.3.6 条
# 后，山东（20,549.74 vs 条文 20,000）被判极差 2.75% P0、烟台（24,300 vs 20,000）被判 21.5% P0——
# 两条都是误报。凡"建筑面积 + 阈值语 + 数字"一律不计入本项目面积陈述。
_AREA_THRESHOLD_WORDS = ("不低于", "不少于", "不超过", "不高于", "不超出",
                         "大于", "小于", "≥", "≤")
RE_TCE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:tce|吨标(?:准)?煤)")
RE_LIST_ITEM = re.compile(r"^(?:[（(]?\d+[)）\.、]|[·•\-—])")


# ================================================================
#  docx 结构解析
# ================================================================

@dataclass(frozen=True)
class Block:
    kind: str  # 'p' | 'tbl'
    index: int  # 文档内块序号
    text: str = ""
    obj: Any = None
    chapter: int = 0


def _chapter_number(text: str) -> int:
    match = RE_CHAPTER.match(text)
    if not match:
        return 0
    token = match.group(1)
    return int(token) if token.isdigit() else _CN_DIGITS.get(token, 0)


def parse_blocks(document: Any) -> List[Block]:
    """按文档顺序遍历段落与表格，并标注所属章节。"""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    paragraph_map = {p._element: p for p in document.paragraphs}
    table_map = {t._element: t for t in document.tables}

    blocks: List[Block] = []
    chapter = 0
    for index, child in enumerate(body.iterchildren()):
        if child.tag == qn("w:p"):
            paragraph = paragraph_map.get(child) or Paragraph(child, document)
            text = paragraph.text.strip()
            found = _chapter_number(text)
            if found:
                chapter = found
            blocks.append(Block("p", index, text, paragraph, chapter))
        elif child.tag == qn("w:tbl"):
            table = table_map.get(child) or Table(child, document)
            blocks.append(Block("tbl", index, "", table, chapter))
    return blocks


def chapter_text(blocks: Sequence[Block], chapter: int) -> str:
    return "\n".join(b.text for b in blocks if b.kind == "p" and b.chapter == chapter and b.text)


def chapter_tables(blocks: Sequence[Block], chapter: int) -> int:
    return sum(1 for b in blocks if b.kind == "tbl" and b.chapter == chapter)


# ================================================================
#  跨章数据一致性
# ================================================================

def _normalize_area(value: str, wan: Optional[str]) -> float:
    number = safe_float(value.replace(",", ""))
    return number * 10000.0 if wan else number


def extract_areas(blocks: Sequence[Block]) -> Dict[int, List[float]]:
    """按章节提取建筑面积陈述值（万 m² 已换算为 m²）。

    排除"建筑面积 + 阈值语（不低于/不超过/大于/小于/≥/≤）+ 数字"的**标准条文阈值**
    （见 `_AREA_THRESHOLD_WORDS`），否则引用条文会污染跨章面积一致性判定。
    """
    found: Dict[int, List[float]] = {}
    for block in blocks:
        if block.kind != "p" or not block.text:
            continue
        for m in RE_AREA.finditer(block.text):
            connector, value, wan = m.group(1) or "", m.group(2), m.group(3)
            if any(w in connector for w in _AREA_THRESHOLD_WORDS):
                continue        # 条文阈值，不是本项目面积
            if "面积" in connector:
                # 「供暖按建筑面积计缴热费，供暖面积X m²」中的数值属于后一个
                # 专业面积口径，不是总建筑面积；不能拿它做跨章建筑面积校验。
                continue
            found.setdefault(block.chapter, []).append(_normalize_area(value, wan))
    return found


def check_area_consistency(
    areas: Dict[int, List[float]],
    truth_area: float,
    garage_area: float = 0.0,
    unit_areas: Optional[Sequence[float]] = None,
) -> List[Finding]:
    """D8 口径（2026-09-20）：全文允许两种面积口径——非指标章 = base.building_area；
    第5章指标分母 = 建筑面积扣除地下车库。两者之差视为合法，其余按容差判。

    逐栋白名单（2026-10-13）：2.2 三段式收口后，逐栋段照参考版写「{楼名}总建筑
    面积{area}m²」，与 `_RE_AREA` 同形。近似任一逐栋面积（`buildings[].area`，
    经 `unit_areas` 传入）的陈述视为**合法分栋陈述**，不参与章级口径判定；
    既不近似章级口径、也不近似任何逐栋面积的陈述仍按 P0 报。"""
    findings: List[Finding] = []
    flat = [(ch, v) for ch, values in areas.items() for v in values if v > 0]
    if not flat:
        return [
            Finding(
                code="V3.CROSS.AREA_MISSING",
                category="跨章一致性",
                severity=SEV_P1,
                title="全文未检出建筑面积陈述",
                location="第2章 / 第5章",
                suggestion="确认第2章建筑概况与第5章指标计算说明中写明总建筑面积",
            )
        ]

    effective_area = (
        truth_area - garage_area if garage_area > 0 and truth_area > garage_area else truth_area
    )
    units = [u for u in (unit_areas or []) if u and u > 0]

    def _close(value: float, target: float) -> bool:
        return target > 0 and abs(value - target) / target * 100.0 <= AREA_TOLERANCE_PCT

    values = [v for _, v in flat]
    low, high = min(values), max(values)

    if truth_area > 0:
        chapter_level = [
            (ch, v) for ch, v in flat if _close(v, truth_area) or _close(v, effective_area)
        ]
        illegal = [
            (ch, v)
            for ch, v in flat
            if not _close(v, truth_area)
            and not _close(v, effective_area)
            and not any(_close(v, u) for u in units)
        ]
        if illegal:
            chapter, value = sorted(illegal)[0]  # 同一偏差不重复报，定位一处即可
            expected_desc = (
                f"{fmt_num(truth_area)} m²（或扣除地下车库后 {fmt_num(effective_area)} m²，D8）"
                if effective_area < truth_area else f"{fmt_num(truth_area)} m²（data.json）"
            )
            findings.append(
                Finding(
                    code="V3.CROSS.AREA_VS_SOURCE",
                    category="跨章一致性",
                    severity=SEV_P0,
                    title=f"第{chapter}章建筑面积与项目数据不符",
                    location=f"第{chapter}章",
                    expected=expected_desc,
                    actual=f"{fmt_num(value)} m²",
                    suggestion="修正报告数据源绑定，勿在文本中硬写面积",
                )
            )
        elif not chapter_level:
            # 全部陈述都近似逐栋面积、无任何总面积口径 → 视同"未检出总面积陈述"
            findings.append(
                Finding(
                    code="V3.CROSS.AREA_MISSING",
                    category="跨章一致性",
                    severity=SEV_P1,
                    title="全文未检出总面积陈述（仅逐栋面积）",
                    location="第2章 / 第5章",
                    suggestion="在第2章建筑概况与第5章指标计算说明中写明总建筑面积",
                )
            )
    else:
        # 无 data.json 参照值（truth_area=0）时退化：仍按原极差法判定
        allowed_gap = low * AREA_TOLERANCE_PCT / 100.0
        if low > 0 and (high - low) > allowed_gap:
            detail = "; ".join(f"第{ch}章 {fmt_num(v)} m²" for ch, v in sorted(flat))
            findings.append(
                Finding(
                    code="V3.CROSS.AREA_MISMATCH",
                    category="跨章一致性",
                    severity=SEV_P0,
                    title=f"各章建筑面积不一致（极差 {(high - low) / low * 100.0:.2f}%，超出允许 {allowed_gap:.0f} m²）",
                    detail=detail,
                    location="跨章",
                    expected="非指标章 = base.building_area；第5章指标分母 = 建筑面积扣除地下车库（D8）",
                    actual=f"{fmt_num(low)} ~ {fmt_num(high)} m²",
                    suggestion="统一口径重新生成受影响章节（车库扣除仅适用于第5章 5.3.1/5.3.2 指标分母说明）",
                )
            )
    return findings


def check_ch5_narrative(blocks: Sequence[Block]) -> List[Finding]:
    """第5章各小节分析叙述检查（2026-09-20 新增）。

    - 小节范围：5.2.x / 5.3.x / 5.4.x
    - 0 字叙述 → P0（整节只有图表/公式，历史事故形态）
    - 叙述 < 80 字 → P1（偏薄）
    - 5.3.x 缺「统计报告期内」定义段 / 缺「分别为」结论评价段 → P1
    - 5.4.x 缺基准规则/推导文字（未见 最近一年/三年平均/平均值）→ P1
    """
    findings: List[Finding] = []
    sec_head = re.compile(r"^(5\.[234]\.\d+)(?=\s|　|$)")
    other_head = re.compile(r"^5(?:\.\d+){0,2}(?=\s|　|$)")
    caption = re.compile(r"^[图表]\s*\d")
    cur = None
    stats: Dict[str, List[int]] = {}
    texts: Dict[str, List[str]] = {}

    for b in blocks:
        if b.kind != "p" or not b.text or b.chapter != 5:
            continue
        text = b.text.strip()
        m = sec_head.match(text)
        if m:
            cur = m.group(1)
            stats.setdefault(cur, [0, 0])
            texts.setdefault(cur, [])
            continue
        if other_head.match(text):
            cur = None
            continue
        if cur is None or caption.match(text) or len(text) < 12:
            continue
        if re.fullmatch(r"[0-9A-Za-z.,%×÷=+\-—–/\s（）()]+", text):
            continue
        stats[cur][0] += 1
        stats[cur][1] += len(text)
        texts[cur].append(text)

    if not stats:
        return findings

    empty = sorted(s for s, (n, _c) in stats.items() if n == 0)
    thin = sorted(f"{s}（{c} 字）" for s, (n, c) in stats.items() if n > 0 and c < 80)
    if empty:
        findings.append(
            Finding(
                code="V3.STRUCT.CH5_NARRATIVE_MISSING",
                category="章节完整性",
                severity=SEV_P0,
                title=f"第5章 {len(empty)} 个小节无分析叙述（只有图表/公式）",
                detail="；".join(empty),
                expected="5.2 四段式 / 5.3 定义段+结论评价段 / 5.4 规则段+逐品种推导（author 补写）",
                actual=f"{len(empty)} 个小节 0 字叙述",
                suggestion="在装配稿 ch5_import.md 上按 chapter5-templates 补写叙述段，重装后复验",
            )
        )
    if thin:
        findings.append(
            Finding(
                code="V3.STRUCT.CH5_NARRATIVE_THIN",
                category="章节完整性",
                severity=SEV_P1,
                title=f"第5章 {len(thin)} 个小节叙述偏薄（<80 字）",
                detail="；".join(thin[:10]),
                suggestion="按 chapter5-templates 的段落结构补足（同比/归因/结论评价）",
            )
        )
    sec53 = sorted(s for s in stats if s.startswith("5.3."))
    lack_def = [s for s in sec53 if not any("统计报告期内" in t for t in texts.get(s, []))]
    lack_concl = [s for s in sec53 if not any("分别为" in t for t in texts.get(s, []))]
    if lack_def or lack_concl:
        bits = []
        if lack_def:
            bits.append("缺定义段（未见「统计报告期内」）：" + "、".join(lack_def))
        if lack_concl:
            bits.append("缺结论评价段（未见「分别为」）：" + "、".join(lack_concl))
        findings.append(
            Finding(
                code="V3.STRUCT.CH5_SECTION_TEXT",
                category="章节完整性",
                severity=SEV_P1,
                title="第5章 5.3.x 结构不完整（定义段/结论评价段缺失）",
                detail="；".join(bits),
                expected="指标定义段（标准原文）＋结论评价段（分别为x、y、z…）",
                suggestion="按 chapter5-templates 5.3 各节模板补写",
            )
        )
    sec54 = sorted(s for s in stats if s.startswith("5.4."))
    lack_rule = [s for s in sec54
                 if not any(("最近一年" in t or "三年平均" in t or "平均值" in t)
                            for t in texts.get(s, []))]
    if lack_rule:
        findings.append(
            Finding(
                code="V3.STRUCT.CH5_BASELINE_TEXT",
                category="章节完整性",
                severity=SEV_P1,
                title="第5章 5.4.x 缺基准规则/推导文字",
                detail="；".join("缺推导：" + s for s in lack_rule),
                expected="规则段（三条规则）＋逐品种推导（各年数值→判定→基准值）",
                suggestion="按 chapter5-templates 5.4 模板补写；数值不重算",
            )
        )
    return findings


def check_building_tables(blocks: Sequence[Block]) -> List[Finding]:
    """建筑基本信息表结构（2026-09-20 新增，对齐公司正式报告口径）。

    识别：首格含「建筑名称/建筑物名称」（或「项目」表头且前 3 行出现建筑名称）。
    要求：4 列键值对、无表头行、全表不加粗。
    """
    findings: List[Finding] = []
    issues: List[str] = []
    ch8_idx = None
    for _i, _b in enumerate(blocks):
        if _b.kind == "p" and (_b.text or "").strip().startswith("第8章"):
            ch8_idx = _i
    apx_idx = None
    if ch8_idx is not None:
        for _i in range(ch8_idx, len(blocks)):
            _b = blocks[_i]
            if _b.kind == "p" and (_b.text or "").strip().startswith("附录"):
                apx_idx = _i
                break
    for _bi, b in enumerate(blocks):
        if b.kind != "tbl" or getattr(b, "obj", None) is None:
            continue
        try:
            rows = b.obj.rows
            if not rows:
                continue
            first_cell = rows[0].cells[0].text.strip()
        except Exception:
            continue
        is_bldg = ("建筑名称" in first_cell) or ("建筑物名称" in first_cell)
        if not is_bldg and first_cell == "项目":
            for r in rows[:3]:
                if any(("建筑名称" in c.text or "建筑物名称" in c.text) for c in r.cells):
                    is_bldg = True
                    break
        if not is_bldg:
            continue
        loc = "附录" if (apx_idx is not None and _bi > apx_idx) else (
            ("第%d章" % b.chapter) if getattr(b, "chapter", None) else "附录"
        )
        n_cols = len(rows[0].cells)
        if n_cols != 4:
            issues.append("%s 建筑表为 %d行×%d列（应为 4 列键值对）" % (loc, len(rows), n_cols))
        if first_cell in ("项目", "序号") or (
            n_cols >= 2 and rows[0].cells[1].text.strip() == "内容"
        ):
            issues.append("%s 建筑表出现表头行（应为无表头行）" % loc)
        bold = False
        for c in rows[0].cells:
            for p in c.paragraphs:
                for r in p.runs:
                    if r.bold:
                        bold = True
        if bold:
            issues.append("%s 建筑表首行存在加粗（应为全表不加粗）" % loc)
    if issues:
        findings.append(
            Finding(
                code="V3.STRUCT.BLDG_TABLE",
                category="章节完整性",
                severity=SEV_P1,
                title="建筑基本信息表结构不符（%d 处）" % len(issues),
                detail="；".join(issues[:8]),
                expected="4 列键值对、无表头行、全表不加粗（公司正式报告口径，见 chapter-guides-1-4.md §7 v4.0）",
                suggestion="按 §7 v4.0 重写 ch2/appendix 中该表（4 列、无表头行；装配链按首格「建筑物名称」自动不加粗/等宽）",
            )
        )
    return findings


def check_energy_consistency(blocks: Sequence[Block]) -> List[Finding]:
    """第4章综合能耗与第5章综合能耗的最大陈述值比对。"""
    def max_tce(chapter: int) -> Optional[float]:
        values = [
            safe_float(v.replace(",", ""))
            for v in RE_TCE.findall(chapter_text(blocks, chapter))
        ]
        positives = [v for v in values if v > 0]
        return max(positives) if positives else None

    ch4, ch5 = max_tce(4), max_tce(5)
    if ch4 is None or ch5 is None:
        return []
    deviation = abs(ch4 - ch5) / max(ch4, ch5) * 100.0
    if deviation <= ENERGY_TOLERANCE_PCT:
        return []
    return [
        Finding(
            code="V3.CROSS.ENERGY_MISMATCH",
            category="跨章一致性",
            severity=SEV_P1,
            title=f"第4章与第5章综合能耗最大值偏差 {deviation:.2f}%",
            detail=f"第4章 {fmt_num(ch4)} tce，第5章 {fmt_num(ch5)} tce",
            location="第4章 vs 第5章",
            expected=f"偏差 ≤ {ENERGY_TOLERANCE_PCT:.0f}%",
            actual=f"{deviation:.2f}%",
            suggestion="核对两章是否同口径（是否含交通能耗/供暖能耗），统一后重新生成",
        )
    ]


def check_year_coverage(blocks: Sequence[Block], years: Sequence[int]) -> List[Finding]:
    text = chapter_text(blocks, 5) + "\n" + chapter_text(blocks, 4)
    missing = [year for year in years if str(year) not in text]
    if not missing:
        return []
    return [
        Finding(
            code="V3.CROSS.YEAR_MISSING",
            category="跨章一致性",
            severity=SEV_P1,
            title=f"审计年份未在第4/5章出现：{missing}",
            location="第4章 / 第5章",
            expected=f"覆盖 {list(years)}",
            actual="缺 " + ", ".join(str(y) for y in missing),
            suggestion="核对能耗表与图表是否遗漏该年数据",
        )
    ]


# ================================================================
#  章节完整性
# ================================================================

def check_cover_consistency(
    blocks: Sequence[Block], base: Optional[Dict[str, Any]]
) -> List[Finding]:
    """封面必备要素必须存在，并与 data.json 的项目身份一致。"""
    base = base or {}
    cover_lines = [
        b.text.strip()
        for b in blocks
        if b.kind == "p" and b.chapter == 0 and b.text.strip()
    ]
    cover_compact = re.sub(r"\s+", "", "\n".join(cover_lines))
    unit_name = str(base.get("unit_name") or "").strip()
    org_name = str(
        base.get("audit_org_name") or base.get("auditor") or ""
    ).strip()
    expected_date = str(
        base.get("report_date") or base.get("audit_end") or ""
    ).strip()

    findings: List[Finding] = []
    missing = []
    if "能源审计报告" not in cover_compact:
        missing.append("报告名称")
    if unit_name and re.sub(r"\s+", "", unit_name) not in cover_compact:
        missing.append(f"单位名称「{unit_name}」")
    if org_name and re.sub(r"\s+", "", org_name) not in cover_compact:
        missing.append(f"审计机构「{org_name}」")
    if missing:
        findings.append(
            Finding(
                code="V3.COVER.REQUIRED_MISSING",
                category="封面完整性",
                severity=SEV_P0,
                title="封面必备要素缺失或与项目数据不一致",
                detail="；".join(missing),
                expected="封面包含单位名称、能源审计报告、审计机构和报告日期",
                actual="缺失或未匹配：" + "、".join(missing),
                suggestion="检查报告日期、单位和机构数据后重新装配封面",
            )
        )

    found_date = re.search(r"20\d{2}年\d{1,2}月", cover_compact)
    if not found_date:
        findings.append(
            Finding(
                code="V3.COVER.DATE_MISSING",
                category="封面完整性",
                severity=SEV_P0,
                title="封面落款缺报告日期",
                expected=expected_date or "应有 YYYY年M月 报告日期",
                actual="封面未见报告日期",
                suggestion="补写 base.report_date；为空时由装配器回落到审计结束月或当前年月",
            )
        )
    elif expected_date:
        expected_compact = re.sub(r"\s+", "", expected_date)
        if expected_compact not in cover_compact:
            findings.append(
                Finding(
                    code="V3.COVER.DATE_MISMATCH",
                    category="封面完整性",
                    severity=SEV_P0,
                    title="封面报告日期与项目数据不一致",
                    expected=expected_date,
                    actual=found_date.group(0),
                    suggestion="统一 base.report_date 与封面装配结果后重新生成",
                )
            )
    return findings


def check_chapters(blocks: Sequence[Block]) -> List[Finding]:
    found: List[int] = []
    for block in blocks:
        if block.kind != "p":
            continue
        number = _chapter_number(block.text)
        if number and number not in found:
            found.append(number)

    findings: List[Finding] = []
    missing = [c for c in EXPECTED_CHAPTERS if c not in found]
    if missing:
        findings.append(
            Finding(
                code="V3.STRUCT.CHAPTER_MISSING",
                category="章节完整性",
                severity=SEV_P0,
                title=f"缺少章节：第{'、'.join(str(c) for c in missing)}章",
                expected="第1~8章齐备",
                actual=f"实检出 {found}",
                suggestion="补齐缺失章节后重新生成报告",
            )
        )
    elif found != sorted(found):
        findings.append(
            Finding(
                code="V3.STRUCT.CHAPTER_ORDER",
                category="章节完整性",
                severity=SEV_P0,
                title="章节顺序异常",
                expected="1→8 递增",
                actual=str(found),
                suggestion="检查生成器章节装配顺序",
            )
        )

    empty = [
        c for c in EXPECTED_CHAPTERS
        if c in found and len(chapter_text(blocks, c)) < 80 and chapter_tables(blocks, c) == 0
    ]
    if empty:
        findings.append(
            Finding(
                code="V3.STRUCT.CHAPTER_EMPTY",
                category="章节完整性",
                severity=SEV_P0,
                title=f"章节内容近乎为空：第{'、'.join(str(c) for c in empty)}章",
                expected="正文 ≥ 80 字或含表格",
                actual="仅有标题",
                suggestion="补齐章节正文",
            )
        )
    return findings


def check_province_rules(blocks: Sequence[Block]) -> List[Finding]:
    """1.6 省级规章条目数（≥3 条）。"""
    section: List[str] = []
    collecting = False
    for block in blocks:
        if block.kind != "p" or not block.text:
            continue
        if RE_H2.match(block.text):
            head = RE_H2.match(block.text)
            collecting = head.group(1) == "1" and head.group(2) == "6"
            continue
        if block.chapter >= 2:
            collecting = False
        if collecting:
            section.append(block.text)

    count = sum(1 for line in section if "《" in line or RE_LIST_ITEM.match(line))
    if count >= MIN_PROVINCE_RULES:
        return []
    return [
        Finding(
            code="V3.STRUCT.PROVINCE_RULES",
            category="章节完整性",
            severity=SEV_P1,
            title=f"1.6 省级规章条目不足（{count} 条）",
            location="第1章 1.6",
            expected=f"≥ {MIN_PROVINCE_RULES} 条",
            actual=f"{count} 条",
            suggestion="用 web_search 核实省级节能规章后补录，禁止字符串替换套用他省规章",
        )
    ]


CH6_TITLE = "第6章 主要能源资源利用系统分析"
CH6_SECTION_KEYS = (
    "用电系统运行分析", "用水系统运行分析", "用热系统运行分析",
    "用燃气系统运行分析", "其他用能系统运行分析", "室内环境检测",
)
CH6_BANNED_WORDS = (
    "建议", "优化空间", "浪费风险",
    "未登记", "待平台补录", "平台登记", "系统数据",
)
RE_CH6_SECTION = re.compile(r"^6\.(\d+)\s*")
RE_CH6_SUBSECTION = re.compile(r"^[（(]\s*(\d+)\s*[）)]")
RE_CH6_FIGURE = re.compile(r"^图6\.(\d+)")
RE_CH6_QTY_RATING = re.compile(
    r"\d+(?:\.\d+)?\s*(?:台|套|个)[^。；\n]{0,24}?"
    r"\d+(?:\.\d+)?\s*(?:kW|W)(?:/(?:台|套))?"
)
RE_CH6_MODEL_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?=[A-Z0-9/-]{5,})(?=[A-Z0-9/-]*\d)"
    r"[A-Z][A-Z0-9/-]*[A-Z0-9](?![A-Za-z0-9])"
)
CH6_PUBLIC_INSTITUTION_SYSTEM_ORDER = (
    ("空调与供暖", ("空调与供暖", "空调及供暖", "供暖空调")),
    ("照明", ("照明",)),
    ("办公设备", ("办公设备", "办公")),
    ("特殊用能", ("特殊用能",)),
    ("变配电", ("变配电",)),
    ("其他用电设备", ("其他用电设备",)),
)


def _chapter6_photo_name_key(text: Any) -> str:
    return re.sub(
        r"[\s/／\\、，,。.；;：:（）()\-—_]+",
        "",
        str(text or ""),
    ).lower()


def _chapter6_equipment_img_ids(equipment: Dict[str, Any]) -> List[str]:
    raw = equipment.get("img_ids")
    if isinstance(raw, (list, tuple, set)):
        return [str(v).strip() for v in raw if str(v).strip()]
    return re.findall(r"\d+", str(raw or ""))


def _chapter6_table_device_names(blocks: Sequence["Block"]) -> List[str]:
    names = []
    for block in blocks:
        if block.kind != "tbl" or block.obj is None:
            continue
        try:
            rows = list(block.obj.rows)
            header = [cell.text.strip() for cell in rows[0].cells]
        except (AttributeError, IndexError):
            continue
        if "设备名称" not in header:
            continue
        col = header.index("设备名称")
        for row in rows[1:]:
            try:
                name = row.cells[col].text.strip()
            except (AttributeError, IndexError):
                continue
            if name and name not in ("—", "-"):
                names.append(name)
    return names


def _missing_chapter6_photo_captions(
    captions: Sequence["Block"],
    equipment: Optional[Sequence[Dict[str, Any]]],
    images: Optional[Sequence[Dict[str, Any]]] = None,
    table_device_names: Optional[Sequence[str]] = None,
) -> List[str]:
    """有设备附件、但第6章没有对应设备名图注的设备（按设备名去重）。"""
    caption_keys = []
    for block in captions:
        match = RE_CH6_FIGURE.match(block.text)
        if match:
            caption_keys.append(_chapter6_photo_name_key(
                re.sub(r"^图6\.\d+\s*", "", block.text)
            ))
    available_ids = {
        str(image.get("file_id")).strip()
        for image in (images or [])
        if image.get("file_id") not in (None, "")
    }
    table_keys = [
        _chapter6_photo_name_key(name) for name in (table_device_names or [])
    ]
    missing, seen = [], set()
    for item in equipment or []:
        name = str(item.get("name") or "").strip()
        key = _chapter6_photo_name_key(name)
        ids = _chapter6_equipment_img_ids(item)
        if not key or key in seen or not ids or not available_ids.intersection(ids):
            continue
        if table_keys and not any(key == tk or key in tk or tk in key for tk in table_keys):
            continue
        seen.add(key)
        if not any(key == ck or (key and ck and (key in ck or ck in key))
                   for ck in caption_keys):
            missing.append(name)
    return missing


def check_chapter6_structure(
    blocks: Sequence[Block],
    *,
    public_institution: bool = False,
    equipment: Optional[Sequence[Dict[str, Any]]] = None,
    images: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[Finding]:
    """第6章结构/内容/措辞检查（2026-10-21 重构，P1 只告警）。

    结构权威：`ea-authoring/references/chapter-guides-6-8.md`《第6章》。
    检查：章标题、主干齐全与编号连续、6.1 动态小节与总述、每节三段、
    公共机构分系统顺序与变配电专表、设备表列头、禁词与平台语言、
    第5章图表引用、图注与图片数量。公共建筑继续使用通用设备表规则。
    """
    # 目录条目会继承"第6章"的 chapter 标记（形如「6.1 …\t41」），必须先剔除
    ch6 = [b for b in blocks
           if b.chapter == 6 and not (b.kind == "p" and re.search(r"\t\d+$", b.text))]
    if not ch6:
        return [Finding(
            code="V3.STRUCT.CHAPTER6_MISSING", category="章节完整性",
            severity=SEV_P1, title="第6章缺失", location="第6章",
            expected=CH6_TITLE, actual="未找到第6章")]

    findings: List[Finding] = []

    def add(code: str, title: str, detail: str = "", expected: str = "", actual: str = "") -> None:
        findings.append(Finding(
            code=code, category="章节完整性", severity=SEV_P1,
            title=title, detail=detail, location="第6章",
            expected=expected, actual=actual))

    # 1. 章标题
    title = next((b.text for b in ch6 if b.kind == "p" and b.text.startswith("第6章")), "")
    if CH6_TITLE.replace(" ", "") not in title.replace(" ", ""):
        add("V3.STRUCT.CHAPTER6_TITLE", "第6章标题不符",
            f"实测：{title or '（空）'}", CH6_TITLE, title)

    # 2. 主干（按名称匹配，允许编号随条件节顺延）
    sections: List[Tuple[int, int, str]] = []
    for i, b in enumerate(ch6):
        if b.kind != "p":
            continue
        m = RE_CH6_SECTION.match(b.text)
        if m and any(k in b.text for k in CH6_SECTION_KEYS):
            sections.append((i, int(m.group(1)), b.text))

    names = [t for _, _, t in sections]
    if not any("用电系统运行分析" in t for t in names):
        add("V3.STRUCT.CHAPTER6_TRUNK", "第6章缺 6.1 用电系统运行分析")
    if not any("用水系统运行分析" in t for t in names):
        add("V3.STRUCT.CHAPTER6_TRUNK", "第6章缺 6.2 用水系统运行分析")

    nums = [n for _, n, _ in sections]
    if nums != list(range(1, len(nums) + 1)):
        add("V3.STRUCT.CHAPTER6_NUMBERING", "第6章主干编号不连续",
            f"实测：{nums}", "1..N 连续", str(nums))

    actual_order = [
        next(j for j, k in enumerate(CH6_SECTION_KEYS) if k in t)
        for _, _, t in sections
    ]
    if actual_order != sorted(actual_order):
        add("V3.STRUCT.CHAPTER6_ORDER", "第6章主干顺序错误",
            "顺序应为：" + " → ".join(CH6_SECTION_KEYS), str(CH6_SECTION_KEYS),
            str(names))

    # 3. 6.1 动态小节 + 总述 + 三段式
    idx61 = next((i for i, _, t in sections if "用电系统运行分析" in t), None)
    if idx61 is not None:
        end = next((i for i, _, _ in sections if i > idx61), len(ch6))
        body = ch6[idx61 + 1:end]
        subs = [(j, b) for j, b in enumerate(body)
                if b.kind == "p" and RE_CH6_SUBSECTION.match(b.text)]
        if len(subs) < MIN_CHAPTER6_H3:
            add("V3.STRUCT.CHAPTER6_SUBSECTIONS", f"6.1 动态小节不足（{len(subs)} 个）",
                "6.1 下应按实际系统用（1）（2）…展开", f"≥ {MIN_CHAPTER6_H3} 个",
                f"{len(subs)} 个")

        if public_institution and subs:
            positions: List[Tuple[str, int]] = []
            for sub_index, (_, sub_block) in enumerate(subs):
                for order_index, (label, aliases) in enumerate(
                    CH6_PUBLIC_INSTITUTION_SYSTEM_ORDER
                ):
                    if any(alias in sub_block.text for alias in aliases):
                        positions.append((label, order_index))
                        break
            order_values = [position for _, position in positions]
            if order_values != sorted(order_values):
                add(
                    "V3.STRUCT.CHAPTER6_SYSTEM_ORDER",
                    "6.1 公共机构分系统顺序错误",
                    "实测：" + " → ".join(label for label, _ in positions),
                    " → ".join(
                        label
                        for label, _ in CH6_PUBLIC_INSTITUTION_SYSTEM_ORDER
                    ),
                    str([label for label, _ in positions]),
                )

        first_sub = subs[0][0] if subs else len(body)
        overview = "".join(b.text for b in body[:first_sub]
                           if b.kind == "p" and len(b.text.strip()) >= 8)
        if "包括" not in overview:
            add("V3.STRUCT.CHAPTER6_OVERVIEW", "6.1 缺系统总述句",
                "6.1 开头须用总述句点明本章展开的用电系统，并与后续小节一一对应")

        for k, (j, b) in enumerate(subs):
            stop = subs[k + 1][0] if k + 1 < len(subs) else len(body)
            paras = [x for x in body[j + 1:stop]
                     if x.kind == "p" and len(x.text.strip()) >= 5
                     and not RE_CAPTION.match(x.text)]
            if len(paras) < 3:
                add("V3.STRUCT.CHAPTER6_PARAS", f"{b.text} 正文段数不足",
                    f"实测 {len(paras)} 段（构成/运行方式/特点与评价格式）", "≥3 段",
                    f"{len(paras)} 段")
            for para in paras:
                ratings = RE_CH6_QTY_RATING.findall(para.text)
                models = RE_CH6_MODEL_TOKEN.findall(para.text)
                if len(ratings) >= 3 or len(models) >= 2:
                    add(
                        "V3.STRUCT.CHAPTER6_DEVICE_DETAIL",
                        f"{b.text} 正文重复展开设备明细",
                        f"同一段出现 {len(ratings)} 组「数量＋单台功率」、"
                        f"{len(models)} 个具体型号表述："
                        f"{para.text[:100]}",
                        "系统构成段只写设备类别、总数量、总装机容量和服务范围；"
                        "品牌、型号、数量及单台功率统一下沉设备清单表",
                        f"{len(ratings)} 组 / {len(models)} 个型号",
                    )

    # 4. 设备清单表 7 列 + 表题
    required_cols = ("序号", "设备名称", "品牌", "规格型号", "数量", "单台功率", "运行时间")
    substation_cols = (
        "序号", "设备名称", "规格型号", "形式", "数量",
        "单台容量", "安装时间",
    )
    for i, b in enumerate(ch6):
        if b.kind != "tbl":
            continue
        try:
            header = "".join(c.text.strip() for c in b.obj.rows[0].cells)
        except (AttributeError, IndexError):
            continue
        if "设备名称" not in header:
            continue
        caption = ch6[i - 1].text if i > 0 and ch6[i - 1].kind == "p" else ""
        is_substation_table = (
            public_institution
            and "变配电" in caption
            and all(c in header for c in substation_cols)
        )
        expected_cols = substation_cols if is_substation_table else required_cols
        missing = [c for c in expected_cols if c not in header]
        if missing:
            add("V3.STRUCT.CHAPTER6_TABLE", "第6章设备表列头不符",
                f"缺：{'、'.join(missing)}", " / ".join(expected_cols), header)
        if "设备清单" not in caption:
            add("V3.STRUCT.CHAPTER6_TABLE_CAPTION", "第6章设备表表题不符",
                f"实测表题：{caption or '（空）'}", "表6.X XX系统设备清单")

    # 5. 禁词 / 平台语言
    text = "\n".join(b.text for b in ch6 if b.kind == "p")
    hits = [w for w in CH6_BANNED_WORDS if w in text]
    if hits:
        add("V3.STRUCT.CHAPTER6_WORDING", "第6章出现禁用表述",
            "命中：" + "、".join(hits),
            "只写事实与可验证评价；禁建议类词与平台语言")
    if re.search(r"(?:^|[，。；：、\s])([应需])(?!用|求)", text):
        add("V3.STRUCT.CHAPTER6_WORDING", "第6章出现建议类措辞",
            "出现「应/需」句（建议、要求类表述归第7章）")
    if re.search(r"(?:建议|应|需|可)\s*改造", text):
        add("V3.STRUCT.CHAPTER6_WORDING", "第6章出现建议性改造措辞",
            "「建议改造/应改造/需改造」归第7章；已完成的节能改造可如实陈述")

    # 6. 不得引用第5章图表
    if re.search(r"(?:第5章\s*图|图5\.\d|详见第5章)", text):
        add("V3.STRUCT.CHAPTER6_CH5REF", "第6章引用了第5章图表",
            "第6章应直接写实算数值，不写「详见第5章图…」")

    # 7. 图注与图片数量
    captions = [b for b in ch6 if b.kind == "p" and RE_CH6_FIGURE.match(b.text)]
    if captions:
        fig_nums = [int(RE_CH6_FIGURE.match(b.text).group(1)) for b in captions]
        if fig_nums != list(range(1, len(fig_nums) + 1)):
            add("V3.STRUCT.CHAPTER6_FIG_NUMBER", "第6章图注编号不连续",
                f"实测：{fig_nums}", "1..N 连续", str(fig_nums))
    img_paras = [b for b in ch6 if b.kind == "p" and "<w:drawing" in b.obj._p.xml]
    if len(img_paras) != len(captions):
        add("V3.STRUCT.CHAPTER6_FIG_COUNT", "第6章图片与图注数量不一致",
            f"图片 {len(img_paras)} 张 / 图注 {len(captions)} 条",
            "图注数=图片数", f"{len(img_paras)}/{len(captions)}")
    missing_photo_captions = _missing_chapter6_photo_captions(
        captions, equipment, images, _chapter6_table_device_names(ch6)
    )
    if missing_photo_captions:
        add(
            "V3.STRUCT.CHAPTER6_PHOTO_COVERAGE",
            "第6章设备配图覆盖不足",
            "以下设备有 img_ids，但报告中没有 `图6.N 设备名`："
            + "、".join(missing_photo_captions),
            "每个有 img_ids 的设备行各写一条设备图注",
            f"缺 {len(missing_photo_captions)} 项",
        )

    return findings


def check_chapter5_figures(blocks: Sequence[Block]) -> List[Finding]:
    """第5章图表硬校验：图注与图片一一对应、图号连续、无落单图片。"""
    ch5 = [
        block for block in blocks
        if block.chapter == 5
        and not (block.kind == "p" and re.search(r"\t\d+$", block.text))
    ]
    captions = [
        block for block in ch5
        if block.kind == "p" and re.match(r"^图5\.\d+", block.text)
    ]
    image_blocks = [
        block for block in ch5
        if block.kind == "p" and block.obj is not None
        and "<w:drawing" in block.obj._p.xml
    ]
    findings: List[Finding] = []

    def add(code: str, title: str, detail: str,
            expected: str, actual: str) -> None:
        findings.append(Finding(
            code=code,
            category="章节完整性",
            severity=SEV_P0,
            title=title,
            detail=detail,
            location="第5章",
            expected=expected,
            actual=actual,
        ))

    if not captions:
        add(
            "V3.STRUCT.CHAPTER5_FIG_COUNT",
            "第5章缺少图表",
            "未找到任何 图5.x 图注",
            "第5章图注与图片一一对应",
            "0 条图注",
        )
        return findings

    if len(image_blocks) != len(captions):
        add(
            "V3.STRUCT.CHAPTER5_FIG_COUNT",
            "第5章图片与图注数量不一致",
            f"图片 {len(image_blocks)} 张 / 图注 {len(captions)} 条",
            "图注数=图片数",
            f"{len(image_blocks)}/{len(captions)}",
        )

    numbers = []
    missing, extra = [], []
    pending_images = 0
    for block in ch5:
        if block.kind != "p":
            continue
        has_image = block.obj is not None and "<w:drawing" in block.obj._p.xml
        match = re.match(r"^图5\.(\d+)", block.text)
        if match:
            number = int(match.group(1))
            numbers.append(number)
            if pending_images == 0:
                missing.append(f"图5.{number}")
            elif pending_images > 1:
                extra.append(f"图5.{number} 前有 {pending_images} 张图片")
            pending_images = 0
        elif has_image:
            pending_images += 1

    if pending_images:
        extra.append(f"末条图注后有 {pending_images} 张未配对图片")
    if numbers != list(range(1, len(numbers) + 1)):
        add(
            "V3.STRUCT.CHAPTER5_FIG_NUMBER",
            "第5章图注编号不连续",
            f"实测：{numbers}",
            "1..N 连续",
            str(numbers),
        )
    if missing:
        add(
            "V3.STRUCT.CHAPTER5_FIG_COUNT",
            "第5章存在无图图注",
            "以下图注前没有图片：" + "、".join(missing),
            "每一条图注前恰有 1 张图片",
            f"缺图 {len(missing)} 条",
        )
    if extra:
        add(
            "V3.STRUCT.CHAPTER5_FIG_COUNT",
            "第5章图片未与图注一一对应",
            "；".join(extra),
            "每一条图注前恰有 1 张图片",
            "图片数量不匹配",
        )
    return findings


CH7_CLASSIFICATION_BAD = ("数据异常", "指标超标", "用能系统及设备问题", "计量与统计问题")
CH7_PLATFORM_BAD = ("未登记", "待平台补录", "平台登记", "系统数据")
DEFAULT_CH7_METERING_CLASSES = ("用电", "用水", "用燃气", "用热")

# 7.1.1 计量状态是 0/1/空三态：空值只能省略，不能改写成“未获取到资料”或“待核实”。
# 这里只拦固定的推断句式，不把“燃气蒸汽锅炉未单独计量”等有字段支撑的事实句误伤。
RE_CHAPTER7_711_SPECULATIVE_METERING = re.compile(
    r"现场未获取到[^。；，,]{0,60}(?:单独计量|分类计量)[^。；，,]{0,40}(?:资料|情况)"
    r"|(?:厨房用水|空调供暖补水|供暖空调用水|绿化灌溉用水)"
    r"[^。；，,]{0,35}(?:单独计量|分类计量)?(?:情况)?待(?:进一步)?核实"
    r"|(?:厨房炊事及供冷供热用气|厨房炊事用气|供冷供热用气|供冷供热与厨房炊事用气)"
    r"[^。；，,]{0,30}(?:情况)?待(?:进一步)?核实"
    r"|(?:单独计量|分类计量|分别独立计量)情况待(?:进一步)?核实"
)

# 按面积缴费时，热量表与供热量不属于必须取得的审计数据。出现下列表述说明
# 作者把正常计费方式误判成了计量缺陷，后文还可能据此生成问题卡和整改建议。
RE_HEATING_AREA_BILLING_DEFECT = re.compile(
    r"(?:未安装|未设置|缺少|没有).{0,6}(?:热量(?:计量)?表|热计量表)"
    r"|供热量(?:无法|未)(?:单独)?计量"
    r"|(?:热力实物量|热力|供热量)(?:数据)?(?:缺失|无法取得)"
)


def chapter7_metering_classes(raw: Optional[Dict[str, Any]]) -> Tuple[str, ...]:
    """按 data.json 判断 7.1.1 实际需要覆盖的计量类别。

    年度消费量、计量器具或已登记设备任一成立即认为该类别存在；原始数据缺失时
    退回四类默认口径，供无 data.json 的独立调用保持兼容。
    """
    data = raw or {}
    yearly = [row for row in (data.get("energy_yearly") or []) if isinstance(row, dict)]
    metering = data.get("metering") or {}
    equipment = [eq for eq in (data.get("equipment") or []) if isinstance(eq, dict)]
    buildings = [b for b in (data.get("buildings") or []) if isinstance(b, dict)]
    water_aux = data.get("water_aux") or {}

    def positive(key: str) -> bool:
        return any(safe_float(row.get(key)) > 0 for row in yearly)

    classes: List[str] = []
    if positive("electricity_kwh") or safe_float(metering.get("electric_meters")) > 0:
        classes.append("用电")
    if (
        positive("water_m3")
        or safe_float(metering.get("water_meters")) > 0
        or str(metering.get("water_measured_depth") or "").strip()
        or any(water_aux.get(key) for key in ("greening", "other", "road"))
    ):
        classes.append("用水")
    gas_equipment = any(
        any(k in f"{eq.get('name') or ''}{eq.get('category') or ''}"
            for k in ("燃气", "锅炉", "溴化锂", "厨房", "食堂"))
        or eq.get("has_gas_use") not in (None, "")
        or eq.get("gas_value") not in (None, "")
        or eq.get("fuel_value") not in (None, "")
        for eq in equipment
    )
    if positive("natural_gas_m3") or safe_float(metering.get("gas_meters")) > 0 or gas_equipment:
        classes.append("用燃气")
    if (
        positive("heating_energy_kwh")
        or positive("heating_energy_heat_gj")
        or positive("heating_cost_wan")
        or safe_float(metering.get("heat_meters")) > 0
        or str(metering.get("heat_pay_type") or "").strip()
        or any(str(b.get("heating_source") or "").strip() for b in buildings)
    ):
        classes.append("用热")
    return tuple(classes) or DEFAULT_CH7_METERING_CLASSES


def check_chapter7_structure(
    blocks: Sequence[Block],
    *,
    metering_classes: Optional[Sequence[str]] = None,
) -> List[Finding]:
    """第7章结构（2026-10-21 样板口径，P1 只告警）。

    结构：7.1 用能系统现状分析（7.1.1 能耗监测系统 + 7.1.2… 问题卡片）；
    7.2 节能潜力分析及建议（与 7.1 一一对应 + 管理与行为节能 + 节能率分析）。
    """
    ch7 = [b for b in blocks
           if b.chapter == 7 and not (b.kind == "p" and re.search(r"\t\d+$", b.text))]
    if not ch7:
        return [Finding(
            code="V3.STRUCT.CHAPTER7_MISSING", category="章节完整性",
            severity=SEV_P1, title="第7章缺失", location="第7章",
            expected="第7章 节能效果与节能潜力分析", actual="未找到第7章")]

    findings: List[Finding] = []

    def add(code: str, title: str, detail: str = "", expected: str = "", actual: str = "") -> None:
        findings.append(Finding(
            code=code, category="章节完整性", severity=SEV_P1,
            title=title, detail=detail, location="第7章",
            expected=expected, actual=actual))

    title = next((b.text for b in ch7 if b.kind == "p" and b.text.startswith("第7章")), "")
    if "节能效果与节能潜力分析" not in title.replace(" ", ""):
        add("V3.STRUCT.CHAPTER7_TITLE", "第7章标题不符",
            f"实测：{title or '（空）'}", "第7章 节能效果与节能潜力分析", title)

    h71 = next((i for i, b in enumerate(ch7)
                if b.kind == "p" and re.match(r"^7\.1\s", b.text)), None)
    if h71 is None or "用能系统现状分析" not in ch7[h71].text:
        add("V3.STRUCT.CHAPTER7_71", "7.1 标题不符",
            "应为「7.1 用能系统现状分析」")

    subs71 = [(i, b.text) for i, b in enumerate(ch7)
              if b.kind == "p" and re.match(r"^7\.1\.\d+\s", b.text)]
    if not subs71:
        add("V3.STRUCT.CHAPTER7_SUBS", "7.1 未按问题卡片分节",
            "应使用 7.1.1、7.1.2… 一题一节")
    else:
        if "能耗监测" not in subs71[0][1]:
            add("V3.STRUCT.CHAPTER7_711", "7.1.1 不是能耗监测系统",
                f"实测：{subs71[0][1]}", "7.1.1 能耗监测系统（固定第一节）")
        if not 3 <= len(subs71) <= 8:
            add("V3.STRUCT.CHAPTER7_SUBCOUNT", f"7.1 问题卡片数量异常（{len(subs71)} 节）",
                "典型 3～8 节，按实际问题取", "3～8 节", f"{len(subs71)} 节")
        for _, t in subs71:
            hit = [w for w in CH7_CLASSIFICATION_BAD if w in t]
            if hit:
                add("V3.STRUCT.CHAPTER7_CLASSNAME", "7.1.x 使用了分类名",
                    f"{t}（命中：{hit[0]}）", "标题写具体问题名")

        # 7.1.1 只覆盖本项目实际存在且有证据的计量类别
        start = subs71[0][0]
        end = subs71[1][0] if len(subs71) > 1 else len(ch7)
        body = "".join(b.text for b in ch7[start + 1:end] if b.kind == "p")
        cover_keys = {
            "用电": ("用电",),
            "用水": ("用水",),
            "用燃气": ("燃气",),
            "用热": ("用热", "供暖", "供热量", "热量计量"),
        }
        required_classes = tuple(
            metering_classes or DEFAULT_CH7_METERING_CLASSES
        )
        missing = [
            k for k in required_classes
            if not any(x in body for x in cover_keys.get(k, ()))
        ]
        if missing:
            add("V3.STRUCT.CHAPTER7_711_COVER", "7.1.1 未覆盖应有计量类别",
                "缺：" + "、".join(missing), "、".join(required_classes))

    h72 = next((i for i, b in enumerate(ch7)
                if b.kind == "p" and re.match(r"^7\.2\s", b.text)), None)
    if h72 is None or "节能潜力分析及建议" not in ch7[h72].text:
        add("V3.STRUCT.CHAPTER7_72", "7.2 标题不符",
            "应为「7.2 节能潜力分析及建议」")

    subs72 = [(i, b.text) for i, b in enumerate(ch7)
              if b.kind == "p" and re.match(r"^7\.2\.\d+\s", b.text)]
    if subs71 and len(subs72) != len(subs71) + 2:
        add("V3.STRUCT.CHAPTER7_MAP", "7.2 建议数量与 7.1 不对应",
            f"7.1.x {len(subs71)} 节 / 7.2.x {len(subs72)} 节",
            "7.2 = 7.1 + 管理与行为节能 + 节能率分析",
            f"{len(subs72)} 节")
    if subs72:
        tail = [t for _, t in subs72[-2:]]
        if "管理与行为节能" not in tail[0] or "节能率分析" not in tail[1]:
            add("V3.STRUCT.CHAPTER7_TAIL", "7.2 末尾两节不符",
                f"实测末两节：{tail}", "管理与行为节能 → 节能率分析")

    text = "\n".join(b.text for b in ch7 if b.kind == "p")
    hits = [w for w in CH7_PLATFORM_BAD if w in text]
    if hits:
        add("V3.STRUCT.CHAPTER7_PLATFORM", "第7章出现平台语言",
            "命中：" + "、".join(hits),
            "删除平台语言；字段为空时省略结论，不得替换为「现场未获取到」或「待核实」")

    return findings


def check_chapter7_711_metering_semantics(blocks: Sequence[Block]) -> List[Finding]:
    """7.1.1 空计量字段不得被改写成“未获取到/待核实”。

    只扫描 7.1.1 到下一个 7.1.x（或 7.2）之间的正文。明确登记为 0 的
    “未单独计量”是合法事实；“现场未获取到……计量资料”“……计量情况待进一步
    核实”才是把空值反向推断成结论，记 P1。
    """
    ch7 = [
        b for b in blocks
        if b.chapter == 7 and not (b.kind == "p" and re.search(r"\t\d+$", b.text))
    ]
    start = next(
        (
            i for i, b in enumerate(ch7)
            if b.kind == "p" and re.match(r"^7\.1\.1\s+能耗监测", b.text)
        ),
        None,
    )
    if start is None:
        return []
    end = next(
        (
            i for i in range(start + 1, len(ch7))
            if ch7[i].kind == "p"
            and (re.match(r"^7\.1\.\d+\s", ch7[i].text)
                 or re.match(r"^7\.2\s", ch7[i].text))
        ),
        len(ch7),
    )

    hits: List[str] = []
    for block in ch7[start + 1:end]:
        if block.kind != "p" or not block.text:
            continue
        match = RE_CHAPTER7_711_SPECULATIVE_METERING.search(block.text)
        if match:
            hits.append(f"命中「{match.group(0)}」；原文：{block.text.strip()[:140]}")

    if not hits:
        return []
    return [
        Finding(
            code="V3.STRUCT.CHAPTER7_711_METERING_SPECULATION",
            category="写作规范",
            severity=SEV_P1,
            title="7.1.1 将空计量字段误写为未获取或待核实",
            detail="；".join(hits[:6]),
            location="第7章 7.1.1",
            expected=(
                "计量状态按 0=明确无、1=明确有、空=省略处理；"
                "空值不得推断为未单独计量或待核实"
            ),
            actual=f"{len(hits)} 处推断性表述",
            suggestion=(
                "删除空字段对应的用途及计量结论；已确认的未计量事实保持黑字。"
                "只有两个证据确实冲突并已提请单位确认时，才写清冲突内容并标红【待核实】"
            ),
        )
    ]


def check_heating_billing_semantics(
    blocks: Sequence[Block], heat_pay_type: str
) -> List[Finding]:
    """按面积缴费不得被误写成热量计量缺陷。

    仅在 `data.json → metering.heat_pay_type` 明确为按面积缴费时触发。
    `heat_meters=0`、缴费方式缺失或按计量表缴费，都不能套用这条规则。
    """
    if "按面积" not in str(heat_pay_type or ""):
        return []

    hits: List[Tuple[int, str, str]] = []
    for block in blocks:
        texts: List[str] = []
        if block.kind == "p" and block.text:
            texts.append(block.text)
        elif block.kind == "tbl":
            try:
                texts.extend(
                    cell.text
                    for row in block.obj.rows
                    for cell in row.cells
                    if cell.text
                )
            except (AttributeError, TypeError):
                pass
        for text in texts:
            match = RE_HEATING_AREA_BILLING_DEFECT.search(text)
            if match:
                hits.append((block.chapter, match.group(0), text.strip()[:120]))

    if not hits:
        return []

    chapters = sorted({chapter for chapter, _, _ in hits if chapter})
    location = (
        "、".join(f"第{chapter}章" for chapter in chapters)
        if chapters else "全文"
    )
    details = [
        f"{f'第{chapter}章：' if chapter else ''}命中「{phrase}」；原文：{text}"
        for chapter, phrase, text in hits[:6]
    ]
    return [
        Finding(
            code="V3.STRUCT.HEATING_AREA_BILLING",
            category="写作规范",
            severity=SEV_P1,
            title="按面积缴费被误写为热量计量缺陷",
            detail="；".join(details),
            location=location,
            expected=(
                "按面积缴费只客观写供暖面积、计费单价和费用；"
                "不得写未安装热量表、供热量无法计量或热力数据缺失"
            ),
            actual=f"{len(hits)} 处错误定性",
            suggestion=(
                "删除计量缺陷、待核实和整改表述；缴费方式为按面积时，"
                "热量表与供热量不是必须取得的审计数据"
            ),
        )
    ]


RE_APPENDIX_START = re.compile(r"^附录(?:\s*[:：]|[0-9一二三四五六七八九十]+[：:])")
RE_PAREN_ITEM = re.compile(r"^[（(]\d+[)）]\s*\S")


def check_chapter8_summary(blocks: Sequence[Block]) -> List[Finding]:
    """检查第8章是否为平铺结论，并与第5/7章条目数及名称联动。

    第8章按三份外部样板采用平铺结构：无 8.x 分节、无表格；建议清单每项
    独立成段。条数不能手写拍脑袋：指标数取第5章 5.3.x，问题数取第7章
    7.1.x，建议数取第7章 7.2.x 中除“节能率分析”以外的各节。
    """
    title_index = next(
        (
            i for i, b in enumerate(blocks)
            if b.kind == "p"
            and b.chapter == 8
            and b.text.startswith("第8章")
            and not re.search(r"\t\d+$", b.text)
        ),
        None,
    )
    if title_index is None:
        return [Finding(
            code="V3.STRUCT.CHAPTER8_TITLE",
            category="章节完整性",
            severity=SEV_P1,
            title="第8章缺失",
            location="第8章",
            expected="第8章 审计结论",
            actual="未找到第8章",
        )]

    end = len(blocks)
    for i in range(title_index + 1, len(blocks)):
        block = blocks[i]
        if block.kind == "p" and RE_APPENDIX_START.match(block.text):
            end = i
            break
    ch8 = blocks[title_index:end]
    findings: List[Finding] = []

    def add(code: str, title: str, detail: str = "",
            expected: str = "", actual: str = "") -> None:
        findings.append(Finding(
            code=code,
            category="章节完整性",
            severity=SEV_P1,
            title=title,
            detail=detail,
            location="第8章",
            expected=expected,
            actual=actual,
        ))

    chapter_title = ch8[0].text.strip()
    if chapter_title != "第8章 审计结论":
        add(
            "V3.STRUCT.CHAPTER8_TITLE",
            "第8章标题不符",
            f"实测：{chapter_title}",
            "第8章 审计结论（不带“与建议”）",
            chapter_title,
        )

    section_headings = [
        b.text for b in ch8
        if b.kind == "p" and re.match(r"^8\.\d+(?:\.\d+)?\s", b.text)
    ]
    if section_headings:
        add(
            "V3.STRUCT.CHAPTER8_SECTION",
            "第8章出现 8.x 分节",
            "；".join(section_headings[:5]),
            "平铺式，无 8.x 分节",
            f"{len(section_headings)} 个分节标题",
        )

    table_count = sum(1 for b in ch8 if b.kind == "tbl")
    if table_count:
        add(
            "V3.STRUCT.CHAPTER8_TABLE",
            "第8章出现正文表格",
            expected="无表格（附录表格不计入第8章）",
            actual=f"{table_count} 张",
        )

    expected_indicators = sum(
        1 for b in blocks
        if b.kind == "p"
        and b.chapter == 5
        and re.match(r"^5\.3\.\d+\s", b.text)
        and not re.search(r"\t\d+$", b.text)
    )
    indicator_items = [
        b.text for b in ch8[1:]
        if b.kind == "p"
        and re.match(r"^\d+[.．、]\s*\S", b.text)
        and "分别为" in b.text
    ]
    if expected_indicators and len(indicator_items) != expected_indicators:
        add(
            "V3.STRUCT.CHAPTER8_INDICATORS",
            "第8章指标条数与第5章不一致",
            f"第5章 5.3.x {expected_indicators} 项 / 第8章逐条 {len(indicator_items)} 项",
            "逐项写全，每项独立成段",
            f"{len(indicator_items)} 项",
        )

    ch7 = [
        b for b in blocks
        if b.kind == "p"
        and b.chapter == 7
        and not re.search(r"\t\d+$", b.text)
    ]
    problem_titles = [
        b.text for b in ch7 if re.match(r"^7\.1\.\d+\s", b.text)
    ]
    recommendation_titles = [
        b.text for b in ch7 if re.match(r"^7\.2\.\d+\s", b.text)
    ]
    recommendation_titles = [
        t for t in recommendation_titles if "节能率分析" not in t
    ]

    chapter8_text = "\n".join(b.text for b in ch8 if b.kind == "p")
    problem_match = re.search(r"发现用能管理问题\s*(\d+)\s*项", chapter8_text)
    suggestion_match = re.search(
        r"提出[^。；\n]{0,20}建议(?:共计)?\s*(\d+)\s*条",
        chapter8_text,
    )
    count_errors: List[str] = []
    if problem_titles:
        if not problem_match:
            count_errors.append(f"未写问题数量（应为{len(problem_titles)}项）")
        elif int(problem_match.group(1)) != len(problem_titles):
            count_errors.append(
                f"问题数写{problem_match.group(1)}项（应为{len(problem_titles)}项）"
            )
    if recommendation_titles:
        if not suggestion_match:
            count_errors.append(f"未写建议数量（应为{len(recommendation_titles)}条）")
        elif int(suggestion_match.group(1)) != len(recommendation_titles):
            count_errors.append(
                f"建议数写{suggestion_match.group(1)}条（应为{len(recommendation_titles)}条）"
            )
    if count_errors:
        add(
            "V3.STRUCT.CHAPTER8_COUNTS",
            "第8章问题/建议计数与第7章不一致",
            "；".join(count_errors),
            "问题数=7.1.x；建议数=7.2.x 除“节能率分析”外各节",
        )

    suggestion_items = [
        b.text.strip() for b in ch8[1:]
        if b.kind == "p" and RE_PAREN_ITEM.match(b.text.strip())
    ]
    if recommendation_titles:
        if len(suggestion_items) != len(recommendation_titles):
            add(
                "V3.STRUCT.CHAPTER8_LIST_FORMAT",
                "第8章建议清单未逐项分行",
                f"建议项段落 {len(suggestion_items)} 个 / 应分开 {len(recommendation_titles)} 项",
                "每条建议各占一个独立段落，不把多条用分号挤在同一段",
                f"{len(suggestion_items)} 段",
            )
        elif any(
            len(re.findall(r"[（(]\d+[)）]", item)) > 1
            for item in suggestion_items
        ):
            add(
                "V3.STRUCT.CHAPTER8_LIST_FORMAT",
                "第8章建议清单存在合并段落",
                "同一段中出现多个建议编号",
                "每条建议各占一个独立段落",
            )

        expected_names = [
            re.sub(r"^7\.2\.\d+\s*", "", t).strip()
            for t in recommendation_titles
        ]
        if len(suggestion_items) == len(expected_names):
            for item, expected_name in zip(suggestion_items, expected_names):
                if expected_name not in item:
                    add(
                        "V3.STRUCT.CHAPTER8_ITEM_TITLE",
                        "第8章建议名称与第7章不一致",
                        f"实测：{item[:60]}",
                        expected_name,
                    )

    return findings


def check_tables_and_placeholders(
    blocks: Sequence[Block], registry: Sequence[Dict[str, str]] = ()
) -> List[Finding]:
    findings: List[Finding] = []
    total_tables = sum(1 for b in blocks if b.kind == "tbl")
    if total_tables < MIN_TABLES:
        findings.append(
            Finding(
                code="V3.STRUCT.TABLE_COUNT",
                category="章节完整性",
                severity=SEV_P1,
                title=f"表格数量偏少（{total_tables} 张）",
                expected=f"≥ {MIN_TABLES} 张",
                actual=f"{total_tables} 张",
                suggestion="核对表1~表3、第2章建筑表、第5章指标表是否齐备",
            )
        )

    # 表题检查（2026-09-20 新增）：**正文**每张表的上方一行应为「表X.Y 标题」/「附表X-Y 标题」
    # 封面/信息表区域（第1章之前）不计；封面三表在 CAPTIONLESS_ALLOWED 内豁免；5.1 参考表走 CH5_REF_TABLES 专项检查。
    captionless: List[str] = []
    ch5_ref: List[str] = []
    prev_text, prev_chapter = "", None
    for b in blocks:
        text = (b.text or "").strip()
        if b.kind == "p":
            if text:
                prev_text, prev_chapter = text, getattr(b, "chapter", None)
            continue
        if b.kind != "tbl":
            continue
        if not prev_chapter:                      # 封面/信息表区域：不属于正文表格
            continue
        if prev_text in CH5_REF_TABLES:
            ch5_ref.append(prev_text[:30] or "（表格上方无段落）")
            continue
        if RE_TABLE_CAPTION.match(prev_text) or prev_text in CAPTIONLESS_ALLOWED:
            continue
        captionless.append(prev_text[:30] or "（表格上方无段落）")
    if captionless:
        findings.append(
            Finding(
                code="V3.STRUCT.TABLE_CAPTION",
                category="章节完整性",
                severity=SEV_P2,
                title=f"有 {len(captionless)} 张正文表缺表题（表X.Y）",
                detail="；".join(f"第{i+1}处「{t}」" for i, t in enumerate(captionless[:5])),
                expected="每张正文表上方一行是 `表X.Y 标题`（附录用 `附表X-Y`）",
                actual=f"{len(captionless)} 张表上方不是表题行",
                suggestion="给每张表补 `表X.Y 标题` 行（章内连续编号、独占一行、紧邻表格上方；附录用附表X-Y）",
            )
        )

    if ch5_ref:
        findings.append(
            Finding(
                code="V3.STRUCT.CH5_REF_TABLE",
                category="章节完整性",
                severity=SEV_P1,
                title=f"第5章出现「写作参考」类数据表 {len(ch5_ref)} 张（禁止进正文）",
                detail="；".join(f"第{i+1}处「{t}」" for i, t in enumerate(ch5_ref[:5])),
                expected="5.1 无表（规范口径）；参考数据仅以文字行保留",
                actual=f"{len(ch5_ref)} 张参考表被渲染为正文表格",
                suggestion="从装配稿删除该表；参考数据改用文字行（保留「写作参考」字样供断言器拦截）",
            )
        )

    full_text = "\n".join(b.text for b in blocks if b.kind == "p")
    # 表格单元格文本并入占位符扫描（表内【待补充】也必须 P0 阻塞；
    # 原实现只扫段落，审计基本信息表/设备表内的占位符必然漏检）
    _cell_texts: List[str] = []
    for b in blocks:
        if b.kind != "tbl":
            continue
        try:
            for row in b.obj.rows:
                for cell in row.cells:
                    _cell_texts.append(cell.text)
        except Exception:
            continue
    if _cell_texts:
        full_text = full_text + "\n" + "\n".join(_cell_texts)

    # 占位符按"每段/每单元格"逐个归属，区分"已登记的数据缺失"与"真漏填"
    scan_texts: List[str] = [b.text for b in blocks if b.kind == "p" and b.text] + _cell_texts
    registered_keywords: List[str] = []
    for item in registry:
        for key in ("field", "label", "location"):
            value = str(item.get(key) or "").strip()
            if value:
                registered_keywords.append(value)

    for token, label in PLACEHOLDERS:
        hits = [text for text in scan_texts if token in text]
        if not hits:
            continue
        registered = [
            text for text in hits
            if any(keyword in text for keyword in registered_keywords)
        ]
        unregistered = [text for text in hits if text not in registered]
        if unregistered:
            findings.append(
                Finding(
                    code="V3.STRUCT.PLACEHOLDER",
                    category="章节完整性",
                    severity=SEV_P0,
                    title=f"残留{label} {len(unregistered)} 处",
                    detail=f"标记='{token}'",
                    expected="0 处",
                    actual=f"{len(unregistered)} 处",
                    suggestion="补齐对应数据或删除占位段落后重新生成",
                )
            )
        if registered:
            findings.append(
                Finding(
                    code="V3.STRUCT.PLACEHOLDER_REGISTERED",
                    category="章节完整性",
                    severity=SEV_P1,
                    title=f"已登记的数据缺失占位 {len(registered)} 处（不阻塞交付）",
                    detail=(
                        f"标记='{token}'；已在 {MISSING_REGISTRY_FILE} 登记："
                        + "、".join(
                            str(item.get("label") or item.get("field") or "?")
                            for item in registry
                        )
                    ),
                    expected="报告中如实说明数据缺失，并告知用户补录",
                    actual=f"{len(registered)} 处占位（已登记）",
                    suggestion="按已登记缺失项处理：保留占位、交付时说明；补录数据后重算重出",
                )
            )

    missing_tables = [name for name in REQUIRED_TABLES if name not in full_text]
    if missing_tables:
        findings.append(
            Finding(
                code="V3.STRUCT.REQUIRED_TABLE",
                category="章节完整性",
                severity=SEV_P1,
                title=f"缺必备表：{'、'.join(missing_tables)}",
                location="审计基本信息",
                suggestion="补齐审计机构信息表/审计组人员名单/配合人员名单",
            )
        )
    return findings


# ================================================================
#  格式规范
# ================================================================

@dataclass
class Violation:
    """格式违规累加器（内部可变，仅用于统计，不对外暴露）。"""

    label: str
    expected: str
    samples: List[str] = field(default_factory=list)
    count: int = 0

    def add(self, sample: str) -> None:
        self.count += 1
        if len(self.samples) < FORMAT_SAMPLE_LIMIT:
            self.samples.append(sample)


def _east_asia_font(run: Any) -> Optional[str]:
    from docx.oxml.ns import qn

    properties = run._element.rPr
    if properties is None or properties.rFonts is None:
        return None
    return properties.rFonts.get(qn("w:eastAsia"))


def _paragraph_font(paragraph: Any) -> Tuple[Optional[str], Optional[float], Optional[bool]]:
    """取首个非空 run 的显式字体设置。None 表示继承样式，不判违规。"""
    for run in paragraph.runs:
        if not run.text.strip():
            continue
        name = _east_asia_font(run) or run.font.name
        size = run.font.size.pt if run.font.size is not None else None
        return name, size, run.font.bold
    return None, None, None


def _classify(text: str) -> str:
    if _chapter_number(text):
        return "h1"
    if RE_H3.match(text):
        return "h3"
    if RE_H2.match(text):
        return "h2"
    if RE_CAPTION.match(text.strip()):
        return "caption"
    return "body" if len(text) >= BODY_MIN_CHARS else "skip"


def check_format(blocks: Sequence[Block]) -> List[Finding]:
    specs = {
        "h1": FMT_H1,
        "h2": FMT_H2,
        "h3": FMT_H3,
        "body": FMT_BODY,
        "caption": FMT_CAPTION,
    }
    violations: Dict[str, Violation] = {}

    def record(key: str, label: str, expected: str, sample: str) -> None:
        violations.setdefault(key, Violation(label, expected)).add(sample)

    for block in blocks:
        if block.kind != "p" or not block.text:
            continue
        kind = _classify(block.text)
        if kind == "skip":
            continue
        spec = specs[kind]
        kind_label = KIND_LABELS.get(kind, kind)
        excerpt = block.text[:24]
        name, size, bold = _paragraph_font(block.obj)

        if spec.get("font") and name is not None and name != spec["font"]:
            record(f"{kind}.font", f"{kind_label} 中文字体", str(spec["font"]), f"{excerpt} → {name}")
        if spec.get("size") and size is not None and abs(size - float(spec["size"])) > 0.51:
            record(f"{kind}.size", f"{kind_label} 字号", f"{spec['size']}pt", f"{excerpt} → {size}pt")
        if spec.get("bold") and bold is False:
            record(f"{kind}.bold", f"{kind_label} 加粗", "加粗", excerpt)

        paragraph_format = block.obj.paragraph_format
        alignment = paragraph_format.alignment
        if alignment is not None and int(alignment) != int(spec["align"]):
            record(
                f"{kind}.align",
                f"{kind_label} 对齐",
                str(spec["align"]),
                f"{excerpt} → {int(alignment)}",
            )

        if kind == "body":
            spacing = paragraph_format.line_spacing
            if spacing is not None and abs(float(spacing) - FMT_BODY["line_spacing"]) > 0.05:
                record("body.spacing", "正文行距", "1.5 倍", f"{excerpt} → {spacing}")
            indent = paragraph_format.first_line_indent
            if indent is not None and abs(indent.pt - FMT_BODY["indent_pt"]) > 2.0:
                record(
                    "body.indent",
                    "正文首行缩进",
                    "2 字符（24pt）",
                    f"{excerpt} → {indent.pt:.1f}pt",
                )

    bad_rows = 0
    total_rows = 0
    for block_index, block in enumerate(blocks):
        if block.kind != "tbl":
            continue
        if is_appendix2_table(blocks, block_index):
            continue
        for row in block.obj.rows:
            total_rows += 1
            height = row.height
            if height is None or abs(int(height) - TABLE_ROW_HEIGHT_EMU) > TABLE_ROW_HEIGHT_TOL:
                bad_rows += 1
    if total_rows and bad_rows:
        record(
            "table.row_height",
            "表格行高",
            "1.01cm 固定行高",
            f"{bad_rows}/{total_rows} 行未设定或不符",
        )

    return [
        Finding(
            code=f"V3.FORMAT.{key.upper().replace('.', '_')}",
            category="格式规范",
            severity=SEV_P2,
            title=f"{violation.label}不符规范（{violation.count} 处）",
            detail="; ".join(violation.samples),
            expected=violation.expected,
            actual=f"{violation.count} 处偏离",
            suggestion="对齐 format_spec.FormatSpec 重新生成，勿手工改样式",
        )
        for key, violation in sorted(violations.items())
    ]


# ================================================================
#  报告定位
# ================================================================

def locate_report(
    project: str, report: Optional[str] = None, output_dir: Optional[str] = None
) -> Tuple[Optional[Path], str]:
    if report:
        path = Path(report).expanduser()
        return (path, "") if path.is_file() else (None, f"报告文件不存在: {path}")

    search_dirs = [project_dir(project, output_dir), Path.cwd()]
    candidates: List[Path] = []
    for directory in search_dirs:
        if directory.is_dir():
            candidates += [
                p for p in directory.glob("*.docx") if not p.name.startswith("~$")
            ]
    if not candidates:
        return None, (
            "未找到 .docx 报告。用 --report <路径> 显式指定，"
            f"或把报告放到 {search_dirs[0]}"
        )
    preferred = [p for p in candidates if "能源审计报告" in p.name] or candidates
    return max(preferred, key=lambda p: p.stat().st_mtime), ""


# ================================================================
#  主流程
# ================================================================

def load_missing_registry(
    project: str, output_dir: Optional[str] = None
) -> List[Dict[str, str]]:
    """读 <项目>/missing_items.json（可选）。缺失返回空列表 → 占位符一律按 P0 处理。"""
    path = project_dir(project, output_dir) / MISSING_REGISTRY_FILE
    data = read_json(path)
    items = data.get("items") if isinstance(data, dict) else None
    out: List[Dict[str, str]] = []
    for item in items or []:
        if isinstance(item, dict):
            out.append({str(k): str(v) for k, v in item.items() if v is not None})
    return out

def check_attribution_layering(project: str) -> List[Finding]:
    """5.2「归因下沉」律 1 —— 总量图注后第一段不得含归因词（2026-09-29 接入自动闸门）。

    此前该检查只能手动跑：`ea-validation/scripts/check_attribution_layering.py` 的 docstring 自述
    "建议性检查，尚未接入 datava REPORT_REVIEW 的 P0/P1 闸门"。实测漏检事故：烟台法院报告的
    5.2.1「…可能得益于节能改造…」与 5.2.2「…与节水管理措施…有关」两处越级归因，直到交付前人工核对才发现。

    判据与定位**完全复用**该脚本（结构定位：总量图注 → 紧随其后的第一段；费用节跳过；
    "提请核实"语境豁免）。严重级别 **P1（待修，不阻塞交付）**：它是明确的规则违反（rules.md 律 1），
    但不改变数据结论，故不设 P0。
    """
    try:
        _scripts_dir = str(Path(__file__).resolve().parents[1])   # …/ea-validation/scripts
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        from check_attribution_layering import resolve_source, scan  # type: ignore
    except Exception as exc:  # noqa: BLE001 —— 检查器不可用不得让整轮审查失败
        return [Finding(
            code="V3.CH5.ATTRIB_CHECKER_UNAVAILABLE",
            category="写作规范",
            severity=SEV_P2,
            title="5.2 归因下沉检查未能执行",
            detail=f"无法加载 check_attribution_layering：{exc}",
            suggestion="确认 ea-validation/scripts/check_attribution_layering.py 存在且可导入",
        )]

    src = Path(resolve_source(project or "", ""))
    if not src.is_file():
        return []
    try:
        hits, _checked = scan(src.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception as exc:  # noqa: BLE001
        return [Finding(
            code="V3.CH5.ATTRIB_CHECKER_UNAVAILABLE",
            category="写作规范",
            severity=SEV_P2,
            title="5.2 归因下沉检查未能执行",
            detail=f"扫描 {src.name} 失败：{exc}",
            suggestion="确认第5章装配稿编码正常（UTF-8）",
        )]

    out: List[Finding] = []
    for h in hits:
        words = "、".join(h.get("words") or [])
        out.append(Finding(
            code="V3.CH5.ATTRIB_LAYERING",
            category="写作规范",
            severity=SEV_P1,
            title=f"5.2 越级归因（归因下沉律 1）：{h.get('section', '')}",
            detail=f"{src.name} 第 {h.get('line')} 行命中归因词「{words}」；原文："
                   f"{str(h.get('text') or '')[:120]}",
            location=f"第5章 {h.get('section', '')}",
            expected="总量图注之后那一段只写增量 / 增减率 / 波动区间 / 极值",
            actual=f"出现归因词「{words}」",
            suggestion="把归因移到该品种的逐月段（图5.N+1 之后），只挂设备形式或现场事件；"
                       "挂不上改写「成因待核实」（rules.md《归因下沉三律》律 1）",
        ))
    return out


def run(
    project: str,
    *,
    report: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> ReviewResult:
    try:
        from docx import Document
    except ImportError as exc:
        return build_result(MODE, project, [], error=f"python-docx 不可用: {exc}")

    path, error = locate_report(project, report, output_dir)
    if error or path is None:
        return build_result(MODE, project, [], error=error or "报告定位失败")

    try:
        document = Document(str(path))
        blocks = parse_blocks(document)
    except Exception as exc:  # noqa: BLE001 — docx 解析异常形态多样，统一降级
        return build_result(MODE, project, [], error=f"报告解析失败 ({path.name}): {exc}")

    raw = read_json(project_data_path(project))
    base = (raw or {}).get("base") or {}
    truth_area = safe_float(base.get("building_area"))
    buildings = [b for b in ((raw or {}).get("buildings") or []) if isinstance(b, dict)]
    garage_area = sum(safe_float(b.get("garage_area")) for b in buildings)
    unit_areas = [safe_float(b.get("area")) for b in buildings]
    years = sorted(
        int(safe_float(row.get("year")))
        for row in ((raw or {}).get("energy_yearly") or [])
        if safe_float(row.get("year")) > 0
    )
    heat_pay_type = str(
        ((raw or {}).get("metering") or {}).get("heat_pay_type") or ""
    ).strip()

    findings: List[Finding] = []
    registry = load_missing_registry(project, output_dir)
    findings += check_cover_consistency(blocks, base)
    findings += check_chapters(blocks)
    findings += check_heating_billing_semantics(blocks, heat_pay_type)
    findings += check_tables_and_placeholders(blocks, registry)
    findings += check_province_rules(blocks)
    findings += check_chapter6_structure(
        blocks,
        public_institution=str(base.get("unit_type", "")).strip() == "公共机构",
        equipment=((raw or {}).get("equipment") or []),
        images=((raw or {}).get("images") or []),
    )
    findings += check_chapter5_figures(blocks)
    findings += check_chapter7_structure(
        blocks,
        metering_classes=chapter7_metering_classes(raw),
    )
    findings += check_chapter7_711_metering_semantics(blocks)
    findings += check_chapter8_summary(blocks)
    findings += check_ch5_narrative(blocks)
    # 5.2 归因下沉（律 1）——2026-09-29 由"手动建议性检查"升级为 V3 自动闸门项（P1，不阻塞）
    findings += check_attribution_layering(project)
    findings += check_building_tables(blocks)
    findings += check_area_consistency(extract_areas(blocks), truth_area, garage_area, unit_areas)
    findings += check_energy_consistency(blocks)
    if years:
        findings += check_year_coverage(blocks, years)
    findings += check_format(blocks)

    result = build_result(
        MODE,
        project,
        findings,
        inputs={
            "报告": str(path),
            "data.json": "已读取" if raw else "缺失（跳过与数据源比对）",
            "missing_items.json": (
                f"已登记 {len(registry)} 项缺失（占位按 P1 放行）" if registry
                else "未提供（占位一律按 P0 阻塞）"
            ),
        },
        extra={
            "paragraphs": sum(1 for b in blocks if b.kind == "p"),
            "tables": sum(1 for b in blocks if b.kind == "tbl"),
            "chapters": sorted({b.chapter for b in blocks if b.chapter}),
            "audit_years": years,
            "missing_registry": len(registry),
        },
    )

    save_dir = project_dir(project, output_dir)
    review_path = Path(write_json(save_dir / "report_review.json", result.to_dict()))
    result = with_artifacts(result, {"report_review.json": str(review_path)})
    result = with_artifacts(
        result,
        {
            "report_review.txt": write_text(
                save_dir / "report_review.txt", result.render_text()
            )
        },
    )
    write_json(review_path, result.to_dict())
    return result
