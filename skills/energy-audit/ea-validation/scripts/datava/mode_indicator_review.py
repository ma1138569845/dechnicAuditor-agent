"""V2 INDICATOR_REVIEW — 指标计算后审查。

三条主线：
    年际对比    逐年指标变化超阈值 → 要求排查/说明
    对标合理性  标准名 / 三值序关系 / 评价文字 三方一致性复核
    数据一致性  面积、人数、床位、供暖电排除的口径校验

产出：indicator_review.json + indicator_review.txt
"""

from __future__ import annotations

import json
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
    # 2026-09-05：供暖能耗低值不误报。混合供暖（空调+市政热力补充）医院热力占比小，
    # 数值低是真实场景；真正要抓的高异常仍由上限 200 拦截。低值缺量（费用有、用量无）
    # 由 V1.HEATING.COST_NO_USAGE 检查负责。
    "heating_kgce_per_m2": (0.0, 200.0),
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
    MetricSpec(
        "unit_area_heating",
        "单位采暖建筑面积供暖能耗",
        ("kgce_per_m2",),
        "kgce/(m²·a)",
        "energy",
    ),
)

# 浙江公共建筑指标的 V2 审查口径。键必须与
# ea-calculation/scripts/public_building_indicators.py 的输出一致。
PUBLIC_BUILDING_METRICS: Dict[str, Tuple[Tuple[str, str, str, str, str, str], ...]] = {
    "office": (
        ("unit_area_energy", "单位建筑面积能耗", "unit_area_energy", "kgce/m²", "three", "unit_area_energy"),
        ("unit_area_electricity", "常规用能系统单位建筑面积电耗", "unit_area_electricity", "kWh/m²", "three", "unit_area_electricity"),
        ("per_capita_energy", "人均综合能耗", "per_capita_energy", "kgce/人", "three", "per_capita_energy"),
        ("per_capita_electricity", "人均电耗", "per_capita_electricity", "kWh/人", "three", "per_capita_electricity"),
        ("unit_water", "单位用水量", "unit_water", "m³/(人·a)", "water", "unit_water"),
    ),
    "hotel": (
        ("unit_energy", "单位综合能耗", "unit_energy", "kgce/m²", "reference", "unit_energy"),
        ("unit_comparable_energy", "单位可比综合能耗", "unit_comparable_energy", "kgce/m²", "level", "unit_comparable_energy"),
        ("water_per_bed", "单位用水量", "water_per_bed", "m³/(床·年)", "water", "water"),
    ),
}

PUBLIC_BUILDING_TOP_METRICS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "office": (
        ("unit_area_non_heating_energy", "kgce_per_m2", "unit_area_energy"),
        ("unit_area_electricity", "kwh_per_m2", "unit_area_electricity"),
        ("per_capita_energy", "kgce_per_person", "per_capita_energy"),
        ("per_capita_electricity", "kwh_per_person", "per_capita_electricity"),
        ("water_indicator", "m3_per_person", "unit_water"),
    ),
    "hotel": (
        ("unit_energy", "kgce_per_m2", "unit_energy"),
        ("unit_comparable_energy", "kgce_per_m2", "unit_comparable_energy"),
        ("water_indicator", "m3_per_bed", "water_per_bed"),
    ),
}

# 山东公共建筑：只有二档，指标字段使用 eA/eB/eC 的明确语义名。
SHANDONG_PUBLIC_BUILDING_METRICS: Dict[str, Tuple[Tuple[str, str, str, str, str], ...]] = {
    "business_office": (
        ("unit_area_heating_energy", "单位建筑面积供暖能耗", "kgce_per_m2", "kgce/(m²·a)", "two"),
        ("unit_area_non_heating_electricity", "单位建筑面积非供暖电耗", "kwh_per_m2", "kWh/(m²·a)", "two"),
    ),
    "hotel": (
        ("unit_area_heating_energy", "单位建筑面积供暖能耗", "kgce_per_m2", "kgce/(m²·a)", "two"),
        ("unit_area_non_heating_electricity", "单位建筑面积非供暖电耗", "kwh_per_m2", "kWh/(m²·a)", "two"),
    ),
    "hospital": (
        ("unit_area_heating_energy", "单位建筑面积供暖能耗", "kgce_per_m2", "kgce/(m²·a)", "two"),
        ("unit_area_non_heating_electricity", "单位建筑面积非供暖电耗", "kwh_per_m2", "kWh/(m²·a)", "two"),
        ("per_bed_non_heating_electricity", "单位床位非供暖电耗", "k10_kwh_per_bed", "10³ kWh/(床·a)", "two"),
    ),
}

