"""V2 INDICATOR_REVIEW — 指标计算后审查。

三条主线：
    年际对比    逐年指标变化超阈值 → 要求排查/说明
    对标合理性  标准名 / 三值序关系 / 评价文字 三方一致性复核
    数据一致性  面积、人数、床位、供暖电排除的口径校验

产出：indicator_review.json + indicator_review.txt
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .common import (
    SEV_P0,
    SEV_P1,
    SEV_P2,
    Finding,
    ReviewResult,
    build_result,
    fmt_num,
    pct_change,
    project_data_path,
    project_dir,
    projects_root,
    read_json,
    safe_float,
    with_artifacts,
    write_json,
    write_text,
)

MODE = "INDICATOR_REVIEW"

YOY_INFO_PCT = 15.0
YOY_WARN_PCT = 30.0
YOY_BLOCK_PCT = 50.0
AREA_TOLERANCE_PCT = 5.0

# 机构类型 → 定额标准名应含的关键词（与 resolve_benchmark 的校验保持一致）
STANDARD_KEYWORDS: Dict[str, str] = {
    "medical": "医疗机构",
    "government": "党政机关",
    "education": "教育机构",
}

# 用水类指标的标准名应含的标志词
WATER_STANDARD_TOKENS: Tuple[str, ...] = ("用水", "水定额", "取水", "4452")

# 集中供暖省份（用于判断供暖用能是否应当单独拆分）
HEATING_PROVINCES: Tuple[str, ...] = (
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "山东", "河南", "陕西", "甘肃", "青海", "宁夏", "新疆", "西藏",
)

# 指标合理量级（超出多为面积/人数口径错误，而非真实能耗水平）
PLAUSIBLE_RANGE: Dict[str, Tuple[float, float]] = {
    "kgce_per_m2": (3.0, 200.0),
    "kwh_per_m2": (10.0, 400.0),
    "kgce_per_person": (50.0, 8000.0),
    "L_per_bed_day": (50.0, 2000.0),
    "m3_per_person": (1.0, 300.0),
}


@dataclass(frozen=True)
class MetricSpec:
    key: str  # indicators['yearly'][i] 中的键
    label: str
    value_fields: Tuple[str, ...]  # 按优先级取第一个存在的字段
    unit: str
    kind: str  # 'energy' | 'water'


METRIC_SPECS: Tuple[MetricSpec, ...] = (
    MetricSpec("unit_area_non_heating", "单位面积非供暖能耗", ("kgce_per_m2",), "kgce/(m²·a)", "energy"),
    MetricSpec("unit_area_electricity", "单位面积常规电耗", ("kwh_per_m2",), "kWh/(m²·a)", "energy"),
    MetricSpec("per_capita_energy", "人均综合能耗", ("kgce_per_person",), "kgce/(人·a)", "energy"),
    MetricSpec(
        "water_indicator",
        "取水指标（医院=床日/机关教育=人均/场馆=面积）",
        ("L_per_bed_day", "m3_per_person", "m3_per_area"),
        "L/(床·d) 或 m³/(人·a) 或 m³/(m²·a)",
        "water",
    ),
)


# ================================================================
#  输入加载
# ================================================================

def _infer_institution_type(quota: dict) -> str:
    """从 by_year 定额标准名推断机构类型。

    只看能耗标准名（机构类型权威来源）；水标准名如
    「山东省教育、卫生等服务业用水定额」是行业分类名，含"教育/卫生"字样，
    不能作为机构类型依据。
    """
    text = str(quota.get("能耗") or "")
    if "医疗" in text:
        return "medical"
    if "教育" in text:
        return "education"
    return "government"


def _water_field_of(row: dict) -> Optional[str]:
    """by_year 行内取水字段名（机关/教育=人均取水量，医疗=床日用水量，场馆=单位面积取水量）。"""
    for key in row:
        if "评价" in key:
            continue
        if "取水" in key or "用水" in key:
            return key
    return None


def _water_value_field(field_name: str) -> str:
    if "床日" in field_name or "L_bed" in field_name or "bed" in field_name.lower():
        return "L_per_bed_day"
    if "面积" in field_name or "m3_m2" in field_name or "m2" in field_name:
        return "m3_per_area"
    return "m3_per_person"


def _water_quota_key(quota: dict) -> Optional[str]:
    """定额标准里存用水两档数值的键（排除标准名字符串键）。

    「用水」键存的是标准名（str），真正的两档数组在如
    「机关用水先进通用」这类键（list 值）里。
    """
    for key, value in quota.items():
        if isinstance(value, (list, tuple)) and ("用水" in key or "取水" in key):
            return key
    return None


def adapt_by_year(payload: dict) -> dict:
    """caliber by_year schema → 模块 yearly[] schema 适配。

    caliber 重建管线产出扁平结构：
      顶层 定额标准.{能耗, 用水, 非供暖三档_约束基准引导, 电耗三档, 人均综合能耗三档,
                     机关用水先进通用: [先进, 通用], ...}
      顶层 口径.{建筑面积_m2, 用能人数, 床位数, ...}
      by_year[i] = {year, 单位建筑面积非供暖能耗_kgce_m2a, 评价_非供暖,
                    常规电耗_kWh_m2a, 评价_电耗, 人均综合能耗_kgce_pa, 评价_人均,
                    人均机关取水量_m3_pa, 评价_取水, ...}

    适配要点：
      - 能源指标三档 [约束, 基准, 引导] 位置语义与模块一致，直接映射；
      - 用水定额只有两档 (先进值, 通用值) 且先进 < 通用，按语义还原后
        放入 约束值=通用值、基准值=先进值，避免 WATER_SEMANTICS 误报；
      - 标准名 / 评价文字一并映射，供对标一致性与评价复核沿用。
    """
    quota = payload.get("定额标准") or {}
    caliber_koujing = payload.get("口径") or {}
    standard_energy = str(quota.get("能耗") or "")
    standard_water = str(quota.get("用水") or "")
    institution_type = _infer_institution_type(quota)

    triple_map = (
        ("unit_area_non_heating", "非供暖三档_约束基准引导"),
        ("unit_area_electricity", "电耗三档"),
        ("per_capita_energy", "人均综合能耗三档"),
    )
    energy_field_map = (
        ("unit_area_non_heating", "单位建筑面积非供暖能耗_kgce_m2a", "kgce_per_m2", "评价_非供暖"),
        ("unit_area_electricity", "常规电耗_kWh_m2a", "kwh_per_m2", "评价_电耗"),
        ("per_capita_energy", "人均综合能耗_kgce_pa", "kgce_per_person", "评价_人均"),
    )

    yearly: List[dict] = []
    for row in payload.get("by_year") or []:
        if not isinstance(row, dict):
            continue
        year = row.get("year")
        item: Dict[str, Any] = {"year": year}
        for key, raw_field, value_field, eval_field in energy_field_map:
            triple = quota.get(dict(triple_map)[key]) or []
            benchmark = {
                "约束值": triple[0] if len(triple) > 0 else 0,
                "基准值": triple[1] if len(triple) > 1 else 0,
                "引导值": triple[2] if len(triple) > 2 else 0,
                "标准": standard_energy,
                "来源": "by_year适配",
                "评价结果": str(row.get(eval_field) or ""),
            }
            item[key] = {value_field: row.get(raw_field), "benchmark": benchmark}

        water_field = _water_field_of(row)
        water_quota_key = _water_quota_key(quota)
        if water_field:
            quota_pair = list(quota.get(water_quota_key) or []) if water_quota_key else []
            advanced = quota_pair[0] if len(quota_pair) > 0 else 0
            general = quota_pair[1] if len(quota_pair) > 1 else 0
            water_benchmark = {
                # 用水两档语义：先进值(严) < 通用值(宽)；按模块口径放 约束=通用、基准=先进
                "约束值": general,
                "基准值": advanced,
                "引导值": 0,
                "标准": standard_water,
                "来源": "by_year适配",
                "评价结果": str(row.get("评价_取水") or ""),
            }
            item["water_indicator"] = {
                _water_value_field(water_field): row.get(water_field),
                "benchmark": water_benchmark,
            }
        yearly.append(item)

    return {
        "project": payload.get("project") or "",
        "institution_type": institution_type,
        "building_area": caliber_koujing.get("建筑面积_m2"),
        "people_count": caliber_koujing.get("用能人数"),
        "beds_count": caliber_koujing.get("床位数") or 0,
        "yearly": yearly,
        "status": "ok",
        "_adapter_note": "caliber by_year schema 适配映射（定额标准→三值，评价文字→benchmark.评价结果）",
    }


def load_indicators(
    project: str, output_dir: Optional[str] = None
) -> Tuple[Optional[dict], str, str]:
    """加载指标。返回 (indicators, 来源说明, 错误)。

    优先级：
      1. indicators.json 的 yearly[]（模块原生 schema）
      2. indicators.json 的 by_year（caliber 重建 schema，适配映射；存在时
         不再回落 data.json 内嵌——内嵌块可能是重建前旧口径残留，见 P1 先例）
      3. data.json 的 indicators 字段（旧口径兼容）
      4. compute_project_indicators 现算
    """
    candidate_dirs = (
        projects_root() / project,           # 项目根目录（老布局）
        projects_root() / project / "data",  # caliber 实际输出目录
    )
    payload = None
    payload_path = None
    for base in candidate_dirs:
        cand = base / "indicators.json"
        data = read_json(cand)
        if isinstance(data, dict):
            payload, payload_path = data, cand
            break
    if isinstance(payload, dict):
        if payload.get("yearly"):
            return payload, f"indicators.json ({payload_path})", ""
        if payload.get("by_year"):
            adapted = adapt_by_year(payload)
            return adapted, f"indicators.json ({payload_path}) (caliber by_year schema, adapter 映射)", ""

    raw = read_json(project_data_path(project))
    if isinstance(raw, dict):
        embedded = raw.get("indicators") or {}
        if embedded.get("yearly"):
            return embedded, "data.json → indicators", ""

    try:
        from tools.energy_audit.indicators import compute_project_indicators
        from tools.energy_audit.project_data import load_project
    except ImportError as exc:
        return None, "", f"indicators.json 不存在且依赖导入失败: {exc}"

    proj = load_project(project)
    if proj is None:
        return None, "", f"项目 '{project}' 的 data.json 不存在，无法计算指标"
    return compute_project_indicators(proj), "compute_project_indicators() 现算", ""


def metric_value(metric: dict, spec: MetricSpec) -> Tuple[str, Optional[float]]:
    """按优先级取指标数值，返回 (字段名, 值)。取不到返回 ('', None)。"""
    for field_name in spec.value_fields:
        if field_name in metric:
            return field_name, safe_float(metric.get(field_name))
    return "", None


# ================================================================
#  对标一致性（纯函数）
# ================================================================

def expected_energy_evaluation(value: float, benchmark: dict) -> str:
    if value <= safe_float(benchmark.get("引导值")):
        return "低于引导值（先进水平）"
    if value <= safe_float(benchmark.get("基准值")):
        return "低于基准值（合理水平）"
    if value <= safe_float(benchmark.get("约束值")):
        return "低于约束值（达标）"
    return "高于约束值（需整改）"


def water_thresholds(benchmark: dict) -> Tuple[float, float]:
    """用水定额三值按语义还原为 (先进值, 通用值)。

    _DEFAULT_BENCHMARKS 中用水定额存为 (先进值, 通用值, 0)，
    经 resolve_benchmark 位置映射后落进 (约束值, 基准值, 引导值)，字段名与语义错位。
    这里按数值大小还原：非零最小值=先进值，最大值=通用值。
    """
    values = [
        safe_float(benchmark.get(key))
        for key in ("约束值", "基准值", "引导值")
    ]
    positives = [v for v in values if v > 0]
    if not positives:
        return 0.0, 0.0
    return min(positives), max(positives)


def expected_water_evaluation(value: float, benchmark: dict) -> str:
    advanced, general = water_thresholds(benchmark)
    if general <= 0:
        return "暂无定额标准可对标"
    if value <= advanced:
        return "低于先进值"
    if value <= general:
        return "低于通用值"
    return "高于通用值（需整改）"


def check_benchmark_structure(
    spec: MetricSpec, benchmark: dict, institution_type: str
) -> List[Finding]:
    """定额本身的结构性检查：三值序关系 + 标准名 + 来源。

    定额逐年相同，故按指标检查一次，避免逐年重复刷屏。
    """
    location = spec.label
    triple = {key: safe_float(benchmark.get(key)) for key in ("约束值", "基准值", "引导值")}
    standard = str(benchmark.get("标准") or "")
    source = str(benchmark.get("来源") or "")
    findings: List[Finding] = []

    if not any(triple.values()):
        return [
            Finding(
                code="V2.BENCH.NO_QUOTA",
                category="对标合理性",
                severity=SEV_P1,
                title=f"{spec.label} 无定额可对标",
                detail=f"约束/基准/引导三值全为 0，标准='{standard or '未给出'}'",
                location=location,
                suggestion="补录 ts_limit_config 或以省级定额标准人工核定，报告中不得给出对标结论",
            )
        ]

    # 1) 三值序关系
    if spec.kind == "energy":
        if not (triple["约束值"] >= triple["基准值"] >= triple["引导值"] > 0):
            findings.append(
                Finding(
                    code="V2.BENCH.ORDER",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"{spec.label} 定额三值序关系颠倒",
                    detail=f"标准='{standard}' 来源={source}",
                    location=location,
                    expected="约束值 ≥ 基准值 ≥ 引导值 > 0",
                    actual=f"约束值 {fmt_num(triple['约束值'])} / 基准值 "
                    f"{fmt_num(triple['基准值'])} / 引导值 {fmt_num(triple['引导值'])}",
                    suggestion="核对 ts_limit_config 的 value1/value2/value3 列序或人工传入定额",
                )
            )
    elif triple["约束值"] < triple["基准值"]:
        advanced, general = water_thresholds(benchmark)
        findings.append(
            Finding(
                code="V2.BENCH.WATER_SEMANTICS",
                category="对标合理性",
                severity=SEV_P0,
                title=f"{spec.label} 用水定额字段语义错位",
                detail=(
                    f"用水定额本为(先进值, 通用值)，被按(约束值, 基准值)位置映射；"
                    f"按数值还原：先进值 {fmt_num(advanced)}、通用值 {fmt_num(general)}"
                ),
                location=location,
                expected="约束值(通用值) ≥ 基准值",
                actual=f"约束值 {fmt_num(triple['约束值'])} < 基准值 {fmt_num(triple['基准值'])}",
                suggestion="修正 indicators._DEFAULT_BENCHMARKS 的用水三元组顺序，或在报告中按先进值/通用值口径表述",
            )
        )

    # 2) 标准名与机构类型
    keyword = STANDARD_KEYWORDS.get(institution_type, "")
    if spec.kind == "water" and standard and not any(
        token in standard for token in WATER_STANDARD_TOKENS
    ):
        findings.append(
            Finding(
                code="V2.BENCH.WATER_STANDARD_NAME",
                category="对标合理性",
                severity=SEV_P1,
                title=f"{spec.label} 引用了非用水类定额标准名",
                location=location,
                expected="用水定额标准（如 DB37/T 4452-2021）",
                actual=f"标准名='{standard}'",
                suggestion="修正 resolve_benchmark 对用水指标返回 water_standard，报告中勿标错标准号",
            )
        )

    if source == "DB" and keyword and keyword not in standard and "用水" not in standard:
        findings.append(
            Finding(
                code="V2.BENCH.STANDARD_MISMATCH",
                category="对标合理性",
                severity=SEV_P0,
                title=f"{spec.label} 定额标准与机构类型不匹配",
                location=location,
                expected=f"标准名含「{keyword}」",
                actual=f"标准名='{standard}'",
                suggestion="核对 ts_limit_config.field_type 与机构类别映射，避免用错类别定额",
            )
        )
    elif source in ("Default", "User"):
        findings.append(
            Finding(
                code="V2.BENCH.SOURCE_FALLBACK",
                category="对标合理性",
                severity=SEV_P2,
                title=f"{spec.label} 定额来自{'内置默认' if source == 'Default' else '用户输入'}",
                detail=f"标准='{standard}'（三级兜底 Layer {'3' if source == 'Default' else '2'}）",
                location=location,
                suggestion="报告中注明定额来源；如需权威值请 web_search 核验省级规章后人工确认",
            )
        )
    return findings


def check_evaluation(year: int, spec: MetricSpec, value: float, benchmark: dict) -> List[Finding]:
    """评价文字与实际值的一致性复核（逐年）。"""
    recorded = str(benchmark.get("评价结果") or "")
    if not recorded:
        return []
    triple = [safe_float(benchmark.get(key)) for key in ("约束值", "基准值", "引导值")]
    if not any(triple):
        return []

    expected = (
        expected_energy_evaluation(value, benchmark)
        if spec.kind == "energy"
        else expected_water_evaluation(value, benchmark)
    )
    if recorded == expected:
        return []
    return [
        Finding(
            code="V2.BENCH.EVAL_MISMATCH",
            category="对标合理性",
            severity=SEV_P0,
            title=f"{spec.label} 评价结论与实际值不符",
            detail=f"实际值 {fmt_num(value)} {spec.unit}，标准='{benchmark.get('标准', '')}'",
            location=f"{year}年 · {spec.label}",
            expected=expected,
            actual=recorded,
            suggestion="以复核结论为准修正指标表与第5章评价文字，勿直接沿用计算函数输出",
        )
    ]


def check_plausibility(year: int, spec: MetricSpec, field_name: str, value: float) -> List[Finding]:
    low, high = PLAUSIBLE_RANGE.get(field_name, (0.0, float("inf")))
    if low <= value <= high:
        return []
    return [
        Finding(
            code="V2.PLAUSIBLE.OUT_OF_RANGE",
            category="数据一致性",
            severity=SEV_P0,
            title=f"{spec.label} 数值超出合理量级",
            detail="该量级偏差通常源于建筑面积/用能人数口径错误，而非真实能耗水平",
            location=f"{year}年 · {spec.label}",
            expected=f"{fmt_num(low)} ~ {fmt_num(high)} {spec.unit}",
            actual=f"{fmt_num(value)} {spec.unit}",
            suggestion="核对分母（面积/人数/床位）与分子能耗的统计范围是否一致",
        )
    ]


# ================================================================
#  年际对比（纯函数）
# ================================================================

def _yoy_severity(change: float) -> Optional[str]:
    magnitude = abs(change)
    if magnitude >= YOY_BLOCK_PCT:
        return SEV_P0
    if magnitude >= YOY_WARN_PCT:
        return SEV_P1
    if magnitude >= YOY_INFO_PCT:
        return SEV_P2
    return None


def _row_metric(row: dict, spec) -> dict:
    """取年度行中某指标的 dict；water_indicator 兼容旧键 per_capita_water。"""
    metric = row.get(spec.key)
    if spec.key == "water_indicator" and not metric:
        metric = row.get("per_capita_water")  # 旧 indicators.json/data.json 兼容
    return metric or {}


def check_yoy(yearly: Sequence[dict]) -> List[Finding]:
    """逐年指标变化排查。"""
    findings: List[Finding] = []
    rows = sorted(yearly, key=lambda r: safe_float(r.get("year")))
    for spec in METRIC_SPECS:
        series: List[Tuple[int, str, float]] = []
        for row in rows:
            metric = _row_metric(row, spec)
            if metric.get("error"):
                continue
            field_name, value = metric_value(metric, spec)
            if value is None:
                continue
            series.append((int(safe_float(row.get("year"))), field_name, value))

        for (prev_year, _, prev_value), (year, _, value) in zip(series, series[1:]):
            change = pct_change(value, prev_value)
            if change is None:
                findings.append(
                    Finding(
                        code="V2.YOY.ZERO_BASE",
                        category="年际对比",
                        severity=SEV_P1,
                        title=f"{spec.label} {prev_year}年基数为 0，无法计算年际变化",
                        location=f"{prev_year}→{year}年 · {spec.label}",
                        actual=f"{prev_year}年 0 → {year}年 {fmt_num(value)}",
                        suggestion="补齐基准年数据，否则第5章年际趋势结论不成立",
                    )
                )
                continue
            severity = _yoy_severity(change)
            if severity is None:
                continue
            findings.append(
                Finding(
                    code="V2.YOY.CHANGE",
                    category="年际对比",
                    severity=severity,
                    title=f"{spec.label} {prev_year}→{year}年变化 {change:+.1f}%",
                    detail=f"{fmt_num(prev_value)} → {fmt_num(value)} {spec.unit}",
                    location=f"{prev_year}→{year}年 · {spec.label}",
                    expected=f"|变化| < {YOY_INFO_PCT:.0f}%",
                    actual=f"{change:+.1f}%",
                    suggestion=(
                        "先排除面积/人数/能耗录入错误，再在第5章说明原因"
                        if abs(change) >= YOY_WARN_PCT
                        else "在第5章补一句变化原因说明"
                    ),
                )
            )
    return findings


# ================================================================
#  数据一致性（纯函数，输入为 data.json 原始 dict）
# ================================================================

def check_consistency(indicators: dict, raw: Optional[dict]) -> List[Finding]:
    findings: List[Finding] = []
    institution_type = str(indicators.get("institution_type") or "")
    area = safe_float(indicators.get("building_area"))
    people = safe_float(indicators.get("people_count"))
    beds = safe_float(indicators.get("beds_count"))

    if area <= 0:
        findings.append(
            Finding(
                code="V2.CONSISTENCY.NO_AREA",
                category="数据一致性",
                severity=SEV_P0,
                title="建筑面积为 0，所有单位面积指标不成立",
                suggestion="补录 base.building_area 后重算指标",
            )
        )
    if people <= 0 and not (institution_type == "medical" and beds > 0):
        findings.append(
            Finding(
                code="V2.CONSISTENCY.NO_PEOPLE",
                category="数据一致性",
                severity=SEV_P0,
                title="用能人数为 0，人均指标不成立",
                suggestion="补录 base.people_count（医疗机构含在岗+编外+门诊折算+床位折算）",
            )
        )
    if institution_type == "medical" and beds <= 0:
        findings.append(
            Finding(
                code="V2.CONSISTENCY.NO_BEDS",
                category="数据一致性",
                severity=SEV_P1,
                title="医疗机构缺床位数，单位开放床日用水量降级为人均取水量",
                expected="beds_count > 0",
                actual=f"beds_count={fmt_num(beds, 0)}",
                suggestion="补录 base.beds_count 以对标 DB37/T 4452-2021 床日用水定额",
            )
        )

    if raw is None:
        return findings

    base = raw.get("base") or {}
    buildings = raw.get("buildings") or []

    raw_area = safe_float(base.get("building_area"))
    if raw_area > 0 and area > 0:
        deviation = abs(raw_area - area) / raw_area * 100.0
        if deviation > 0.5:
            findings.append(
                Finding(
                    code="V2.CONSISTENCY.AREA_SOURCE_MISMATCH",
                    category="数据一致性",
                    severity=SEV_P0,
                    title="指标计算用面积与 data.json 面积不一致",
                    location="base.building_area vs indicators.building_area",
                    expected=f"{fmt_num(raw_area)} m²",
                    actual=f"{fmt_num(area)} m²",
                    suggestion="指标结果已过期，重算 compute_project_indicators 后再进入报告生成",
                )
            )

    building_sum = sum(safe_float(b.get("area")) for b in buildings)
    if buildings and building_sum > 0 and raw_area > 0:
        deviation = abs(building_sum - raw_area) / raw_area * 100.0
        if deviation > AREA_TOLERANCE_PCT:
            findings.append(
                Finding(
                    code="V2.CONSISTENCY.AREA_SUM",
                    category="数据一致性",
                    severity=SEV_P1,
                    title=f"单栋建筑面积合计与总建筑面积偏差 {deviation:.1f}%",
                    detail=f"{len(buildings)} 栋合计 {fmt_num(building_sum)} m²，总面积 {fmt_num(raw_area)} m²",
                    location="第2章 建筑概况",
                    expected=f"偏差 ≤ {AREA_TOLERANCE_PCT:.0f}%",
                    actual=f"{deviation:.1f}%",
                    suggestion="确认是否存在未列入清单的建筑，或总面积含非审计范围建筑",
                )
            )

    findings += check_heating_split(raw)
    return findings


def check_heating_split(raw: dict) -> List[Finding]:
    """供暖用能是否已从常规用能中拆分。

    EnergyYearly 未设供暖用电/供暖燃气字段，转换到 YearlyEnergyData 时
    heating_energy_kwh 恒为 0，即 非供暖电耗 == 总电耗。
    """
    base = raw.get("base") or {}
    province = str(base.get("province") or "")
    energy_yearly = raw.get("energy_yearly") or []
    if not energy_yearly:
        return []

    in_heating_zone = any(p in province for p in HEATING_PROVINCES)
    heat_years = [
        int(safe_float(row.get("year")))
        for row in energy_yearly
        if safe_float(row.get("heating_energy_heat_gj")) > 0
    ]

    if in_heating_zone and not heat_years:
        return [
            Finding(
                code="V2.CONSISTENCY.HEATING_NOT_SPLIT",
                category="数据一致性",
                severity=SEV_P1,
                title="供暖能耗为 0 且供暖用电未拆分，非供暖类指标被高估",
                detail=(
                    f"省份='{province}'（集中供暖区）但各年 heating_energy_heat_gj 均为 0；"
                    "EnergyYearly 无供暖用电字段，非供暖电耗 = 总电耗"
                ),
                location="能耗数据 · 供暖口径",
                expected="供暖能耗单独计量并从总电耗中剔除",
                actual="供暖能耗 0 GJ，供暖用电 0 kWh",
                suggestion="补录外购热量或供暖用电拆分；无法拆分时须在第5章注明口径",
            )
        ]

    if heat_years:
        return [
            Finding(
                code="V2.CONSISTENCY.HEATING_PUMP_ELEC",
                category="数据一致性",
                severity=SEV_P2,
                title="供暖循环泵电耗未从总电耗中剔除",
                detail=f"{heat_years} 年有外购热量，但数据模型无供暖用电字段",
                location="能耗数据 · 供暖口径",
                suggestion="如有分项计量请拆出供暖用电；否则在第5章注明常规用能系统电耗含供暖辅机",
            )
        ]
    return []


# ================================================================
#  主流程
# ================================================================

def run(project: str, *, output_dir: Optional[str] = None) -> ReviewResult:
    indicators, source, error = load_indicators(project, output_dir)
    if error or indicators is None:
        return build_result(MODE, project, [], error=error or "指标加载失败")

    if indicators.get("status") != "ok":
        return build_result(
            MODE,
            project,
            [
                Finding(
                    code="V2.STATUS.PENDING",
                    category="数据一致性",
                    severity=SEV_P0,
                    title="指标计算未完成，无法审查",
                    detail=str(indicators.get("reason") or ""),
                    suggestion="补齐必要参数后重跑指标计算",
                )
            ],
            inputs={"来源": source},
        )

    raw = read_json(project_data_path(project))
    institution_type = str(indicators.get("institution_type") or "government")
    yearly = indicators.get("yearly") or []

    findings: List[Finding] = list(check_consistency(indicators, raw if isinstance(raw, dict) else None))
    findings += check_yoy(yearly)

    seen_benchmarks: Dict[str, dict] = {}
    for row in sorted(yearly, key=lambda r: safe_float(r.get("year"))):
        year = int(safe_float(row.get("year")))
        for spec in METRIC_SPECS:
            metric = _row_metric(row, spec)
            if metric.get("error"):
                findings.append(
                    Finding(
                        code="V2.METRIC.ERROR",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{spec.label} 计算失败",
                        detail=str(metric.get("error")),
                        location=f"{year}年 · {spec.label}",
                        suggestion="修正输入参数后重算指标",
                    )
                )
                continue
            field_name, value = metric_value(metric, spec)
            if value is None:
                continue
            findings += check_plausibility(year, spec, field_name, value)

            benchmark = metric.get("benchmark") or {}
            if not benchmark:
                continue
            if spec.key not in seen_benchmarks:
                seen_benchmarks[spec.key] = benchmark
                findings += check_benchmark_structure(spec, benchmark, institution_type)
            findings += check_evaluation(year, spec, value, benchmark)

    result = build_result(
        MODE,
        project,
        findings,
        inputs={
            "指标来源": source,
            "data.json": "已读取" if isinstance(raw, dict) else "缺失（跳过口径校验）",
        },
        extra={
            "institution_type": institution_type,
            "institution_category": indicators.get("institution_category", ""),
            "years": [int(safe_float(r.get("year"))) for r in yearly],
            "building_area": indicators.get("building_area"),
            "people_count": indicators.get("people_count"),
            "beds_count": indicators.get("beds_count"),
        },
    )

    save_dir = project_dir(project, output_dir)
    review_path = Path(write_json(save_dir / "indicator_review.json", result.to_dict()))
    result = with_artifacts(result, {"indicator_review.json": str(review_path)})
    result = with_artifacts(
        result,
        {
            "indicator_review.txt": write_text(
                save_dir / "indicator_review.txt", result.render_text()
            )
        },
    )
    write_json(review_path, result.to_dict())
    return result
