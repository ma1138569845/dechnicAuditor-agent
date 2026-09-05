"""
第5章子Agent v2 —— 能源资源消费/消耗指标分析

完整结构：
  总述 → 5.1概况(流向图+饼图) → 5.2数据(按类型动态H3+费用) → 5.3指标 → 5.4建筑能耗基准

数据来源：ts_institution_energy_main + ts_institution_energy_data (data_type: 1=能耗,2=费用,3=供冷,4=供热,5=交通)
备选：Excel / 手动输入
"""

import argparse, json, os, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401

from tools.energy_audit.chart_utils import setup_chart_font, chart_text

from tools.energy_audit.indicators import (
    YearlyEnergyData,
    calc_unit_area_non_heating_energy,
    calc_unit_area_electricity,
    calc_per_capita_energy,
    calc_water_indicator,
    calc_baseline,
    institution_category_to_type,
    COEFFICIENTS,
)

# 能源类型中英文映射（使用 indicators 中的标准 key）
_ENERGY_CN_MAP = {
    'electricity': '电', 'water': '水', 'natural_gas': '天然气',
    'heat': '热', 'diesel': '柴油', 'gasoline': '汽油',
}

# 5.2 小节标题用名（正式报告"用电/用水/用热/用气情况分析"）
_TITLE_NAME = {
    'electricity': '电', 'water': '水', 'natural_gas': '气',
    'heat': '热', 'diesel': '油', 'gasoline': '油',
}

# 原始 energy_code → indicators 标准 key 的映射
def _normalize_energy_code(code: str) -> str:
    code = str(code or '').strip().lower()
    mapping = {
        'electricity': 'electricity', '45': 'electricity', '电能': 'electricity',
        'water': 'water', '01': 'water', '水': 'water',
        'natural_gas': 'natural_gas', '25': 'natural_gas', '天然气': 'natural_gas',
        'heat': 'heat', '50': 'heat', '热能': 'heat', '供热': 'heat', '热量': 'heat',
        'diesel': 'diesel', '300302': 'diesel', '柴油': 'diesel',
        'gasoline': 'gasoline', 'petrol': 'gasoline', '300301': 'gasoline', '汽油': 'gasoline',
    }
    return mapping.get(code, code)


def _coeff_info(energy_type: str) -> dict:
    """返回能源类型的中文/单位/折标系数信息（基于 indicators.COEFFICIENTS）。"""
    std = _normalize_energy_code(energy_type)
    name = _ENERGY_CN_MAP.get(std, energy_type)
    unit_map = {
        'electricity': 'kWh', 'water': 'm³', 'natural_gas': 'm³',
        'heat': 'GJ', 'diesel': 'kg', 'gasoline': 'kg',
    }
    coeff = COEFFICIENTS.get(std, 0)
    return {
        'name': name,
        'unit': unit_map.get(std, ''),
        'coeff': coeff,
        'display': f"{'kgce' if std != 'heat' else 'tce'}/{unit_map.get(std, '')}",
    }


# ============================================================
# 数据加载
# ============================================================

def load_from_db(config: dict) -> dict:
    """从 ts_institution_energy_main + ts_institution_energy_data 加载能耗和费用数据"""
    from tools.energy_audit.pg_query import PgDataQuery
    from tools.energy_audit.db_config import get_pg_config
    # 调用方 config['database'] 为显式覆盖；缺项/未提供时走统一解析链
    db_cfg = get_pg_config(config.get('database'))

    with PgDataQuery(db_cfg) as db:
        customer_id = config.get('customer_id')
        y1, y2 = int(config['year_start']), int(config['year_end'])

        # 新两表结构统一查询：value1..value12 由 period_code 展开生成（见 pg_query）
        rows = db.get_institution_energy(customer_id=customer_id)

        # 建筑表：聚合供热面积（5.3.5 采暖建筑面积；部分建筑供暖项目不能拿总面积兜底）
        # 权威源 ts_institution_build.heat_area；查询失败/全 0 时上层再走建筑总面积兜底
        heating_area = 0.0
        try:
            buildings = db.get_institution_build(customer_id=customer_id)
            heating_area = sum(float(b.get('heat_area') or 0) for b in buildings)
        except Exception:
            heating_area = 0.0

    def _in_range(r):
        try:
            y = int(r.get('year') or 0)
        except (TypeError, ValueError):
            return False
        return y1 <= y <= y2

    # 1. 能耗 (data_type=1)  2. 费用 (data_type=2)  3. 分项 (data_type=3,4,5)
    energy_rows = [r for r in rows if str(r.get('data_type')) == '1' and _in_range(r)]
    cost_rows = [r for r in rows if str(r.get('data_type')) == '2' and _in_range(r)]
    sub_rows = [r for r in rows if str(r.get('data_type')) in ('3', '4', '5') and _in_range(r)]

    # 整理为结构化数据
    energy_data = {}  # {year: {energy_code: {name, unit, monthly: [v1..v12], total, building_total?}}}
    cost_data = {}    # 同上
    for r in energy_rows:
        y = str(r['year'])
        code = r['energy_code']
        entry = {
            'name': r['energy_name'] or '',
            'unit': r['energy_unit'] or '',
            'monthly': [float(r.get(f'value{i}', 0) or 0) for i in range(1, 13)],
            'total': float(r['unit_total_value'] or 0),
        }
        # 合署办公追溯：整栋建筑用量 > 本单位用量时记录
        building_total = float(r.get('building_total_value') or 0)
        if building_total > entry['total'] > 0:
            entry['building_total'] = building_total
            entry['co_location_ratio'] = round(building_total / entry['total'], 2)
        energy_data.setdefault(y, {})[code] = entry
    for r in cost_rows:
        y = str(r['year'])
        code = r['energy_code']
        cost_data.setdefault(y, {})[code] = {
            'name': r['energy_name'] or '',
            'unit': '万元',
            'monthly': [float(r.get(f'value{i}', 0) or 0) for i in range(1, 13)],
            'total': float(r['unit_total_value'] or 0),
        }

    sub_items = {}  # {year: {data_type: unit_total_value}}
    for r in sub_rows:
        y = str(r['year'])
        dt = r['data_type']
        sub_items.setdefault(y, {})[f'data_type_{dt}'] = float(r['unit_total_value'] or 0)

    return {
        'energy_data': energy_data,
        'cost_data': cost_data,
        'sub_items': sub_items,
        'heating_area': heating_area,
        'from_db': True,
    }