ZHEJIANG_PUBLIC_INSTITUTION_METRICS: Dict[str, Tuple[Tuple[str, str, str, str], ...]] = {
    "agency": (
        ("unit_area_energy", "单位建筑面积能耗", "kgce_per_m2", "kgce/(m²·a)"),
        ("per_capita_energy", "人均综合能耗", "kgce_per_person", "kgce/(人·a)"),
        ("unit_area_electricity", "单位面积电耗", "kwh_per_m2", "kWh/(m²·a)"),
        ("per_capita_electricity", "人均电耗", "kwh_per_person", "kWh/(人·a)"),
    ),
    "venue": (
        ("unit_area_energy", "单位建筑面积能耗", "kgce_per_m2", "kgce/(m²·a)"),
        ("per_capita_energy", "人均综合能耗", "kgce_per_person", "kgce/(人·a)"),
        ("unit_area_electricity", "单位面积电耗", "kwh_per_m2", "kWh/(m²·a)"),
        ("per_capita_electricity", "人均电耗", "kwh_per_person", "kWh/(人·a)"),
    ),
    "university": (
        ("unit_area_energy", "单位建筑面积能耗", "kgce_per_m2", "kgce/(m²·a)"),
        ("per_capita_energy", "人均综合能耗", "kgce_per_person", "kgce/(人·a)"),
        ("unit_area_electricity", "单位面积电耗", "kwh_per_m2", "kWh/(m²·a)"),
        ("per_capita_electricity", "人均电耗", "kwh_per_person", "kWh/(人·a)"),
    ),
    "hospital": (
        ("comparable_unit_area_energy", "可比单位建筑面积能耗", "kgce_per_m2", "kgce/(m²·a)"),
        ("per_capita_energy", "人均综合能耗", "kgce_per_person", "kgce/(人·a)"),
        ("unit_area_electricity", "常规用能系统单位建筑面积电耗", "kwh_per_m2", "kWh/(m²·a)"),
    ),
}

ZHEJIANG_PUBLIC_INSTITUTION_STANDARDS = {
    "agency": "DB33/T 736-2021",
    "venue": "DB33/T 736-2021",
    "university": "DB33/T 737-2021",
    "hospital": "DB33/T 738-2021",
}


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
        if is_public_building_payload(payload):
            return payload, f"indicators.json ({payload_path})", ""
        if is_public_institution_payload(payload):
            return payload, f"indicators.json ({payload_path})", ""
        if payload.get("yearly"):
            return payload, f"indicators.json ({payload_path})", ""
        if payload.get("by_year"):
            adapted = adapt_by_year(payload)
            return adapted, f"indicators.json ({payload_path}) (caliber by_year schema, adapter 映射)", ""

    raw = read_json(project_data_path(project))

    # 2026-09-05: compute 现算优先于 data.json 嵌块——嵌块是采集时快照可能陈旧
    # （实例：水三元组改口径后，嵌块旧值 约束10/基准25 掩盖现算新值 25/10，
    # 致 WATER_SEMANTICS 误报 P0）。datava 是审查工具，应对最新口径现算核对。
    try:
        from tools.energy_audit.indicators import compute_project_indicators
        from tools.energy_audit.project_data import load_project
        proj = load_project(project)
        if proj is not None:
            return compute_project_indicators(proj), "compute_project_indicators() 现算", ""
    except ImportError:
        pass

    # 兜底：data.json 内嵌 indicators 快照（仅当现算不可用时）
    if isinstance(raw, dict):
        embedded = raw.get("indicators") or {}
        if embedded.get("yearly"):
            return embedded, "data.json → indicators（compute 不可用时的兜底快照）", ""

    return None, "", f"indicators 不存在且现算失败（项目 '{project}'）"


def is_public_building_payload(payload: dict) -> bool:
    return (
        str(payload.get("family") or "").strip() == "公共建筑"
        or isinstance(payload.get("public_building"), dict)
    )


def _public_building_expected_grade(
    value: float,
    tiers: Sequence[float],
    kind: str,
    *,
    water_missing: bool = False,
) -> str:
    if kind == "reference":
        return "参考指标"
    if kind == "water":
        if water_missing or value <= 0 or len(tiers) < 2:
            return "无数据，不评价"
        general, advanced = safe_float(tiers[0]), safe_float(tiers[1])
        if advanced > 0 and value <= advanced:
            return "低于先进值"
        if general > 0 and value <= general:
            return "低于通用值"
        return "高于通用值"
    if len(tiers) < 3:
        return ""
    first, second, third = (safe_float(v) for v in tiers[:3])
    if kind == "level":
        if third > 0 and value <= third:
            return "低于1级（先进值）"
        if second > 0 and value <= second:
            return "低于2级（约束值）"
        if first > 0 and value <= first:
            return "低于3级（限额值）"
        return "高于3级（限额值）"
    if third > 0 and value <= third:
        return "低于引导值"
    if second > 0 and value <= second:
        return "低于基准值"
    if first > 0 and value <= first:
        return "低于约束值"
    return "高于约束值"


