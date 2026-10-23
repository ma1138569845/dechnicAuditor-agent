# -*- coding: utf-8 -*-
"""按标准包生成第 5 章，不混用省份指标与评价档位。"""
from __future__ import annotations

from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    lines.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(lines)


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


def _metric_table(
    metric: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    key = metric["key"]
    unit = metric["unit"]
    headers = ["项目"] + [f"{row.get('year')}年" for row in results]
    values = []
    for row in results:
        value = row.get("values", {}).get(key, "—")
        if value in (None, ""):
            value = "—"
        values.append(_num(value))
    rows: list[list[Any]] = [[f"{metric['label']}（{unit}）", *values]]
    labels = metric.get("tier_labels") or ["约束值", "基准值", "引导值"]

    tier_sets: list[tuple[Any, ...]] = []
    for row in results:
        tiers = (row.get("quota") or {}).get(key) or []
        tier_sets.append(tuple(tiers))

    for index, label in enumerate(labels):
        tier_values = [
            _num(tiers[index]) if index < len(tiers) else "—"
            for tiers in tier_sets
        ]
        rows.append([f"{label}（{unit}）", *tier_values])
    grade_key = metric.get("grade_key") or key
    rows.append([
        "评价结果",
        *[
            row.get("grade", {}).get(grade_key, "—")
            for row in results
        ],
    ])
    table = _table(headers, rows)
    if len(set(tier_sets)) > 1:
        table += "\n\n注：各年度限额依据该年度实际使用强度修正后分别列示。"
    return table


def render(
    *,
    spec: dict[str, Any],
    results: list[dict[str, Any]],
    unit_name: str,
    standard_id: str,
    standard_title: str,
    metrics: list[dict[str, Any]],
    figures_manifest: dict[str, Any] | None = None,
) -> str:
    years = [row.get("year") for row in results]
    year_label = "、".join(str(year) for year in years)
    flow_fig = _manifest_figure(figures_manifest, "energy_flow")
    lines: list[str] = [
        "# 第5章 能源资源消费/消耗指标分析",
        "",
        (
            f"本章依据 {standard_id}《{standard_title}》，基于{unit_name}"
            f"{year_label}年的能源账单、计量记录及运行资料，对能源资源消费、"
            "指标水平和对标结果进行分析。"
        ),
        "",
        "## 5.1 能源资源消费/消耗概况",
        "",
    ]
    if flow_fig:
        lines += [
            f"{unit_name}的能源资源流向如{_figure_no(flow_fig)}所示。",
            "",
            flow_fig["caption"],
            "",
        ]
    else:
        lines += [
            f"{unit_name}的能源资源流向按项目实际能源品种汇总，"
            "缺少流向图时保留本节文字说明，不虚构图形。",
            "",
        ]

    lines += ["## 5.2 能源资源消费/消耗数据", "", "### 5.2.1 用电情况分析", ""]
    electricity_rows = [
        [
            f"{row.get('year')}年",
            f"{_f(row.get('electricity_kwh')):.0f}",
            f"{_f(row.get('electricity_cost_wan')):.2f}"
            if row.get("electricity_cost_wan") else "—",
        ]
        for row in spec.get("years", [])
    ]
    lines += [
        _table(["年份", "用电量（kWh）", "电费（万元）"], electricity_rows),
        "",
    ]
    total_e = _manifest_figure(figures_manifest, "total", "electricity")
    monthly_e = _manifest_figure(figures_manifest, "monthly", "electricity")
    refs = []
    if total_e:
        refs.append(f"年用电量变化趋势如{_figure_no(total_e)}所示")
    if monthly_e:
        refs.append(f"逐月用电情况如{_figure_no(monthly_e)}所示")
    if refs:
        lines += ["，".join(refs) + "。", ""]
    lines += [fig["caption"] + "\n" for fig in (total_e, monthly_e) if fig]

    lines += ["### 5.2.2 用水情况分析", ""]
    water_rows = [
        [
            f"{row.get('year')}年",
            f"{_f(row.get('water_t')):.0f}",
            f"{_f(row.get('water_cost_wan')):.2f}"
            if row.get("water_cost_wan") else "—",
        ]
        for row in spec.get("years", [])
    ]
    lines += [
        _table(["年份", "用水量（m³）", "水费（万元）"], water_rows),
        "",
    ]
    total_w = _manifest_figure(figures_manifest, "total", "water")
    monthly_w = _manifest_figure(figures_manifest, "monthly", "water")
    refs = []
    if total_w:
        refs.append(f"年用水量变化趋势如{_figure_no(total_w)}所示")
    if monthly_w:
        refs.append(f"逐月用水情况如{_figure_no(monthly_w)}所示")
    if refs:
        lines += ["，".join(refs) + "。", ""]
    lines += [fig["caption"] + "\n" for fig in (total_w, monthly_w) if fig]

    lines += ["### 5.2.3 其他用能分析", ""]
    other_rows = [
        [
            f"{row.get('year')}年",
            f"{_f(row.get('gas_m3')):.0f}",
            f"{_f(row.get('heat_gj')):.2f}",
        ]
        for row in spec.get("years", [])
    ]
    lines += [
        _table(["年份", "天然气（m³）", "供热量（GJ）"], other_rows),
        "",
        "其他能源品种按项目实际计量数据统计；未独立计量的品种在口径说明中披露，不以估算值替代实测值。",
        "",
    ]

    lines += ["### 5.2.4 能源资源费用分析", ""]
    cost_rows = [
        [
            f"{row.get('year')}年",
            f"{_f(row.get('electricity_cost_wan')):.2f}",
            f"{_f(row.get('water_cost_wan')):.2f}",
            f"{_f(row.get('gas_cost_wan')):.2f}",
            f"{_f(row.get('heat_cost_wan')):.2f}",
        ]
        for row in spec.get("years", [])
    ]
    lines += [
        _table(
            ["年份", "电费（万元）", "水费（万元）", "燃气费（万元）", "热费（万元）"],
            cost_rows,
        ),
        "",
    ]
    pie_figures = [
        _manifest_figure(figures_manifest, "cost_pie", year=str(year))
        for year in years
    ]
    pie_figures = [figure for figure in pie_figures if figure]
    if pie_figures:
        lines += ["各年度能源资源费用结构如下。", ""]
        lines += [figure["caption"] + "\n" for figure in pie_figures]
    else:
        lines += ["费用结构按项目实际费用数据列示，缺少费用分项时不绘制虚构饼图。", ""]

    lines += ["## 5.3 能耗资源消耗/消费指标", ""]
    for index, metric in enumerate(metrics, 1):
        label = metric["label"]
        lines += [
            f"### 5.3.{index} {label}",
            "",
            f"{label}依据 {standard_id} {metric.get('anchor', '')} 计算，结果见表5.{index}。",
            "",
            f"表5.{index} {label}",
            "",
            _metric_table(metric, results),
            "",
        ]
        sentences = []
        for row in results:
            value = row.get("values", {}).get(metric["key"])
            if value is None:
                sentences.append(f"{row.get('year')}年无完整数据，不评价")
                continue
            grade = row.get("grade", {}).get(
                metric.get("grade_key") or metric["key"], "—"
            )
            sentences.append(
                f"{row.get('year')}年为{_num(value)} {metric['unit']}，{grade}"
            )
        lines += [
            f"{unit_name}{year_label}年{label}分别为：" + "；".join(sentences) + "。",
            "",
        ]
        note = metric.get("note")
        if note:
            lines += [note, ""]
    return "\n".join(lines).rstrip() + "\n"