def load_from_user(config: dict) -> dict:
    """用户手动输入或Excel提供的数据"""
    manual = config.get('manual', {})
    return {
        'energy_data': manual.get('energy_data', {}),
        'cost_data': manual.get('cost_data', {}),
        'sub_items': manual.get('sub_items', {}),
        'heating_area': float(config.get('heating_area', 0) or 0),
        # 供暖电耗明细（kWh，总电的子集，须从总电量剔除后计非供暖能耗）
        'heating_energy_kwh_map': config.get('heating_energy_kwh_map', {}) or {},
        'from_db': False,
    }


# ============================================================
# 数据转换与计算（统一复用 indicators.py）
# ============================================================

def _convert_to_yearly_energy_data(energy_data: dict, config: dict) -> List[YearlyEnergyData]:
    """把 chapter5_agent 的 energy_data 结构转换为 indicators.YearlyEnergyData 列表。"""
    area = config.get('building_area', 0)
    people = config.get('people_count', 0)

    yd_list = []
    for y in sorted(energy_data.keys()):
        y_data = energy_data.get(y, {})
        kwargs = {
            'year': int(y),
            'building_area': float(area),
            'people_count': float(people),
        }
        for code, info in y_data.items():
            std = _normalize_energy_code(code)
            val = float(info.get('total', 0) or 0)
            if std == 'electricity':
                kwargs['electricity_kwh'] = kwargs.get('electricity_kwh', 0) + val
            elif std == 'water':
                kwargs['water_m3'] = kwargs.get('water_m3', 0) + val
            elif std == 'natural_gas':
                kwargs['natural_gas_m3'] = kwargs.get('natural_gas_m3', 0) + val
            elif std == 'heat':
                kwargs['heating_energy_heat'] = kwargs.get('heating_energy_heat', 0) + val
            elif std == 'gasoline':
                kwargs['transportation_petrol_kg'] = kwargs.get('transportation_petrol_kg', 0) + val
            elif std == 'diesel':
                kwargs['transportation_diesel_kg'] = kwargs.get('transportation_diesel_kg', 0) + val
        yd_list.append(YearlyEnergyData(**kwargs))
    return yd_list


def calc_yearly_tce(energy_data: dict, years: list) -> dict:
    """计算每年总TCE（复用 indicators.YearlyEnergyData.total_energy_tce）。"""
    config = {'building_area': 0, 'people_count': 0}
    yd_list = _convert_to_yearly_energy_data(energy_data, config)
    return {str(yd.year): yd.total_energy_tce for yd in yd_list}


def _co_location_note(en: dict, year: str, codes: list, unit_name: str) -> str:
    """生成合署办公追溯说明（仅当存在 building_total > unit_total 时输出）。

    数据来源说明：ts_institution_energy_main 同时维护两个值 —
      total_value = 整栋建筑的合署办公总量
      real_value  = 本单位实际用量（本次审计目标值）
    """
    y_data = en.get(year, {})
    notes = []
    for code in codes:
        info = y_data.get(code, {})
        building = info.get('building_total', 0)
        unit = info.get('total', 0)
        if building > unit > 0:
            c = _coeff_info(code)
            ratio = round(building / unit, 2)
            notes.append(
                f"- **{c['name']}**：整栋建筑共消耗 **{building:,.2f} {c['unit']}**，"
                f"其中{unit_name}实际用量 **{unit:,.2f} {c['unit']}**（合署比 {ratio}，即建筑总量是本单位用量的 {ratio} 倍）"
            )
    if not notes:
        return ""
    header = "**📌 合署办公场景说明**：本审计周期内，能源消耗数据涉及合署办公情形，"\
             "DB 中 `ts_institution_energy_main` 同时维护两个数值字段：\n\n"\
             "- `total_value`：整栋建筑的合署办公总量（含同楼其他单位）\n"\
             "- `real_value`：本次审计对象的本单位实际用量（审计报告目标值）\n\n"\
             "本报告所有指标均以 `real_value` 为准。各能源合署情况如下：\n\n"
    return header + "\n".join(notes) + "\n\n"