def _two_tier_expected_grade(value: float, tiers: Sequence[float]) -> str:
    if len(tiers) < 2:
        return ""
    constraint, advanced = safe_float(tiers[0]), safe_float(tiers[1])
    if advanced > 0 and value <= advanced:
        return "达到先进值"
    if constraint > 0 and value <= constraint:
        return "符合约束值"
    return "超过约束值"


def _indicator_region(indicators: dict, raw: Optional[dict] = None) -> str:
    region = str(indicators.get("region") or "").strip()
    if not region:
        region = str(
            (indicators.get("public_building") or {}).get("region") or ""
        ).strip()
    if not region and isinstance(raw, dict):
        region = str(((raw.get("base") or {}).get("province")) or "").strip()
    if "山东" in region:
        return "山东"
    if "浙江" in region:
        return "浙江"
    return region


def review_public_building_payload(
    indicators: dict, raw: Optional[dict]
) -> List[Finding]:
    """审查浙江公共建筑 indicators.json，不回算、不套山东指标。"""
    findings: List[Finding] = []
    public_building = indicators.get("public_building") or {}
    subtype = str(public_building.get("subtype") or "")
    metric_family = "hotel" if subtype == "hotel" else "office"
    if subtype not in ("office", "venue", "hotel"):
        findings.append(
            Finding(
                code="V2.PB.SUBTYPE",
                category="报告族",
                severity=SEV_P0,
                title="浙江公共建筑子类无效，无法确定指标集",
                actual=f"subtype={subtype or '空'}",
                suggestion="确认 public_building.subtype 为 office / venue / hotel",
            )
        )

    results = public_building.get("results")
    if not isinstance(results, list) or not results:
        return findings + [
            Finding(
                code="V2.PB.RESULTS",
                category="报告族",
                severity=SEV_P0,
                title="公共建筑指标结果缺失",
                suggestion="重跑 caliber_agent.py，生成 public_building.results[]",
            )
        ]

    if isinstance(raw, dict):
        base = raw.get("base") or {}
        if str(base.get("unit_type") or "").strip() != "公共建筑":
            findings.append(
                Finding(
                    code="V2.PB.FAMILY_MISMATCH",
                    category="报告族",
                    severity=SEV_P0,
                    title="指标为公共建筑，但 data.json 报告族不是公共建筑",
                    actual=f"unit_type={base.get('unit_type') or '空'}",
                    suggestion="以 data.json → base.unit_type + base.province 为唯一报告族来源",
                )
            )
        if "浙江" not in str(base.get("province") or ""):
            findings.append(
                Finding(
                    code="V2.PB.REGION",
                    category="报告族",
                    severity=SEV_P0,
                    title="浙江公共建筑指标缺少浙江省份依据",
                    actual=f"province={base.get('province') or '空'}",
                    suggestion="补录 base.province=浙江；其他省份不得套用 DB33/T 指标",
                )
            )
    else:
        findings.append(
            Finding(
                code="V2.PB.RAW_MISSING",
                category="数据一致性",
                severity=SEV_P1,
                title="data.json 缺失，公共建筑报告族与输入口径无法交叉核验",
                suggestion="恢复项目 data.json 后重跑 V2",
            )
        )

    specs = PUBLIC_BUILDING_METRICS[metric_family]
    values_by_metric: Dict[str, List[Tuple[int, float]]] = {}
    valid_results = []

    def result_year(row: Any) -> int:
        return int(safe_float(row.get("year"))) if isinstance(row, dict) else 0

    for result in sorted(results, key=result_year):
        if not isinstance(result, dict):
            findings.append(
                Finding(
                    code="V2.PB.RESULT_SHAPE",
                    category="数据一致性",
                    severity=SEV_P0,
                    title="公共建筑年度指标结果结构错误",
                    suggestion="每个 results[] 项必须是对象",
                )
            )
            continue
        valid_results.append(result)
        year = int(safe_float(result.get("year")))
        values = result.get("values") or {}
        quota = result.get("quota") or {}
        grades = result.get("grade") or {}
        notes = result.get("notes") or {}
        for key, label, value_field, unit, kind, grade_key in specs:
            raw_value = values.get(value_field)
            value = safe_float(raw_value)
            compare_value = value
            if metric_family == "hotel" and key == "water_per_bed":
                compare_value = safe_float(values.get("water_per_bed_normalized"))
            if raw_value is None:
                findings.append(
                    Finding(
                        code="V2.PB.METRIC_MISSING",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}缺少年度结果",
                        location=f"{year}年 · {label}",
                        suggestion="重算公共建筑指标，补齐 values 字段",
                    )
                )
                continue
            if value <= 0 and kind != "water":
                findings.append(
                    Finding(
                        code="V2.PB.METRIC_ZERO",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}数值为 0",
                        location=f"{year}年 · {label}",
                        suggestion="核对面积/人数/床位与能耗分子，零值不能生成正式对标结论",
                    )
                )
            if value > 0:
                values_by_metric.setdefault(key, []).append((year, value))
            tiers = quota.get("water" if grade_key == "water" else key) or []
            water_missing = bool(notes.get("water_missing")) or value <= 0
            expected = _public_building_expected_grade(
                compare_value, tiers, kind, water_missing=water_missing
            )
            recorded = str(grades.get(grade_key) or "")
            if expected and recorded != expected:
                findings.append(
                    Finding(
                        code="V2.PB.GRADE",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}评价结论与数值不符",
                        location=f"{year}年 · {label}",
                        expected=expected,
                        actual=recorded or "空",
                        suggestion="修正公共建筑指标评价或第5章结论，二者必须逐字一致",
                    )
                )

    for key, points in values_by_metric.items():
        points.sort()
        for (prev_year, prev_value), (year, value) in zip(points, points[1:]):
            change = pct_change(value, prev_value)
            if change is None:
                findings.append(
                    Finding(
                        code="V2.PB.YOY.ZERO_BASE",
                        category="年际对比",
                        severity=SEV_P1,
                        title=f"{key} {prev_year}年基数为 0，无法计算年际变化",
                        location=f"{prev_year}→{year}年 · {key}",
                        suggestion="补齐基准年数据，否则第5章趋势结论不成立",
                    )
                )
                continue
            severity = _yoy_severity(change)
            if severity:
                findings.append(
                    Finding(
                        code="V2.PB.YOY.CHANGE",
                        category="年际对比",
                        severity=severity,
                        title=f"{key} {prev_year}→{year}年变化 {change:+.1f}%",
                        location=f"{prev_year}→{year}年 · {key}",
                        suggestion="先排除面积/人数/床位/能耗录入错误，再在第5章说明原因",
                    )
                )

    if not valid_results:
        return findings + [
            Finding(
                code="V2.PB.RESULTS",
                category="报告族",
                severity=SEV_P0,
                title="公共建筑指标结果无可读年度对象",
                suggestion="重跑 caliber_agent.py，生成 public_building.results[]",
            )
        ]
    latest = sorted(valid_results, key=result_year)[-1]
    latest_values = latest.get("values") or {}
    expected_standards = (
        {"unit_comparable_energy"}
        if metric_family == "hotel"
        else {
            "unit_area_non_heating_energy",
            "unit_area_electricity",
            "per_capita_energy",
            "per_capita_electricity",
        }
    )
    for metric_key, value_field, result_key in PUBLIC_BUILDING_TOP_METRICS[metric_family]:
        node = indicators.get(metric_key)
        if not isinstance(node, dict):
            findings.append(
                Finding(
                    code="V2.PB.TOP_METRIC",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"公共建筑顶层指标缺少 {metric_key}",
                    suggestion="重跑 caliber_agent.py，保持顶层指标与 results[] 同源",
                )
            )
            continue
        top_value = safe_float(node.get(value_field))
        latest_value = safe_float(latest_values.get(result_key))
        if abs(top_value - latest_value) > 0.011:
            findings.append(
                Finding(
                    code="V2.PB.TOP_METRIC_MISMATCH",
                    category="数据一致性",
                    severity=SEV_P0,
                    title=f"{metric_key} 顶层值与最新年度值不一致",
                    expected=f"{fmt_num(latest_value)}",
                    actual=f"{fmt_num(top_value)}",
                    suggestion="以同一批 results[] 重建顶层指标，防止第5章与写作契约分叉",
                )
            )
        benchmark = node.get("benchmark") or {}
        standard = str(benchmark.get("标准") or "")
        grade_key = (
            "water"
            if metric_key == "water_indicator" and metric_family == "hotel"
            else result_key
        )
        latest_grade = str((latest.get("grade") or {}).get(grade_key) or "")
        benchmark_grade = str(benchmark.get("评价结果") or "")
        if benchmark_grade and latest_grade and benchmark_grade != latest_grade:
            findings.append(
                Finding(
                    code="V2.PB.TOP_BENCHMARK",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"{metric_key} 顶层评价结果与最新年度不一致",
                    expected=latest_grade,
                    actual=benchmark_grade,
                    suggestion="以 public_building.results[] 最新年度结果同步顶层 benchmark",
                )
            )
        if "DB37" in standard.upper():
            findings.append(
                Finding(
                    code="V2.PB.DB37",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"{metric_key} 错用山东 DB37 定额",
                    actual=standard,
                    suggestion="浙江公共建筑改用 DB33/T 736-2021 或 DB33/T 760-2023",
                )
            )
        if metric_key in expected_standards:
            required = "DB33/T 760-2023" if metric_family == "hotel" else "DB33/T 736-2021"
            if required not in standard:
                findings.append(
                    Finding(
                        code="V2.PB.STANDARD",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{metric_key} 标准号与公共建筑子类不符",
                        expected=required,
                        actual=standard or "空",
                        suggestion="修正公共建筑指标标准来源",
                    )
                )
        elif metric_key == "water_indicator" and standard:
            if "浙江" not in standard or not any(
                token in standard for token in ("用水", "取水", "水定额")
            ):
                findings.append(
                    Finding(
                        code="V2.PB.WATER_STANDARD",
                        category="对标合理性",
                        severity=SEV_P0,
                        title="单位用水量未引用浙江省用水定额",
                        actual=standard,
                        suggestion="用水指标改引浙江省用（取）水定额（2019）",
                    )
                )
    return findings


