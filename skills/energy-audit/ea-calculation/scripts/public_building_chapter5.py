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
    ("unit_comparable_energy", "单位可比综合能耗", "kgce/m²"),
    ("water_per_bed", "单位床年用水量", "m³/(床·年)"),
]

LEGACY_760_GRADES = {
    "低于1级（先进值）": "低于引导值",
    "低于2级（约束值）": "低于基准值",
    "低于3级（限额值）": "低于约束值",
    "高于3级（限额值）": "高于约束值",
}


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


def _year_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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

    quota_key = "water" if (hotel and metric_key == "water_per_bed") else metric_key
    tiers = results[0].get("quota", {}).get(quota_key) or []
    if hotel and metric_key == "unit_comparable_energy":
        tier_labels = ["约束值", "基准值", "引导值"]
    elif metric_key == "unit_water" or (hotel and metric_key == "water_per_bed"):
        tier_labels = ["通用值", "先进值"]
    else:
        tier_labels = ["约束值", "基准值", "引导值"]
    for i, tier_label in enumerate(tier_labels):
        val = tiers[i] if i < len(tiers) else "—"
        val = _num(val)
        rows.append([f"定额标准{tier_label}（{unit}）"] + [val] * len(years))

    grade_key = "water" if (hotel and metric_key == "water_per_bed") else metric_key
    grades = [str(r["grade"].get(grade_key, "—")) for r in results]
    if hotel and metric_key == "unit_comparable_energy":
        grades = [LEGACY_760_GRADES.get(grade, grade) for grade in grades]
    rows.append(["评价结果"] + grades)
    return _table(headers, rows)


def _manifest_figure(
    manifest: dict[str, Any] | None,
    kind: str,
    energy_code: str = "",
    year: str = "",
) -> dict[str, Any]:
    for item in (manifest or {}).get("figures", []) or []:
        if str(item.get("kind") or "") != kind:
            continue
        if energy_code and str(item.get("energy_code") or "") != energy_code:
            continue
        if year and str(item.get("year") or "") != str(year):
            continue
        return item
    return {}


def _figure_no(figure: dict[str, Any]) -> str:
    return str(figure.get("caption") or "").split(" ", 1)[0]


