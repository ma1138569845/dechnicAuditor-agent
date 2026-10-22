# -*- coding: utf-8 -*-
"""公共建筑第5章生成（v0.1，最小可用）。

输入：
- spec: 与 public_building_indicators.compute_project 相同的项目 dict
- results: compute_project 的输出（逐年）
- unit_name: 单位/建筑名称

输出：第5章 Markdown。图表位置保留文字提示，图表由 author/装配链处理。
"""
from __future__ import annotations

from typing import Any


OFFICE_METRICS = [
    ("unit_area_energy", "单位建筑面积能耗", "kgce/m²"),
    ("unit_area_electricity", "常规用能系统单位建筑面积电耗", "kWh/m²"),
    ("per_capita_energy", "人均综合能耗", "kgce/per"),
    ("per_capita_electricity", "人均电耗", "kWh/per"),
    ("unit_water", "单位用水量", "m³/(p·a)"),
]

HOTEL_METRICS = [
    ("unit_energy", "单位综合能耗", "kgce/m²"),
    ("unit_comparable_energy", "单位可比综合能耗", "kgce/m²"),
    ("water_per_bed", "单位用水量", "m³/(床·年)"),
]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> Any:
    """整数浮点去掉无意义小数位（6.0 → 6），其余保持原值。"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def _metric_table(metric_key: str, label: str, unit: str,
                  results: list[dict[str, Any]], hotel: bool) -> str:
    years = [r["year"] for r in results]
    headers = ["项目"] + [f"{y}年" for y in years]
    rows: list[list[Any]] = []
    values = []
    for r in results:
        value = r["values"].get(metric_key, "—")
        if metric_key in ("unit_water", "water_per_bed") and _f(value) == 0:
            value = "—"
        values.append(_num(value))
    rows.append([f"{label}（{unit}）"] + values)

    if metric_key == "unit_energy":
        rows.append(["评价结果"] + ["参考指标"] * len(years))
        return _table(headers, rows)

    quota_key = "water" if (hotel and metric_key == "water_per_bed") else metric_key
    tiers = results[0].get("quota", {}).get(quota_key) or []
    if hotel and metric_key == "unit_comparable_energy":
        tier_labels = ["3级（限额值）", "2级（约束值）", "1级（先进值）"]
    elif metric_key == "unit_water" or (hotel and metric_key == "water_per_bed"):
        tier_labels = ["通用值", "先进值"]
    else:
        tier_labels = ["约束值", "基准值", "引导值"]
    for i, tier_label in enumerate(tier_labels):
        val = tiers[i] if i < len(tiers) else "—"
        val = _num(val)
        rows.append([f"定额标准{tier_label}（{unit}）"] + [val] * len(years))

    grade_key = "water" if (hotel and metric_key == "water_per_bed") else metric_key
    rows.append(["评价结果"] + [r["grade"].get(grade_key, "—") for r in results])
    return _table(headers, rows)


def render(spec: dict[str, Any], results: list[dict[str, Any]], unit_name: str) -> str:
    subtype = spec.get("subtype", "office")
    hotel = subtype == "hotel"
    years = [r["year"] for r in results]
    year_label = "、".join(str(y) for y in years)

    lines: list[str] = [
        "# 第5章 能源资源消费/消耗指标分析",
        "",
        f"本章基于{unit_name}{year_label}年的电、水等能源账单及统计数据，对建筑能耗、"
        "能耗指标及对标情况进行分析。",
        "",
        "## 5.1 能源资源消费/消耗概况",
        "",
        "本项目主要用能类型包括电、水、天然气等，能源资源流向如图5.1所示。",
        "",
        "图5.1 能源资源流向图",
        "",
        "## 5.2 能源资源消耗/消费数据",
        "",
        "### 5.2.1 用电情况分析",
        "",
    ]

    elec_rows = []
    for y in spec.get("years", []):
        elec_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('electricity_kwh')):.0f}",
            f"{_f(y.get('electricity_cost_wan')):.2f}" if y.get("electricity_cost_wan") else "—",
        ])
    lines += [_table(["年份", "用电量（kWh）", "电费（万元）"], elec_rows), "",
              "近三年用电量变化趋势如图5.2所示，逐月用电情况如图5.3所示。", "",
              "图5.2 年用电量变化趋势", "", "图5.3 逐月用电量", ""]

    lines += ["### 5.2.2 用水情况分析", ""]
    water_rows = []
    for y in spec.get("years", []):
        water_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('water_t')):.0f}",
            f"{_f(y.get('water_cost_wan')):.2f}" if y.get("water_cost_wan") else "—",
        ])
    lines += [_table(["年份", "用水量（m³）", "水费（万元）"], water_rows), "",
              "近三年用水量变化趋势如图5.4所示，逐月用水情况如图5.5所示。", "",
              "图5.4 年用水量变化趋势", "", "图5.5 逐月用水量", ""]

    lines += ["### 5.2.3 其他用能分析", ""]
    other_rows = []
    for y in spec.get("years", []):
        other_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('gas_m3')):.0f}",
            f"{_f(y.get('heat_gj')):.2f}",
        ])
    lines += [_table(["年份", "天然气（m³）", "供热量（GJ）"], other_rows), "",
              "其他能源品种按实际计量数据统计；未计量的品种在报告中注明。", ""]

    lines += ["### 5.2.4 能源资源费用分析", ""]
    cost_rows = []
    for y in spec.get("years", []):
        cost_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('electricity_cost_wan')):.2f}",
            f"{_f(y.get('water_cost_wan')):.2f}",
            f"{_f(y.get('gas_cost_wan')):.2f}",
            f"{_f(y.get('heat_cost_wan')):.2f}",
        ])
    lines += [_table(["年份", "电费（万元）", "水费（万元）", "燃气费（万元）", "热费（万元）"], cost_rows), "",
              "费用占比及变化趋势按项目实际数据补充。", ""]

    lines += ["## 5.3 能耗资源消耗/消费指标", ""]
    metrics = HOTEL_METRICS if hotel else OFFICE_METRICS
    for idx, (key, label, unit) in enumerate(metrics, 1):
        lines += [f"### 5.3.{idx} {label}", "",
                  f"{label}按标准口径计算，统计结果见表5.{idx}。", "",
                  f"表5.{idx} {label}", "",
                  _metric_table(key, label, unit, results, hotel), ""]
        sentences = []
        for r in results:
            value = r["values"].get(key)
            grade = r["grade"].get("water" if (hotel and key == "water_per_bed") else key, "—")
            if key in ("unit_water", "water_per_bed") and _f(value) == 0:
                value = "—"
            if key == "unit_energy":
                grade = "参考指标"
            sentences.append(f"{r['year']}年为{value}{unit}，{grade}")
        lines += [f"{unit_name}{year_label}年{label}分别为：" + "；".join(sentences) + "。", ""]

    lines += ["", "> 注：本章为 v0.1 自动生成骨架；图表与逐月归因由 author 按公共建筑写作指南补充。", ""]
    return "\n".join(lines)
