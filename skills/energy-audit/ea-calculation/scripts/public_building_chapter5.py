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

DB33_T_760_2023 = "《旅游饭店单位综合能耗限额及计算方法》（DB33/T 760-2023）"


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


def _electricity_complete(year: dict[str, Any]) -> bool:
    """判断电量是否完整；月度数据存在时须覆盖 12 个月。"""
    monthly = year.get("monthly_electricity_kwh")
    if isinstance(monthly, list):
        return len(monthly) == 12 and all(value is not None for value in monthly)
    return _f(year.get("electricity_kwh")) > 0


def _year_spec(spec: dict[str, Any], year: Any) -> dict[str, Any]:
    for item in spec.get("years", []) or []:
        if _year_int(item.get("year")) == _year_int(year):
            return item
    return {}


def _hotel_energy_applicable(
    spec: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    """5.3.1 以电量完整为门槛；缺新水不连带排除该年度。"""
    notes = result.get("notes") or {}
    if "unit_comparable_energy_applicable" in notes:
        return bool(notes["unit_comparable_energy_applicable"])
    if "electricity_complete" in notes:
        return bool(notes["electricity_complete"])
    source = _year_spec(spec, result.get("year"))
    if source:
        return _electricity_complete(source)
    electricity = (notes.get("energy_components") or {}).get(
        "electricity"
    ) or {}
    return _f(electricity.get("amount")) > 0


def _hotel_water_applicable(
    spec: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    """5.3.2 只使用水量完整的年度。"""
    notes = result.get("notes") or {}
    if "water_complete" in notes:
        return bool(notes["water_complete"])
    if notes.get("water_missing") is True:
        return False
    source = _year_spec(spec, result.get("year"))
    if source:
        return _f(source.get("water_t")) > 0
    return _f((result.get("values") or {}).get("water_per_bed")) > 0


def _unit_energy_table(
    spec: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    """表 5.2：按能源品种分行列示实物量和折标准煤系数。"""
    headers = ["项目"] + [f"{r['year']}年" for r in results]
    component_specs = (
        ("electricity", "年耗电量（kWh）",
         "折标准煤系数（kgce/kWh）"),
        ("natural_gas", "年天然气消耗量（m³）",
         "折标准煤系数（kgce/m³）"),
        ("heat", "年供热量（GJ）",
         "折标准煤系数（kgce/GJ）"),
        ("new_water", "年取水量（m³）",
         "折标准煤系数（kgce/t）"),
        ("other", "其他能源折标准煤量（kgce）", "折标准煤系数"),
    )
    rows: list[list[Any]] = []
    for key, amount_label, coefficient_label in component_specs:
        component_rows = [
            (r.get("notes") or {}).get("energy_components", {}).get(key) or {}
            for r in results
        ]
        if key not in ("electricity", "new_water") and not any(
            _f(item.get("amount")) > 0 or _f(item.get("kgce")) > 0
            for item in component_rows
        ):
            continue
        amount_values: list[Any] = []
        for result, item in zip(results, component_rows):
            notes = result.get("notes") or {}
            if key == "new_water" and notes.get(
                "water_missing", not bool(item)
            ):
                amount_values.append("—")
            else:
                amount_values.append(
                    _num(round(_f(item.get("amount")), 2))
                    if item
                    else "—"
                )
        rows.append([amount_label] + amount_values)
        rows.append(
            [coefficient_label]
            + [
                _num(round(_f(item.get("coefficient")), 4))
                if item else "—"
                for item in component_rows
            ]
        )

    total_tce: list[Any] = []
    area_values: list[Any] = []
    unit_values: list[Any] = []
    for result in results:
        notes = result.get("notes") or {}
        components = notes.get("energy_components") or {}
        energy_kgce = _f(notes.get("energy_kgce"))
        if not energy_kgce:
            energy_kgce = sum(
                _f(item.get("kgce")) for item in components.values()
            )
        total_tce.append(_num(round(energy_kgce / 1000, 2)))
        area_values.append(
            _num(round(_f(notes.get("area_mm"), _f(spec.get("area_m2"))), 2))
        )
        unit_values.append(_num(result.get("values", {}).get("unit_energy", "—")))
    rows.extend(
        [
            ["综合能耗（tce）"] + total_tce,
            ["建筑面积统计值（m²）"] + area_values,
            ["单位综合能耗（kgce/m²）"] + unit_values,
        ]
    )
    return _table(headers, rows)


def _metric_table(metric_key: str, label: str, unit: str,
                  results: list[dict[str, Any]], hotel: bool,
                  spec: dict[str, Any] | None = None) -> str:
    if not results:
        return "暂无可纳入对标评价的完整年度数据。"
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

    if hotel and metric_key == "unit_comparable_energy":
        component_rows = []
        area_values = []
        unit_energy_values = []
        correction_labels = {
            "laundry": "洗衣房修正系数",
            "pool": "恒温游泳池和恒温水池修正系数",
            "heat_network": "热力管网修正系数",
            "floor_area_ratio": "建筑容积率修正系数",
            "dining_meeting_ratio": "餐饮、会议设施面积占比修正系数",
            "occupancy": "客房出租率修正系数",
        }
        correction_keys: list[str] = []
        for result in results:
            notes = result.get("notes") or {}
            components = notes.get("energy_components") or {}
            energy_kgce = _f(notes.get("energy_kgce")) or sum(
                _f(item.get("kgce")) for item in components.values()
            )
            component_rows.append(_num(round(energy_kgce / 1000, 2)))
            area_values.append(
                _num(round(
                    _f(
                        notes.get("area_mm"),
                        _f((spec or {}).get("area_m2")),
                    ),
                    2,
                ))
            )
            unit_energy_values.append(
                _num(result.get("values", {}).get("unit_energy", "—"))
            )
            for key in (notes.get("correction_factors") or {}):
                if key not in correction_keys:
                    correction_keys.append(key)
        rows.extend(
            [
                ["综合能耗（tce）"] + component_rows,
                ["建筑面积统计值（m²）"] + area_values,
                ["单位综合能耗（kgce/m²）"] + unit_energy_values,
            ]
        )
        correction_values = {
            key: [
                _f(
                    (r.get("notes") or {})
                    .get("correction_factors", {})
                    .get(key, "—")
                )
                for r in results
            ]
            for key in correction_keys
        }
        for key in correction_keys:
            rows.append(
                [correction_labels.get(key, key)]
                + [f"{value:.2f}" for value in correction_values[key]]
            )
        correction_products = [
            _f((r.get("notes") or {}).get("correction_product"))
            for r in results
        ]
        rows.append(
            ["修正系数连乘值"]
            + [f"{value:.2f}" for value in correction_products]
        )
        # 基础数据 → 指标 → 对标 → 评价；指标行不能跑到基础数据之前。
        rows = rows[1:] + [rows[0]]
    elif hotel and metric_key == "water_per_bed":
        water_values = []
        bed_values = []
        occupancy_values = []
        for result in results:
            source = _year_spec(spec or {}, result["year"])
            water_values.append(_num(round(_f(source.get("water_t")), 2)))
            bed_values.append(_num(round(_f(source.get("beds")), 2)))
            occupancy_values.append(
                _num(round(_f(source.get("occupancy")) * 100, 2))
            )
        rows = [
            ["年度用水量（m³）"] + water_values,
            ["总床位数（床）"] + bed_values,
            ["宾馆床位出租率（%）"] + occupancy_values,
            [f"{label}（{unit}）"] + values,
        ]

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
    base_results = [
        result for result in results
        if _year_int(result.get("year")) not in blocked_years
    ]
    energy_results = base_results
    water_results = base_results
    electricity_years = [
        year for year in table_years
        if _electricity_complete(year)
    ]
    partial_electricity_years = [
        year
        for year in table_years
        if not _electricity_complete(year)
    ]
    complete_electricity_year_values = [
        _year_int(year.get("year")) for year in electricity_years
    ]
    partial_electricity_year_values = [
        _year_int(year.get("year")) for year in partial_electricity_years
    ]
    missing_water_years: list[Any] = []
    if hotel:
        missing_water_years = [
            result["year"]
            for result in base_results
            if not _hotel_water_applicable(spec, result)
        ]
        energy_results = [
            result for result in base_results
            if _hotel_energy_applicable(spec, result)
        ]
        water_results = [
            result for result in base_results
            if _hotel_water_applicable(spec, result)
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
    ]

    if hotel:
        complete_electricity_text = "、".join(
            f"{year}年"
            for year in complete_electricity_year_values
            if year is not None
        )
        if complete_electricity_text:
            scope_sentence = (
                f"电量数据完整的{complete_electricity_text}纳入用电分析。"
            )
            partial_text = "、".join(
                f"{year}年"
                for year in partial_electricity_year_values
                if year is not None
            )
            if partial_text:
                scope_sentence += (
                    f"{partial_text}电量记录不足12个月，仅作正文说明。"
                )
            missing_water_text = "、".join(
                f"{year}年"
                for year in missing_water_years
                if _year_int(year) is not None
            )
            if missing_water_text:
                scope_sentence += (
                    f"{missing_water_text}未形成独立新水计量，仍纳入用电分析、"
                    "5.3.1单位综合能耗计算和评价；该年取水量及新水折标量以"
                    "“—”表示，不纳入5.3.2用水指标评价。"
                )
            lines += [scope_sentence, ""]

    lines += [
        "## 5.2 能源资源消耗/消费数据",
        "",
        "### 5.2.1 用电情况分析",
        "",
    ]

    elec_rows = []
    for y in electricity_years:
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
        water_value = (
            f"{_f(y.get('water_t')):.0f}"
            if _f(y.get("water_t")) > 0
            else "—"
        )
        water_rows.append([
            f"{y.get('year')}年",
            water_value,
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
        water_cost = (
            f"{_f(y.get('water_cost_wan')):.2f}"
            if _f(y.get("water_t")) > 0
            else "—"
        )
        cost_rows.append([
            f"{y.get('year')}年",
            f"{_f(y.get('electricity_cost_wan')):.2f}",
            water_cost,
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
    table_no = 2
    for idx, (key, label, unit) in enumerate(metrics, 1):
        if hotel and idx == 1:
            metric_results = energy_results
        elif hotel and idx == 2:
            metric_results = water_results
        else:
            metric_results = results
        table_metric_results = (
            metric_results if hotel else base_results
        )
        lines += [f"### 5.3.{idx} {label}", ""]
        if hotel and idx == 1:
            lines += [
                f"本指标依据{DB33_T_760_2023}计算。",
                "",
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
                "单位综合能耗是计算单位可比综合能耗的中间量，"
                "按下列公式计算：",
                "",
                "[FORMULA7]",
                "",
                "式中：",
                "",
                "E_{j}——单位综合能耗，单位为千克标准煤每平方米"
                "（kgce/m²）；",
                "E——综合能耗，即各类能源实物量与其折标准煤系数"
                "乘积之和，单位为千克标准煤（kgce）；",
                "M_{m}——建筑面积统计值，单位为平方米（m²）。",
                "",
            ]
            if missing_water_years:
                missing_label = "、".join(
                    f"{year}年" for year in missing_water_years
                )
                lines += [
                    f"{missing_label}电量数据完整，仍纳入"
                    f"{DB33_T_760_2023}单位综合能耗计算和评价；该年未形成"
                    "独立新水计量，年取水量及新水折标量以“—”表示，"
                    "评价反映已计量的电力部分，且不纳入5.3.2用水指标评价。",
                ]
            else:
                lines += ["电量完整年度单位综合能耗计算结果见表5.2。"]
            lines += [
                "",
                "表5.2 单位综合能耗",
                "",
                (
                    _unit_energy_table(spec, energy_results)
                    if energy_results
                    else "暂无可纳入760单位综合能耗计算的完整电量年度数据。"
                ),
                "",
                "以单位综合能耗为中间量，按修正系数连乘值折算后，"
                "电量完整年度单位可比综合能耗计算结果见表5.3。",
                "",
            ]
            table_no = 3
        elif hotel and key == "water_per_bed":
            water_notes = (
                (water_results or results)[0].get("notes") or {}
            )
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
                f"统计结果见表5.{table_no}。",
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
                f"{label}按标准口径计算，统计结果见表5.{table_no}。",
                "",
            ]
        lines += [
            f"表5.{table_no} {label}",
            "",
            _metric_table(
                key, label, unit, table_metric_results, hotel, spec
            ),
            "",
        ]
        table_no += 1
        if hotel and idx == 1:
            lines += [
                "单位综合能耗 E_{j} 仅为计算单位可比综合能耗的中间量，"
                "不作为独立评价指标。",
                "",
            ]
        sentences = []
        narrative_results = metric_results if hotel else results
        for r in narrative_results:
            value = r["values"].get(key)
            grade = r["grade"].get("water" if (hotel and key == "water_per_bed") else key, "—")
            if hotel and key == "unit_comparable_energy":
                grade = LEGACY_760_GRADES.get(str(grade), grade)
            if key in ("unit_water", "water_per_bed") and _f(value) == 0:
                value = "—"
            sentences.append(f"{r['year']}年为{value}{unit}，{grade}")
        if sentences:
            metric_year_label = "、".join(
                f"{r['year']}年" for r in narrative_results
            )
            lines += [
                f"{unit_name}{metric_year_label}{label}分别为：" +
                "；".join(sentences) + "。",
                "",
            ]
        else:
            metric_year_label = "、".join(
                f"{r['year']}年" for r in narrative_results
            ) or year_label
            lines += [
                f"{unit_name}{metric_year_label}{label}因完整口径数据不足，"
                "本次不开展对标评价。",
                "",
            ]

    return "\n".join(lines)