def review_shandong_public_building_payload(
    indicators: dict, raw: Optional[dict]
) -> List[Finding]:
    """审查山东公共建筑 eA/eB/eC 与 DB37 二档口径。"""
    findings: List[Finding] = []
    section = indicators.get("public_building") or {}
    subtype = str(section.get("subtype") or "")
    if subtype not in SHANDONG_PUBLIC_BUILDING_METRICS:
        return [
            Finding(
                code="V2.SD_PB.SUBTYPE",
                category="报告族",
                severity=SEV_P0,
                title="山东公共建筑子类无效",
                actual=f"subtype={subtype or '空'}",
                suggestion=(
                    "确认 public_building.subtype 为 business_office / hotel / hospital；"
                    "机关办公不得套用 DB37/T 5078"
                ),
            )
        ]

    standard = {
        "business_office": "DB37/T 5078-2024",
        "hotel": "DB37/T 5076-2024",
        "hospital": "DB37/T 5079-2024",
    }[subtype]
    results = section.get("results")
    if not isinstance(results, list) or not results:
        return [
            Finding(
                code="V2.SD_PB.RESULTS",
                category="报告族",
                severity=SEV_P0,
                title="山东公共建筑指标结果缺失",
                suggestion="重跑 caliber_agent.py，生成 public_building.results[]",
            )
        ]

    if isinstance(raw, dict):
        base = raw.get("base") or {}
        if str(base.get("unit_type") or "").strip() != "公共建筑":
            findings.append(
                Finding(
                    code="V2.SD_PB.FAMILY_MISMATCH",
                    category="报告族",
                    severity=SEV_P0,
                    title="指标为公共建筑，但 data.json 报告族不是公共建筑",
                    actual=f"unit_type={base.get('unit_type') or '空'}",
                )
            )
        if "山东" not in str(base.get("province") or ""):
            findings.append(
                Finding(
                    code="V2.SD_PB.REGION",
                    category="报告族",
                    severity=SEV_P0,
                    title="山东公共建筑指标缺少山东省份依据",
                    actual=f"province={base.get('province') or '空'}",
                )
            )
    else:
        findings.append(
            Finding(
                code="V2.SD_PB.RAW_MISSING",
                category="数据一致性",
                severity=SEV_P1,
                title="data.json 缺失，山东公共建筑口径无法交叉核验",
            )
        )

    for result in sorted(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: safe_float(item.get("year")),
    ):
        year = int(safe_float(result.get("year")))
        values = result.get("values") or {}
        quota = result.get("quota") or {}
        grades = result.get("grade") or {}
        if str(result.get("standard_id") or "") != standard:
            findings.append(
                Finding(
                    code="V2.SD_PB.STANDARD",
                    category="对标合理性",
                    severity=SEV_P0,
                    title="山东公共建筑标准号与子类不符",
                    location=f"{year}年 · {subtype}",
                    expected=standard,
                    actual=str(result.get("standard_id") or "空"),
                )
            )
        for key, label, value_field, unit, kind in SHANDONG_PUBLIC_BUILDING_METRICS[subtype]:
            raw_value = values.get(key)
            if raw_value is None:
                findings.append(
                    Finding(
                        code="V2.SD_PB.METRIC_MISSING",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}缺少年度结果",
                        location=f"{year}年 · {label}",
                    )
                )
                continue
            value = safe_float(raw_value)
            tiers = quota.get(key) or []
            if len(tiers) != 2:
                findings.append(
                    Finding(
                        code="V2.SD_PB.TIERS",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}限额档位不是二档",
                        location=f"{year}年 · {label}",
                        expected="[约束值, 先进值]",
                        actual=str(tiers),
                    )
                )
                continue
            expected = _two_tier_expected_grade(value, tiers)
            recorded = str(grades.get(key) or "")
            if expected != recorded:
                findings.append(
                    Finding(
                        code="V2.SD_PB.GRADE",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}评价结论与数值不符",
                        location=f"{year}年 · {label}",
                        expected=expected,
                        actual=recorded or "空",
                    )
                )

    latest = sorted(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: safe_float(item.get("year")),
    )[-1]
    latest_values = latest.get("values") or {}
    for key, label, value_field, _unit, _kind in SHANDONG_PUBLIC_BUILDING_METRICS[subtype]:
        node = indicators.get(key)
        if not isinstance(node, dict):
            findings.append(
                Finding(
                    code="V2.SD_PB.TOP_METRIC_MISSING",
                    category="数据一致性",
                    severity=SEV_P0,
                    title=f"{label}顶层指标缺失",
                )
            )
            continue
        if abs(safe_float(node.get(value_field)) - safe_float(latest_values.get(key))) > 0.011:
            findings.append(
                Finding(
                    code="V2.SD_PB.TOP_METRIC_MISMATCH",
                    category="数据一致性",
                    severity=SEV_P0,
                    title=f"{label}顶层值与最新年度不一致",
                )
            )
        benchmark = node.get("benchmark") or {}
        if any(token in benchmark for token in ("基准值", "引导值")):
            findings.append(
                Finding(
                    code="V2.SD_PB.FORBIDDEN_TIER",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"{label}混入浙江三档字段",
                    actual="、".join(k for k in ("基准值", "引导值") if k in benchmark),
                )
            )
        if "DB33" in str(benchmark.get("标准") or ""):
            findings.append(
                Finding(
                    code="V2.SD_PB.DB33",
                    category="对标合理性",
                    severity=SEV_P0,
                    title=f"{label}错用浙江 DB33 定额",
                    actual=str(benchmark.get("标准") or ""),
                )
            )
    if (
        "DB33" in json.dumps(indicators, ensure_ascii=False)
        and not any(f.code == "V2.SD_PB.DB33" for f in findings)
    ):
        findings.append(
            Finding(
                code="V2.SD_PB.DB33",
                category="对标合理性",
                severity=SEV_P0,
                title="山东公共建筑指标混入浙江 DB33 标准",
                suggestion="按山东公共建筑包使用 DB37/T 5076/5078/5079",
            )
        )
    return findings