# ============================================================
# Markdown 生成
# ============================================================

def generate_chapter5_md(data: dict, config: dict) -> str:
    en = data.get('energy_data', {})
    co = data.get('cost_data', {})
    years = sorted(en.keys())
    if not years:
        return "# 第5章\n\n无数据，请提供能耗数据。\n"

    years_short = [y[:4] for y in years]
    area = config.get('building_area', 0)
    people = config.get('people_count', 0)
    unit_name = config.get('unit_name', '被审计单位')

    # 收集所有能源代码
    all_codes = set()
    for y_data in en.values():
        all_codes.update(y_data.keys())
    all_codes = sorted(all_codes)

    year_tce = calc_yearly_tce(en, years)
    md = f"# 第5章 能源资源消费/消耗指标分析\n\n"

    # ===== 总述 =====
    md += f"为全面准确分析{unit_name}用能情况和用能规律，此次能源审计工作选取{unit_name}"
    md += f"{years_short[0]}年-{years_short[-1]}年完整年周期内"
    md += "、".join([_coeff_info(c)['name'] for c in all_codes])
    md += f"等用能数据，并根据近三年总用能及各项用能数据进行计算分析。\n\n"

    # ===== 5.1 概况 =====
    md += "## 5.1 能源资源消费/消耗概况\n\n"
    md += f"{unit_name}主要用能类型包括"
    md += "、".join([_coeff_info(c)['name'] for c in all_codes])
    md += "。能源资源流向如图5.1所示。\n\n"
    chart_dir = config.get('chart_dir', './charts')
    if os.path.exists(os.path.join(chart_dir, 'energy_flow.png')):
        md += "![图5.1 能源资源流向图](charts/energy_flow.png)\n\n"

    # 各类型消费总量（写作参考，正式报告 5.1 无此表）
    latest_year = years[-1]
    md += f"**能源消费结构（写作参考，不占正式表号）**\n\n"
    md += "| 能源类型 | 消耗量 | 单位 | 折标系数 | 折标煤量(tce) | 占比 |\n"
    md += "|----------|--------|------|----------|---------------|------|\n"
    total_tce = year_tce[latest_year]
    for code in all_codes:
        info = en.get(latest_year, {}).get(code, {})
        total = info.get('total', 0)
        c = _coeff_info(code)
        std = _normalize_energy_code(code)
        coeff = c['coeff'] * 1000 if std == 'heat' else c['coeff']
        tce_val = round(total * coeff / 1000, 2)
        pct = round(tce_val / total_tce * 100, 1) if total_tce else 0
        md += f"| {c['name']} | {total:,.2f} | {c['unit']} | {c['display']} | {tce_val:,.2f} | {pct}% |\n"
    md += f"\n综合能耗总量：**{total_tce:,.2f} tce**\n\n"

    # ===== 合署办公追溯说明 =====
    md += _co_location_note(en, latest_year, all_codes, unit_name)

    # 逐年对比（写作参考）
    if len(years) > 1:
        md += f"**逐年能耗对比（写作参考，不占正式表号）**\n\n"
        header = "| 项目 | " + " | ".join(f"{y}年" for y in years) + " |\n"
        sep = "|------|" + "|".join(["------"] * len(years)) + "|\n"
        md += header + sep
        md += "| 综合能耗(tce) | " + " | ".join(f"{year_tce[y]:,.2f}" for y in years) + " |\n"
        md += "| 人均能耗(tce/人) | " + " | ".join(f"{year_tce[y]/people:.4f}" if people else "0" for y in years) + " |\n"
        md += "| 单位面积能耗(tce/m²) | " + " | ".join(f"{year_tce[y]/area:.4f}" if area else "0" for y in years) + " |\n\n"

    # ===== 5.2 数据（按类型动态H3） =====
    md += "## 5.2 能源资源消耗/消费数据\n\n"
    chart_dir = config.get('chart_dir', './charts')
    fig_no = 2  # 图5.1 已用于 5.1 概况；5.2 内图号连续递增

    # 主要能源分类（对齐正式报告 5.2 小节划分，公共函数）
    major_codes, minor_codes = _classify_energy_types(en, years)

    section_idx = 1
    for code in major_codes:
        c = _coeff_info(code)
        std = _normalize_energy_code(code)
        title_name = _TITLE_NAME.get(std, c['name'])
        section_num = f"5.2.{section_idx}"
        section_idx += 1
        md += f"### {section_num} 用{title_name}情况分析\n\n"

        # 逐年总量（写作参考数据行，正式报告 5.2 无表，author 转文字）
        vals_txt = "；".join(
            f"{str(y)[:4]}年{c['name']}量 {en.get(y, {}).get(code, {}).get('total', 0):,.2f} {c['unit']}"
            for y in years)
        md += f"**数据参考**：{vals_txt}\n\n"

        # 逐月数据参考行（有月度数据才输出，author 写逐月分析需精确值）
        monthly_ok = False
        monthly_rows = []
        for y in years:
            m = en.get(y, {}).get(code, {}).get('monthly', []) or []
            if any(float(v or 0) > 0 for v in m):
                monthly_ok = True
            monthly_rows.append((m + [0] * 12)[:12])
        if monthly_ok:
            fmt = ',.2f' if 'm³' in c['unit'] else ',.0f'
            for y, m in zip(years, monthly_rows):
                m_txt = " / ".join(f"{i + 1}月 {float(v or 0):{fmt}}" for i, v in enumerate(m))
                md += f"**逐月参考**：{str(y)[:4]}年 {m_txt}\n"
            md += "\n"

        # 三年总量柱状图 + 逐月分组柱状图（对齐正式报告：仅有月度数据的主要类型画图）
        if monthly_ok:
            if os.path.exists(os.path.join(chart_dir, f'chart_{code}_total.png')):
                y1, y3 = str(years[0])[:4], str(years[-1])[:4]
                md += f"![图5.{fig_no} {y1}年-{y3}年总用{title_name}量（单位：{c['unit']}）](charts/chart_{code}_total.png)\n\n"
                fig_no += 1
            if os.path.exists(os.path.join(chart_dir, f'chart_{code}_monthly.png')):
                y1, y3 = str(years[0])[:4], str(years[-1])[:4]
                md += f"![图5.{fig_no} {y1}年-{y3}年逐月用{title_name}量（单位：{c['unit']}）](charts/chart_{code}_monthly.png)\n\n"
                fig_no += 1

    # 其他用能分析（次要能源合并小节，正式报告 5.2.4 结构）
    if minor_codes:
        section_num = f"5.2.{section_idx}"
        section_idx += 1
        md += f"### {section_num} 其他用能分析\n\n"
        for code in minor_codes:
            c = _coeff_info(code)
            vals_txt = "；".join(
                f"{str(y)[:4]}年{c['name']}量 {en.get(y, {}).get(code, {}).get('total', 0):,.2f} {c['unit']}"
                for y in years)
            md += f"- {c['name']}：{vals_txt}\n"
        md += "\n"

    # 费用分析（最后一节）
    cost_section_num = f"5.2.{section_idx}"
    md += f"### {cost_section_num} 能源资源费用分析\n\n"
    if co:
        md += f"**表5.1 各项能源费用统计表**\n\n"
        cost_header = "| 费用类型 |"
        cost_sep = "|------|"
        for y in years:
            cost_header += f" {str(y)[:4]}年(万元) |"
            cost_sep += "------|"
        md += cost_header + "\n" + cost_sep + "\n"
        for code in all_codes:
            c = _coeff_info(code)
            row = f"| {c['name']}费 |"
            for y in years:
                val = co.get(y, {}).get(code, {}).get('total', 0)
                row += f" {val:,.2f} |"
            md += row + "\n"
        md += "\n"
        # 能源费用占比饼图（每年一张，连号，与正式报告一致）
        pie_no = fig_no
        for y in years:
            y4 = str(y)[:4]
            if not os.path.exists(os.path.join(chart_dir, f'cost_pie_{y4}.png')):
                continue
            md += f"![图5.{pie_no} {y4}年能源费用占比](charts/cost_pie_{y4}.png)\n\n"
            pie_no += 1
    else:
        md += "（费用数据待用户提供）\n\n"

    # ===== 5.3 指标（统一复用 indicators.py） =====
    md += "## 5.3 能耗资源消耗/消费指标\n\n"

    # 统一转换为 YearlyEnergyData 并计算指标
    institution_type = institution_category_to_type(config.get('institution_category', ''))
    bed_count = config.get('beds_count', 0) or 0
    yd_list = _convert_to_yearly_energy_data(en, config)

    # 注入供暖电耗明细（energy_data dict 无法承载"总电的子集"，走 data 顶层 map 通道；
    # 缺失该 map 时供暖电耗=0 → 非供暖能耗未剔除供暖电耗，与 indicators.json 口径不一致）
    hk_map = data.get('heating_energy_kwh_map') or {}
    for yd in yd_list:
        hk = hk_map.get(str(yd.year))
        if hk:
            yd.heating_energy_kwh = float(hk)

    if not yd_list:
        md += "（无可用能耗数据，无法计算指标）\n\n"
    else:
        table_no = 2  # 表5.1 = 各项能源费用统计表（5.2 费用节）
        # 5.3.1 单位建筑面积非供暖能耗
        md += "### 5.3.1 单位建筑面积非供暖能耗\n\n"
        md += "单位建筑面积非供暖能耗 = (综合能耗 - 供暖能耗 - 交通能耗) / 建筑面积\n\n"
        md += f"**表5.{table_no} 单位建筑面积非供暖能耗**\n\n"
        table_no += 1
        md += "| 项目 | " + " | ".join(f"{y}年" for y in years) + " |\n"
        md += "|------|" + "|".join(["------"]*len(years)) + "|\n"
        row_nh = ["| 非供暖能耗(tce) |"]
        row_nh_m2 = ["| 单位面积非供暖能耗(kgce/m²) |"]
        row_nh_ev = ["| 评价结果 |"]
        for yd in yd_list:
            r = calc_unit_area_non_heating_energy(yd)
            if 'benchmark' not in r:
                from tools.energy_audit.indicators import compare_with_benchmark
                r['benchmark'] = compare_with_benchmark(r['kgce_per_m2'], institution_type=institution_type)
            row_nh.append(f" {r['non_heating_kgce']/1000:,.2f} |")
            row_nh_m2.append(f" {r['kgce_per_m2']:,.2f} |")
            row_nh_ev.append(f" {r['benchmark']['评价结果']} |")
        md += "".join(row_nh) + "\n"
        md += "".join(row_nh_m2) + "\n"
        md += "".join(row_nh_ev) + "\n\n"

        # 5.3.2 常规用能系统单位建筑面积电耗
        md += "### 5.3.2 常规用能系统单位建筑面积电耗\n\n"
        md += "常规用能系统单位建筑面积电耗 = 年总用电量 / 建筑面积\n\n"
        if area:
            md += f"**表5.{table_no} 常规用能系统单位建筑面积电耗**\n\n"
            table_no += 1
            md += "| 年度 | 用电量(kWh) | 单位面积电耗(kWh/m²) | 评价结果 |\n"
            md += "|------|-------------|---------------------|----------|\n"
            for yd in yd_list:
                r = calc_unit_area_electricity(yd, institution_type=institution_type)
                md += f"| {yd.year}年 | {r['total_electricity_kwh']:,.2f} | {r['kwh_per_m2']:,.2f} | {r['benchmark']['评价结果']} |\n"
        md += "\n"

        # 5.3.3 人均综合能耗
        md += "### 5.3.3 人均综合能耗\n\n"
        md += "人均综合能耗 = 综合能耗 / 用能人数\n\n"
        if people:
            md += f"**表5.{table_no} 人均综合能耗**\n\n"
            table_no += 1
            md += "| 年度 | 综合能耗(kgce) | 用能人数 | 人均综合能耗(kgce/人) | 评价结果 |\n"
            md += "|------|---------------|----------|----------------------|----------|\n"
            for yd in yd_list:
                r = calc_per_capita_energy(yd, institution_type=institution_type)
                md += f"| {yd.year}年 | {r['total_kgce']:,.2f} | {people} | {r['kgce_per_person']:,.2f} | {r['benchmark']['评价结果']} |\n"
        md += "\n"

        # 5.3.4 取水指标（公式按机构类型自适应，DB37/T 4452-2021）
        if institution_type == 'medical' and bed_count:
            md += "### 5.3.4 卫生业单位用水量\n\n"
            md += "单位开放床日用水量 = 年用水总量 / Σ全年实际开放床日数 × 10³（L/(床·d)，4452 式(5)；开放床日数缺失时按 床位数×365 近似）\n\n"
            md += f"**表5.{table_no} 卫生业单位用水量**\n\n"
            table_no += 1
            md += "| 年度 | 取水量(m³) | 床位数 | 单位开放床日用水量(L/床·d) | 评价结果 |\n"
            md += "|------|-----------|--------|---------------------------|----------|\n"
            for yd in yd_list:
                r = calc_water_indicator(yd, institution_type='medical', bed_count=bed_count)
                md += f"| {yd.year}年 | {r['total_water_m3']:,.2f} | {bed_count} | {r['L_per_bed_day']:,.2f} | {r['benchmark']['评价结果']} |\n"
        elif institution_type in ('venue', 'service') and area:
            md += "### 5.3.4 单位建筑面积年取水量\n\n"
            md += "单位建筑面积年取水量 = 年取水量 × 1000 / 建筑面积（L/(m²·a)，4452 式(6)；4452 无面积口径取水定额，不对标）\n\n"
            md += f"**表5.{table_no} 单位建筑面积年取水量**\n\n"
            table_no += 1
            md += "| 年度 | 取水量(m³) | 建筑面积(m²) | 单位建筑面积年取水量(L/(m²·a)) | 评价结果 |\n"
            md += "|------|-----------|--------------|--------------------------------|----------|\n"
            for yd in yd_list:
                r = calc_water_indicator(yd, institution_type=institution_type, building_area=area)
                md += f"| {yd.year}年 | {r['total_water_m3']:,.2f} | {area:,.0f} | {r['L_per_area']:,.2f} | — |\n"
        else:
            title = "人均用水量" if institution_type == 'education' else "人均机关取水量"
            md += f"### 5.3.4 {title}\n\n"
            if institution_type == 'education':
                md += "人均用水量 = 年取水量 / 标准人数（m³/(人·a)，4452 式(3)/(4)；高校标准人数=统招生+留学生+0.5×教职工，中小学/幼儿园标准人数=非住宿生+2×住宿生+教职工；人数细分数据缺失时用用能人数近似）\n\n"
            else:
                md += "人均机关取水量 = 年机关取水量 / 机关人数（m³/(人·a)，4452 式(7)）\n\n"
            if people:
                md += f"**表5.{table_no} {title}**\n\n"
                table_no += 1
                md += f"| 年度 | 取水量(m³) | 用能人数 | {title}(m³/(人·a)) | 评价结果 |\n"
                md += "|------|-----------|----------|-------------------|----------|\n"
                for yd in yd_list:
                    r = calc_water_indicator(yd, institution_type=institution_type)
                    md += f"| {yd.year}年 | {r['total_water_m3']:,.2f} | {people} | {r['m3_per_person']:,.2f} | {r['benchmark']['评价结果']} |\n"
        md += "\n"

        # 5.3.5 单位采暖建筑面积供暖能耗（有供暖能耗的项目必写；无供暖跳过）
        from tools.energy_audit.indicators import calc_unit_area_heating_energy
        has_heating = any((getattr(yd, 'heating_energy_heat', 0) or 0) > 0 or
                          (getattr(yd, 'heating_energy_kwh', 0) or 0) > 0 or
                          (getattr(yd, 'heating_energy_gas', 0) or 0) > 0 for yd in yd_list)
        if has_heating:
            # 采暖建筑面积兜底链：data 顶层(load_from_db 聚合) → data['buildings'] 聚合
            # (生产 data.json 权威) → 建筑总面积（2026-09-02 用户确认口径）
            heating_area = ((data.get('heating_area', 0) or 0)
                            or sum(float(b.get('heating_area') or 0)
                                   for b in (data.get('buildings') or []))
                            or area)
            md += "### 5.3.5 单位采暖建筑面积供暖能耗\n\n"
            md += "单位采暖建筑面积供暖能耗 = 供暖能耗 / 采暖建筑面积\n\n"
            md += f"**表5.{table_no} 单位采暖建筑面积供暖能耗**\n\n"
            table_no += 1
            md += "| 年度 | 供暖能耗(tce) | 采暖建筑面积(m²) | 单位面积供暖能耗(kgce/m²) | 评价结果 |\n"
            md += "|------|---------------|------------------|---------------------------|----------|\n"
            for yd in yd_list:
                r = calc_unit_area_heating_energy(yd, heating_area=heating_area,
                                                  institution_type=institution_type)
                ev = r['benchmark']['评价结果'] if r.get('benchmark') else '—'
                md += f"| {yd.year}年 | {r['heating_energy_kgce']/1000:,.2f} | {r['heating_area_m2']:,.0f} | {r['kgce_per_m2']:,.2f} | {ev} |\n"
            md += "\n"

    # ===== 5.4 建筑能耗基准（复用 indicators.calc_baseline） =====
    md += "## 5.4 建筑能耗基准\n\n"

    # 5.4.1 用量基准
    md += "### 5.4.1 能源资源用量基准\n\n"
    md += "根据《山东省公共建筑节能改造节能量核定办法》（试行），各年能耗波动范围在±10%以内时，"
    md += "取三年平均值作为基准年能耗。\n\n"
    bl = calc_baseline(yd_list) if yd_list else {'usage': {}, 'cost': {}}
    md += f"**表5.{table_no} 能源资源用量基准表**\n\n"
    table_no += 1
    md += "| 能源类型 | 用量基准 | 单位 | 计算方法 |\n"
    md += "|----------|----------|------|----------|\n"
    for label, info in bl.get('usage', {}).items():
        md += f"| {label} | {info['基准值']:,.2f} | {info.get('单位', '')} | {info.get('方法', '')} |\n"
    if not bl.get('usage'):
        for code in all_codes:
            vals = [en.get(y, {}).get(code, {}).get('total', 0) for y in years]
            avg = sum(vals) / len(vals) if vals else 0
            c = _coeff_info(code)
            md += f"| {c['name']} | {avg:,.2f} | {c['unit']} | 三年均值 |\n"
    md += "\n"

    # 5.4.2 费用基准
    md += "### 5.4.2 能源资源费用基准\n\n"
    if co:
        md += f"**表5.{table_no} 能源资源费用基准表**\n\n"
        md += "| 能源类型 | 费用基准(万元) | 计算方法 |\n"
        md += "|----------|---------------|----------|\n"
        for label, info in bl.get('cost', {}).items():
            md += f"| {label} | {info['基准值']:,.2f} | {info.get('方法', '')} |\n"
        if not bl.get('cost'):
            for code in all_codes:
                vals = [co.get(y, {}).get(code, {}).get('total', 0) for y in years]
                avg = sum(vals) / len(vals) if vals else 0
                c = _coeff_info(code)
                md += f"| {c['name']} | {avg:,.2f} | 三年均值 |\n"
        md += "\n"
    else:
        md += "（费用数据待用户提供）\n\n"

    return md