def render(
    spec: dict[str, Any],
    results: list[dict[str, Any]],
    unit_name: str,
    figures_manifest: dict[str, Any] | None = None,
) -> str:
    subtype = spec.get("subtype", "office")
    hotel = subtype == "hotel"
    years = [r["year"] for r in results]
    blocked_years = {
        year
        for value in (spec.get("incomplete_report_years") or {})
        for year in [_year_int(value)]
        if year is not None
    }
    table_years = [
        year for year in spec.get("years", [])
        if _year_int(year.get("year")) not in blocked_years
    ]
    table_results = [
        result for result in results
        if _year_int(result.get("year")) not in blocked_years
    ]
    year_label = "、".join(str(y) for y in years)
    flow_fig = _manifest_figure(figures_manifest, "energy_flow")
    flow_block = [flow_fig["caption"], ""] if flow_fig else []

    lines: list[str] = [
        "# 第5章 能源资源消费/消耗指标分析",
        "",
        f"本章基于{unit_name}{year_label}年的电、水等能源账单及统计数据，对建筑能耗、"
        "能耗指标及对标情况进行分析。",
        "",
        "## 5.1 能源资源消费/消耗概况",
        "",
        (
            f"本项目主要用能类型包括电、水、天然气等，能源资源流向如"
            f"{_figure_no(flow_fig)}所示。"
            if flow_fig else "本项目主要用能类型包括电、水、天然气等。"
        ),
        "",
        *flow_block,
        "## 5.2 能源资源消耗/消费数据",
        "",
        "### 5.2.1 用电情况分析",
        "",
    ]

    elec_rows = []
    for y in table_years:
        elec_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('electricity_kwh')):.0f}",
            f"{_f(y.get('electricity_cost_wan')):.2f}" if y.get("electricity_cost_wan") else "—",
        ])
    elec_total = _manifest_figure(figures_manifest, "total", "electricity")
    elec_monthly = _manifest_figure(figures_manifest, "monthly", "electricity")
    lines += [_table(["年份", "用电量（kWh）", "电费（万元）"], elec_rows), ""]
    elec_refs = []
    if elec_total:
        elec_refs.append(f"年用电量变化趋势如{_figure_no(elec_total)}所示")
    if elec_monthly:
        elec_refs.append(f"逐月用电情况如{_figure_no(elec_monthly)}所示")
    if elec_refs:
        lines += ["，".join(elec_refs) + "。", ""]
    if elec_total:
        lines += [elec_total["caption"], ""]
    if elec_monthly:
        lines += [elec_monthly["caption"], ""]

    lines += ["### 5.2.2 用水情况分析", ""]
    water_rows = []
    for y in table_years:
        water_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('water_t')):.0f}",
            f"{_f(y.get('water_cost_wan')):.2f}" if y.get("water_cost_wan") else "—",
        ])
    water_total = _manifest_figure(figures_manifest, "total", "water")
    water_monthly = _manifest_figure(figures_manifest, "monthly", "water")
    lines += [_table(["年份", "用水量（m³）", "水费（万元）"], water_rows), ""]
    water_refs = []
    if water_total:
        water_refs.append(f"年用水量变化趋势如{_figure_no(water_total)}所示")
    if water_monthly:
        water_refs.append(f"逐月用水情况如{_figure_no(water_monthly)}所示")
    if water_refs:
        lines += ["，".join(water_refs) + "。", ""]
    if water_total:
        lines += [water_total["caption"], ""]
    if water_monthly:
        lines += [water_monthly["caption"], ""]

    lines += ["### 5.2.3 其他用能分析", ""]
    other_rows = []
    for y in table_years:
        other_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('gas_m3')):.0f}",
            f"{_f(y.get('heat_gj')):.2f}",
        ])
    lines += [_table(["年份", "天然气（m³）", "供热量（GJ）"], other_rows), "",
              "其他能源品种按实际计量数据统计；未计量的品种在报告中注明。", ""]

    lines += ["### 5.2.4 能源资源费用分析", ""]
    cost_rows = []
    for y in table_years:
        cost_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('electricity_cost_wan')):.2f}",
            f"{_f(y.get('water_cost_wan')):.2f}",
            f"{_f(y.get('gas_cost_wan')):.2f}",
            f"{_f(y.get('heat_cost_wan')):.2f}",
        ])
    lines += [_table(["年份", "电费（万元）", "水费（万元）", "燃气费（万元）", "热费（万元）"], cost_rows), ""]
    pie_captions = []
    for year in years:
        pie = _manifest_figure(figures_manifest, "cost_pie", year=str(year))
        if pie:
            pie_captions.append(pie["caption"])
    if pie_captions:
        lines += ["各年度能源费用占比如下。", ""]
        for caption in pie_captions:
            lines += [caption, ""]
    else:
        lines += ["费用占比及变化趋势按项目实际数据补充。", ""]

    lines += ["## 5.3 能耗资源消耗/消费指标", ""]
    metrics = HOTEL_METRICS if hotel else OFFICE_METRICS
    for idx, (key, label, unit) in enumerate(metrics, 1):
        lines += [f"### 5.3.{idx} {label}", ""]
        if hotel and idx == 1:
            lines += [
                "单位可比综合能耗按下列公式计算：",
                "",
                "[FORMULA10]",
                "",
                "式中：",
                "",
                "E_{kd}——单位可比综合能耗，单位为千克标准煤每平方米"
                "（kgce/m²）；",
                "E_{j}——单位综合能耗，单位为千克标准煤每平方米"
                "（kgce/m²）；",
                "a——综合能耗修正系数；",
                "m——第m项综合能耗修正系数。",
                "",
                f"统计结果见表5.{idx}。",
                "",
            ]
        elif hotel and key == "water_per_bed":
            water_notes = results[0].get("notes") or {}
            industry_code = water_notes.get("water_industry_code", "")
            category_name = water_notes.get("water_category_name", "")
            subitem = water_notes.get("water_subitem", "")
            lines += [
                "单位床年用水量按下式计算：",
                "",
                "[FORMULA9]",
                "",
                "式中：",
                "",
                "V_{uc}——单位床年用水量，单位为立方米每床年"
                "（m³/(床·年)）；",
                "V_{k}——年度用水量，单位为立方米每年（m³/a）；",
                "N——总床位数，单位为床；",
                "Q——宾馆床位出租率。",
                "",
                f"统计结果见表5.{idx}。",
                "",
                (
                    f"本项目按 {industry_code} {category_name}—{subitem}"
                    f"匹配用水定额，定额单位为 {unit}。"
                )
                if industry_code and category_name and subitem
                else f"{label}按标准口径计算。",
                "",
            ]
        else:
            lines += [
                f"{label}按标准口径计算，统计结果见表5.{idx}。",
                "",
            ]
        lines += [
            f"表5.{idx} {label}",
            "",
            _metric_table(key, label, unit, table_results, hotel),
            "",
        ]
        if hotel and idx == 1:
            lines += [
                "单位综合能耗 E_{j} 仅为计算单位可比综合能耗的中间量，"
                "不作为独立评价指标。",
                "",
            ]
        sentences = []
        for r in results:
            value = r["values"].get(key)
            grade = r["grade"].get("water" if (hotel and key == "water_per_bed") else key, "—")
            if hotel and key == "unit_comparable_energy":
                grade = LEGACY_760_GRADES.get(str(grade), grade)
            if key in ("unit_water", "water_per_bed") and _f(value) == 0:
                value = "—"
            sentences.append(f"{r['year']}年为{value}{unit}，{grade}")
        lines += [f"{unit_name}{year_label}年{label}分别为：" + "；".join(sentences) + "。", ""]

    return "\n".join(lines)