def is_public_institution_payload(payload: dict) -> bool:
    return (
        str(payload.get("family") or "").strip() == "公共机构"
        and (
            str(payload.get("region") or "").strip() == "浙江"
            or isinstance(payload.get("public_institution"), dict)
        )
    )


def review_zhejiang_public_institution_payload(
    indicators: dict, raw: Optional[dict]
) -> List[Finding]:
    """审查浙江公共机构 736/737/738 三档指标。"""
    findings: List[Finding] = []
    section = indicators.get("public_institution") or {}
    subtype = str(section.get("subtype") or "")
    if subtype not in ZHEJIANG_PUBLIC_INSTITUTION_METRICS:
        return [
            Finding(
                code="V2.ZJ_PI.SUBTYPE",
                category="报告族",
                severity=SEV_P0,
                title="浙江公共机构子类无效",
                actual=f"subtype={subtype or '空'}",
                suggestion="确认 subtype 为 agency / venue / university / hospital",
            )
        ]

    expected_standard = ZHEJIANG_PUBLIC_INSTITUTION_STANDARDS[subtype]
    results = section.get("results")
    if not isinstance(results, list) or not results:
        return [
            Finding(
                code="V2.ZJ_PI.RESULTS",
                category="报告族",
                severity=SEV_P0,
                title="浙江公共机构指标结果缺失",
            )
        ]
    if isinstance(raw, dict):
        base = raw.get("base") or {}
        if str(base.get("unit_type") or "").strip() != "公共机构":
            findings.append(
                Finding(
                    code="V2.ZJ_PI.FAMILY_MISMATCH",
                    category="报告族",
                    severity=SEV_P0,
                    title="指标为公共机构，但 data.json 报告族不匹配",
                    actual=f"unit_type={base.get('unit_type') or '空'}",
                )
            )
        if "浙江" not in str(base.get("province") or ""):
            findings.append(
                Finding(
                    code="V2.ZJ_PI.REGION",
                    category="报告族",
                    severity=SEV_P0,
                    title="浙江公共机构指标缺少浙江省份依据",
                    actual=f"province={base.get('province') or '空'}",
                )
            )
    else:
        findings.append(
            Finding(
                code="V2.ZJ_PI.RAW_MISSING",
                category="数据一致性",
                severity=SEV_P1,
                title="data.json 缺失，浙江公共机构口径无法交叉核验",
            )
        )

    for result in sorted(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: safe_float(item.get("year")),
    ):
        year = int(safe_float(result.get("year")))
        values = result.get("values") or {}
        quota = result.get("quota") or {}
        grades = result.get("grade") or {}
        if str(result.get("standard_id") or "") != expected_standard:
            findings.append(
                Finding(
                    code="V2.ZJ_PI.STANDARD",
                    category="对标合理性",
                    severity=SEV_P0,
                    title="浙江公共机构标准号与子类不符",
                    location=f"{year}年 · {subtype}",
                    expected=expected_standard,
                    actual=str(result.get("standard_id") or "空"),
                )
            )
        for key, label, value_field, unit in ZHEJIANG_PUBLIC_INSTITUTION_METRICS[subtype]:
            raw_value = values.get(key)
            if raw_value is None:
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.METRIC_MISSING",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}缺少年度结果",
                        location=f"{year}年 · {label}",
                    )
                )
                continue
            tiers = quota.get(key) or []
            if len(tiers) != 3:
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.TIERS",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}限额档位不是三档",
                        location=f"{year}年 · {label}",
                        expected="[约束值, 基准值, 引导值]",
                        actual=str(tiers),
                    )
                )
                continue
            expected = _public_building_expected_grade(
                safe_float(raw_value), tiers, "three"
            )
            recorded = str(grades.get(key) or "")
            if expected != recorded:
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.GRADE",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}评价结论与数值不符",
                        location=f"{year}年 · {label}",
                        expected=expected,
                        actual=recorded or "空",
                    )
                )

    # 顶层指标是第 5/8 章的取数入口。逐项核对最新年度值是必要的：
    # 只校验 results[] 会放过“年度结果正确，但指标 JSON 顶层被手工改错”的报告。
    latest_rows = sorted(
        (item for item in results if isinstance(item, dict)),
        key=lambda item: safe_float(item.get("year")),
    )
    if latest_rows:
        latest = latest_rows[-1]
        latest_values = latest.get("values") or {}
        for key, label, value_field, _unit in ZHEJIANG_PUBLIC_INSTITUTION_METRICS[subtype]:
            node = indicators.get(key)
            if not isinstance(node, dict):
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.TOP_METRIC_MISSING",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}顶层指标缺失",
                        suggestion="重跑 caliber_agent.py，确保最新年度结果同步到顶层指标",
                    )
                )
                continue
            if abs(safe_float(node.get(value_field)) - safe_float(latest_values.get(key))) > 0.011:
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.TOP_METRIC_MISMATCH",
                        category="数据一致性",
                        severity=SEV_P0,
                        title=f"{label}顶层值与最新年度不一致",
                        expected=str(latest_values.get(key)),
                        actual=str(node.get(value_field)),
                    )
                )
            benchmark = node.get("benchmark") or {}
            if any(label not in benchmark for label in ("约束值", "基准值", "引导值")):
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.TOP_BENCHMARK",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}顶层定额三档不完整",
                        actual=str(sorted(benchmark)),
                    )
                )
            if "DB37" in str(benchmark.get("标准") or ""):
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.DB37",
                        category="对标合理性",
                        severity=SEV_P0,
                        title=f"{label}错用山东 DB37 定额",
                        actual=str(benchmark.get("标准") or ""),
                    )
                )

        # 738 的原始单位面积能耗只能作为过程量，不能替代可比指标成为
        # 顶层主指标。保留过程值时，不得给它配置浙江三档 benchmark。
        if subtype == "hospital" and "unit_area_energy" in indicators:
            raw_node = indicators.get("unit_area_energy") or {}
            raw_benchmark = raw_node.get("benchmark") if isinstance(raw_node, dict) else {}
            if raw_benchmark:
                findings.append(
                    Finding(
                        code="V2.ZJ_PI.HOSPITAL_PRIMARY_METRIC",
                        category="对标合理性",
                        severity=SEV_P0,
                        title="医院报告把原始单位面积能耗配置成主指标",
                        suggestion="仅使用「可比单位建筑面积能耗」作为 738 主指标",
                    )
                )

    if "0.31" in json.dumps(indicators, ensure_ascii=False):
        findings.append(
            Finding(
                code="V2.ZJ_PI.COAL_EQUIVALENT",
                category="对标合理性",
                severity=SEV_P0,
                title="浙江公共机构指标混入山东公共机构 0.31 等价值口径",
                suggestion="按浙江公共机构包使用 0.1229 kgce/kWh",
            )
        )
    if "DB37" in json.dumps(indicators, ensure_ascii=False):
        findings.append(
            Finding(
                code="V2.ZJ_PI.DB37",
                category="对标合理性",
                severity=SEV_P0,
                title="浙江公共机构指标混入山东 DB37 标准",
                suggestion="按浙江公共机构包使用 DB33/T 736/737/738",
            )
        )
    return findings


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
        return "低于引导值"
    if value <= safe_float(benchmark.get("基准值")):
        return "低于基准值"
    if value <= safe_float(benchmark.get("约束值")):
        return "低于约束值"
    return "高于约束值"


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
    return "高于通用值"


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
    rng_key = "heating_kgce_per_m2" if spec.key == "unit_area_heating" else field_name
    low, high = PLAUSIBLE_RANGE.get(rng_key, (0.0, float("inf")))
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
                title="医疗机构缺床位数，单位开放床日用水量待补充（不降级人均口径）",
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