# ============================================================
# 图表（matplotlib + graphviz）
# ============================================================

# chapter5_agent 标准 key → 流向图 key（energy_flow_chart）
_FLOW_KEY_MAP = {
    'electricity': 'electricity_kwh',
    'water': 'water_m3',
    'natural_gas': 'natural_gas_m3',
    'heat': 'heating_energy_heat_gj',
    'gasoline': 'petrol_kg',
    'diesel': 'diesel_kg',
}


def _generate_flow_diagram(en: dict, config: dict, output_dir: str) -> str:
    """5.1 能源资源流向图（graphviz 全动态）。失败返回 ''。"""
    try:
        from tools.energy_audit.energy_flow_chart import draw_energy_flow_diagram
    except Exception:
        return ''
    codes = set()
    for y_data in en.values():
        codes.update(y_data.keys())
    flow_keys = []
    for c in sorted(codes):
        fk = _FLOW_KEY_MAP.get(_normalize_energy_code(c))
        if fk and fk not in flow_keys:
            flow_keys.append(fk)
    if not flow_keys:
        return ''
    try:
        return draw_energy_flow_diagram(
            energy_types=flow_keys,
            equipment=config.get('equipment') or None,
            unit_name=config.get('unit_name', ''),
            output_path=os.path.join(output_dir, 'energy_flow'),
        )
    except Exception:
        return ''


def _generate_total_bar_chart(years, totals, name_cn, unit, output_dir, fname) -> bool:
    """三年总量对比柱状图（正式报告 图5.N  Y1年-Y3年总XX量）。"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        setup_chart_font(plt)
    except ImportError:
        return False
    y_labels = [str(y)[:4] for y in years]
    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(y_labels, totals, color='#4C8BF5', width=0.5)
    for b, v in zip(bars, totals):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f'{v:,.2f}',
                ha='center', va='bottom', fontsize=9)
    ax.set_title(chart_text(f'{y_labels[0]}年-{y_labels[-1]}年总{name_cn}量（单位：{unit}）'))
    ax.grid(True, alpha=0.3, axis='y')
    fig.savefig(os.path.join(output_dir, fname), dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return True


def _generate_monthly_grouped_bar(years, series_map, name_cn, unit, output_dir, fname) -> bool:
    """三年逐月分组柱状图（正式报告 图5.N  Y1年-Y3年逐月XX量）。"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        setup_chart_font(plt)
    except ImportError:
        return False
    months_cn = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
    y_labels = [str(y)[:4] for y in years]
    x = np.arange(12)
    n = max(len(years), 1)
    width = 0.8 / n
    fig, ax = plt.subplots(figsize=(12, 4.5))
    for i, y in enumerate(years):
        vals = [float(v or 0) for v in (series_map.get(y) or [0] * 12)[:12]]
        ax.bar(x + (i - (n - 1) / 2) * width, vals, width, label=f'{str(y)[:4]}年')
    ax.set_xticks(x)
    ax.set_xticklabels(months_cn)
    ax.legend()
    ax.set_title(chart_text(f'{y_labels[0]}年-{y_labels[-1]}年逐月{name_cn}量（单位：{unit}）'))
    ax.grid(True, alpha=0.3, axis='y')
    fig.savefig(os.path.join(output_dir, fname), dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return True


def _type_tce_3y(en: dict, years: list, code: str) -> float:
    """某能源类型三年折标煤量(tce)。heat 系数 0.03412 已为 tce/GJ 量纲，×1000 转 kgce 统一口径。"""
    c = _coeff_info(code)
    std = _normalize_energy_code(code)
    coeff = c['coeff'] * 1000 if std == 'heat' else c['coeff']
    return sum(
        float(en.get(y, {}).get(code, {}).get('total', 0) or 0) for y in years
    ) * coeff / 1000


# 主要能源小节固定顺序（对齐正式报告 5.2：电→水→气→热→油）
_MAJOR_ORDER = ['electricity', 'water', 'natural_gas', 'heat', 'gasoline', 'diesel']


def _classify_energy_types(en: dict, years: list):
    """主要/次要能源分类（对齐正式报告 5.2 小节划分）：
    主要 = 折标能耗占比≥5% 或 水；其余归"其他用能分析"。
    返回 (major_codes, minor_codes)，major 按固定顺序电→水→气→热→油。"""
    all_codes = set()
    for y_data in en.values():
        all_codes.update(y_data.keys())
    type_tce = {code: _type_tce_3y(en, years, code) for code in all_codes}
    total_tce_all = sum(type_tce.values()) or 1
    major_codes, minor_codes = [], []
    for code in sorted(all_codes):
        std = _normalize_energy_code(code)
        if std == 'water' or (type_tce.get(code, 0) / total_tce_all >= 0.05):
            major_codes.append(code)
        else:
            minor_codes.append(code)
    major_codes.sort(key=lambda c: _MAJOR_ORDER.index(_normalize_energy_code(c))
                     if _normalize_energy_code(c) in _MAJOR_ORDER else 99)
    return major_codes, minor_codes


def generate_charts(data: dict, config: dict, output_dir: str = './charts'):
    """生成第5章全部图表：
    - energy_flow.png（5.1 流向图）
    - chart_{code}_total.png（各能源类型三年总量柱，5.2）
    - chart_{code}_monthly.png（各能源类型三年逐月分组柱，有月度数据才画）
    - cost_pie_{year}.png（各年费用占比饼图，5.2 费用节）
    """
    os.makedirs(output_dir, exist_ok=True)
    en = data.get('energy_data', {})
    years = sorted(en.keys())
    if not years:
        return

    # 5.1 能源资源流向图
    _generate_flow_diagram(en, config, output_dir)

    # 5.2 各能源类型：总量柱 + 逐月分组柱
    # （对齐正式报告：仅有月度抄表数据的主要类型画图，如热力无逐月数据则不画图）
    major_codes, _minor = _classify_energy_types(en, years)
    for code in major_codes:
        c = _coeff_info(code)
        totals = []
        series_map = {}
        has_monthly = False
        for y in years:
            info = en.get(y, {}).get(code, {})
            total = float(info.get('total', 0) or 0)
            totals.append(total)
            monthly = info.get('monthly', [0] * 12) or []
            series_map[y] = monthly
            if any(float(v or 0) > 0 for v in monthly):
                has_monthly = True
        if not has_monthly:
            continue
        _generate_total_bar_chart(years, totals, c['name'], c['unit'], output_dir,
                                  f'chart_{code}_total.png')
        _generate_monthly_grouped_bar(years, series_map, c['name'], c['unit'], output_dir,
                                      f'chart_{code}_monthly.png')

    # ===== 能源费用占比饼图（每年一张，正式报告 5.2 费用分析节）=====
    co = data.get('cost_data', {})
    if co:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            setup_chart_font(plt)
        except ImportError:
            return
        cost_colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336', '#9C27B0', '#795548']
        for y in years:
            labels, values = [], []
            for code, entry in (co.get(y) or {}).items():
                v = float(entry.get('total', 0) or 0)
                if v > 0:
                    label = entry.get('name') or _coeff_info(code)['name'] + '费'
                    labels.append(label)
                    values.append(v)
            if not values:
                continue
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90,
                   colors=cost_colors[:len(values)])
            ax.set_title(chart_text(f'{y[:4]}年能源费用占比'))
            fig.savefig(os.path.join(output_dir, f'cost_pie_{y[:4]}.png'), dpi=150,
                        bbox_inches='tight', facecolor='white')
            plt.close(fig)