def _save_review_result(
    project: str,
    output_dir: Optional[str],
    result: ReviewResult,
) -> ReviewResult:
    """保存 V2 审查产物，并保证 txt 中写有最终 artifact 路径。"""
    save_dir = project_dir(project, output_dir)
    review_path = Path(
        write_json(save_dir / "indicator_review.json", result.to_dict())
    )
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


def run(project: str, *, output_dir: Optional[str] = None) -> ReviewResult:
    indicators, source, error = load_indicators(project, output_dir)
    if error or indicators is None:
        return build_result(MODE, project, [], error=error or "指标加载失败")

    if (
        not is_public_building_payload(indicators)
        and not is_public_institution_payload(indicators)
        and indicators.get("status") != "ok"
    ):
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
    is_shandong_pb = (
        is_public_building_payload(indicators)
        and _indicator_region(indicators, raw) == "山东"
    )
    if is_public_building_payload(indicators):
        public_building = indicators.get("public_building") or {}
        results = public_building.get("results") or []
        findings = (
            review_shandong_public_building_payload(indicators, raw)
            if is_shandong_pb
            else review_public_building_payload(indicators, raw)
        )
        result = build_result(
            MODE,
            project,
            findings,
            inputs={
                "指标来源": source,
                "报告族": (
                    "公共建筑（山东）"
                    if is_shandong_pb
                    else "公共建筑（浙江）"
                ),
                "data.json": "已读取" if isinstance(raw, dict) else "缺失（跳过口径校验）",
            },
            extra={
                "institution_type": "public_building",
                "region": "山东" if is_shandong_pb else "浙江",
                "public_building_subtype": public_building.get("subtype", ""),
                "years": [
                    int(safe_float(row.get("year")))
                    for row in results
                    if isinstance(row, dict)
                ],
                "building_area": indicators.get("building_area"),
                "people_count": indicators.get("people_count"),
                "beds_count": indicators.get("beds_count"),
            },
        )
        return _save_review_result(project, output_dir, result)

    if is_public_institution_payload(indicators):
        public_institution = indicators.get("public_institution") or {}
        results = public_institution.get("results") or []
        result = build_result(
            MODE,
            project,
            review_zhejiang_public_institution_payload(indicators, raw),
            inputs={
                "指标来源": source,
                "报告族": "公共机构（浙江）",
                "data.json": "已读取" if isinstance(raw, dict) else "缺失（跳过口径校验）",
            },
            extra={
                "institution_type": "public_institution",
                "region": "浙江",
                "public_institution_subtype": public_institution.get("subtype", ""),
                "years": [
                    int(safe_float(row.get("year")))
                    for row in results
                    if isinstance(row, dict)
                ],
                "building_area": indicators.get("building_area"),
                "people_count": indicators.get("people_count"),
                "beds_count": indicators.get("beds_count"),
            },
        )
        return _save_review_result(project, output_dir, result)

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
                # 2026-09-05：区分"数据缺失待补充"（error_kind=missing_input，P1 不阻塞）
                # 与"计算失败"（P0 阻塞）。医院缺 bed_count 属于前者。
                is_missing = metric.get("error_kind") == "missing_input"
                findings.append(
                    Finding(
                        code="V2.METRIC.MISSING" if is_missing else "V2.METRIC.ERROR",
                        category="数据一致性",
                        severity=SEV_P1 if is_missing else SEV_P0,
                        title=f"{spec.label} 待补充数据" if is_missing else f"{spec.label} 计算失败",
                        detail=str(metric.get("error")),
                        location=f"{year}年 · {spec.label}",
                        suggestion=("补采缺失字段后重算指标（如医院 bed_count）"
                                    if is_missing else "修正输入参数后重算指标"),
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

    return _save_review_result(project, output_dir, result)