# ============================================================
# 主流程
# ============================================================

def generate(config: dict, output_path: str = None) -> str:
    # 加载
    if config.get('manual'):
        data = load_from_user(config)
    else:
        data = load_from_db(config)

    if not data['energy_data']:
        print("[WARN] 无能耗数据，请检查数据库或提供手动数据")
        return ""

    # 图表
    chart_dir = config.get('chart_dir', './charts')
    generate_charts(data, config, chart_dir)

    # Markdown
    md = generate_chapter5_md(data, config)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"Saved: {output_path} ({len(md)} chars)")

    return md


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', help='JSON config path')
    parser.add_argument('--project-id', type=int)
    parser.add_argument('--customer-id', type=int)
    parser.add_argument('--year-start', type=int, default=2022)
    parser.add_argument('--year-end', type=int, default=2024)
    parser.add_argument('--building-area', type=float, default=0)
    parser.add_argument('--people-count', type=int, default=1)
    parser.add_argument('--unit-name', default='被审计单位')
    parser.add_argument('--output', default='chapter5_output.md')
    parser.add_argument('--chart-dir', default='./charts')

    args = parser.parse_args()
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {
            'project_id': args.project_id,
            'customer_id': args.customer_id,
            'year_start': args.year_start,
            'year_end': args.year_end,
            'building_area': args.building_area,
            'people_count': args.people_count,
            'unit_name': args.unit_name,
            'chart_dir': args.chart_dir,
        }

    md = generate(config, args.output)
    print(f"Done: {len(md)} chars")


if __name__ == '__main__':
    main()
