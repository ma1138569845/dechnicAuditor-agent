#!/usr/bin/env python3
"""
Caliber Agent — 能耗指标计算与第5章生成

输入: ~/projects/energy-audit/<project_name>/data.json (AuditProject)
输出: ~/projects/energy-audit/<project_name>/
       ├── indicators.json     # 5项指标 + 定额对标 + 基准
       ├── chapter5.md         # 第5章完整Markdown
       └── charts/             # 图表文件

用法:
    python caliber_agent.py <project_name>
    python caliber_agent.py "山东省省立医院东院区" --skip-charts
"""

import json, os, sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Windows GBK 控制台兼容：输出含 emoji/中文，强制 UTF-8 防 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ── 项目路径适配 ──────────────────────────────────────────────
# 脚本位于用户 profile 目录，需先定位项目根，再借用 tools/energy_audit。
# 3 层降级：env → CWD 向上爬 → __file__ 向上爬（与 _paths.py 一致）。

def _resolve_project_root() -> Path:
    """3 层降级：env → CWD 向上爬 → __file__ 向上爬"""

    # Layer 1: 环境变量（CI/Docker/IDE 推荐）
    env = os.environ.get("HERMES_AGENT_HOME")
    if env:
        candidate = Path(env).expanduser().resolve()
        if (candidate / "tools" / "energy_audit" / "indicators.py").is_file():
            return candidate

    # Layer 2: CWD 向上爬（从项目根或子目录运行时）
    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "tools" / "energy_audit" / "indicators.py").is_file():
            return parent

    # Layer 3: __file__ 向上爬（脚本被放入项目树内时）
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "tools" / "energy_audit" / "indicators.py").is_file():
            return parent

    raise RuntimeError(
        "无法定位项目根目录。请按以下方式修复：\n"
        "  1. 设置环境变量: export HERMES_AGENT_HOME=/path/to/project\n"
        "  2. 从项目根目录运行: cd /path/to/project && python ...\n"
        "  3. 将脚本放入项目内（与 tools/energy_audit 同级）\n"
        f"\n诊断: $PWD={cwd} $HERMES_AGENT_HOME={env!r} __file__={__file__}"
    )


try:
    ROOT_DIR = _resolve_project_root()
except RuntimeError as e:
    print(f"[Caliber] ❌ 路径解析失败\n{e}")
    sys.exit(1)

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from tools.energy_audit.project_data import load_project, AuditProject
    from tools.energy_audit.report_family import (
        ReportFamilyUnsupported,
        resolve_report_family,
    )
    from tools.energy_audit.indicators import (
        YearlyEnergyData,
        calc_unit_area_non_heating_energy,
        compare_with_benchmark,
        calc_unit_area_electricity,
        calc_per_capita_energy,
        calc_water_indicator,
        calc_unit_area_heating_energy,
        project_sub_type,
        calc_baseline,
        resolve_coefficient,
        resolve_benchmark,
        institution_category_to_type,
    )
    from tools.energy_audit.chapter5_agent import (
        generate as gen_chapter5,
        generate_charts,
        load_chapter5_manifest,
    )
    TOOLS_AVAILABLE = True
except ImportError as e:
    print(f"[Caliber] ⚠️ 工具导入失败: {e}")
    print(f"[Caliber] sys.path[0]: {sys.path[0]}")
    TOOLS_AVAILABLE = False

# 公共建筑模块（与当前脚本同目录；仅公共建筑分支使用，不影响公共机构路径）
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from public_building_indicators import compute_project as compute_public_building_indicators
    from public_building_chapter5 import render as render_public_building_chapter5
    from shandong_public_building_indicators import (
        compute_project as compute_shandong_public_building_indicators,
        load_quota_values as load_shandong_public_building_quota,
    )
    from zhejiang_public_institution_indicators import (
        compute_project as compute_zhejiang_public_institution_indicators,
    )
    from standard_chapter5 import render as render_standard_chapter5
    PUBLIC_BUILDING_AVAILABLE = True
except ImportError as e:
    print(f"[Caliber] ⚠️ 地区标准模块导入失败: {e}")
    PUBLIC_BUILDING_AVAILABLE = False


# ================================================================
#  数据提取
# ================================================================

def extract_yearly_data(proj: AuditProject) -> List[YearlyEnergyData]:
    """从 AuditProject 提取 YearlyEnergyData 列表

    2026-09-20 补：注入车库面积（D8 分母剔除）与费用字段——与
    compute_project_indicators / chapter5_agent 同口径，防 indicators.json 与报告分叉。
    """
    # 地下车库面积：建筑表 garage_area 聚合（D8：5.3.1/5.3.2 分母 = 建筑面积 − 车库面积）
    garage_area = sum(float(getattr(b, 'garage_area', 0) or 0)
                      for b in getattr(proj, 'buildings', []) or [])
    # 特殊设备（独立计量 + 有当年电量）→ {年: {'kwh','area'}}（2026-10-19，与 chapter5_agent 同口径）
    from tools.energy_audit.indicators import special_energy_map
    special_map = special_energy_map(getattr(proj, 'equipment', []) or [])
    data_list = []
    for ey in proj.energy_yearly:
        year = getattr(ey, 'year', 0)
        d = YearlyEnergyData(
            year=year,
            electricity_kwh=float(getattr(ey, 'electricity_kwh', 0) or 0),
            water_m3=float(getattr(ey, 'water_m3', 0) or 0),
            natural_gas_m3=float(getattr(ey, 'natural_gas_m3', 0) or 0),
            heating_energy_heat=float(getattr(ey, 'heating_energy_heat_gj', 0) or 0),
            heating_energy_kwh=float(getattr(ey, 'heating_energy_kwh', 0) or 0),
            heating_energy_gas=0,
            transportation_petrol_kg=float(getattr(ey, 'petrol_kg', 0) or 0),
            transportation_diesel_kg=float(getattr(ey, 'diesel_kg', 0) or 0),
            building_area=float(getattr(proj.base, 'building_area', 0) or 0),
            people_count=float(getattr(proj.base, 'people_count', 0) or 0),
            coefficients=dict(getattr(ey, 'coefficients', {}) or {}),
            # 费用字段（5.4 费用基准「三条规则」输入；缺失=0）
            electricity_cost_wan=float(getattr(ey, 'electricity_cost_wan', 0) or 0),
            water_cost_wan=float(getattr(ey, 'water_cost_wan', 0) or 0),
            natural_gas_cost_wan=float(getattr(ey, 'natural_gas_cost_wan', 0) or 0),
            heating_cost_wan=float(getattr(ey, 'heating_cost_wan', 0) or 0),
            petrol_cost_wan=float(getattr(ey, 'petrol_cost_wan', 0) or 0),
            # D8 地下车库面积（分母剔除；缺失=0）
            garage_area=garage_area,
            # 5.3 剔除项（2026-10-19，与 chapter5_agent 同口径）
            transportation_electricity_kwh=float(getattr(ey, 'transport_electricity_kwh', 0) or 0),
            construction_electricity_kwh=float(getattr(ey, 'construction_electricity_kwh', 0) or 0),
            special_electricity_kwh=float((special_map.get(int(year)) or {}).get('kwh') or 0),
            special_area_m2=float((special_map.get(int(year)) or {}).get('area') or 0),
        )
        data_list.append(d)
    return sorted(data_list, key=lambda x: x.year)


# 机构类型解析统一用 indicators.institution_category_to_type（唯一权威，
# 含 venue/service 全分支；2026-09-05 前本地简化版缺 venue/service 且默认 medical，
# 导致政务服务中心类项目在 indicators.json 中被误判为医院）


# ================================================================
#  指标计算
# ================================================================

def _resolve_heating_area(proj) -> float:
    """采暖建筑面积取值（2026-09-29 口径判别）。

    建筑表 heat_area 常被平台按「每栋建筑面积」默认填充（实测岚山医院 7 栋 heat_area
    与 build_area 全等、合计 63465.91㎡），而真实供暖面积在 scene.heat_area
    （54523.3㎡，与 120 万热费、22 元/㎡ 完全自洽）。
    判别：聚合 build.heat_area 与建筑面积全等（疑似默认填充）且 metering.heat_area
    > 0 且小于聚合值 → 用 scene 口径；否则沿用建筑表聚合
    （法院 build=24300、scene 为空 → 不受影响；2026-09-29 用户裁决本案用 54523.3）。
    """
    buildings = list(getattr(proj, 'buildings', []) or [])
    b_sum = sum(float(getattr(b, 'heating_area', 0) or 0) for b in buildings)
    building_area = float(getattr(getattr(proj, 'base', None), 'building_area', 0) or 0)
    m_heat = float(getattr(getattr(proj, 'metering', None), 'heat_area', None) or 0)
    if (b_sum > 0 and building_area > 0 and abs(b_sum - building_area) < 0.5
            and 0 < m_heat < b_sum):
        return m_heat
    return b_sum


def calc_all_indicators(
    proj: AuditProject,
    yearly_data: List[YearlyEnergyData],
) -> dict:
    """计算全部5项指标 + 定额对标 + 能耗基准"""
    if not yearly_data:
        return {'error': '无年度能耗数据'}

    latest = yearly_data[-1]
    inst_type = institution_category_to_type(getattr(proj.base, 'institution_category', '') or '')
    bed_count = getattr(proj.base, 'beds_count', 0) or 0

    # 二级维度查询串（2026-09-20）：分档/等级·气候区/场馆类型·省市档，
    # 由平台字典码（unit_func/children_func）+ 内置气候区表拼出；表2 换成「·供暖类型」。
    st_non_heating = project_sub_type(proj.base, inst_type, 'unit_area_non_heating')
    st_elec = project_sub_type(proj.base, inst_type, 'unit_area_elec')
    st_capita = project_sub_type(proj.base, inst_type, 'per_capita_energy')
    st_water = project_sub_type(proj.base, inst_type, 'water_per_person')
    st_heating = project_sub_type(proj.base, inst_type, 'unit_area_heating')

    results = {
        'project': getattr(proj.base, 'unit_name', ''),
        'year': latest.year,
        'building_area': getattr(proj.base, 'building_area', 0),
        'people_count': getattr(proj.base, 'people_count', 0),
        'institution_type': inst_type,
        'sub_type': {'unit_area_non_heating': st_non_heating, 'unit_area_elec': st_elec,
                     'per_capita_energy': st_capita, 'water_indicator': st_water,
                     'unit_area_heating': st_heating},
        'calculated_at': datetime.now().isoformat(),
    }

    # ── 指标 (1): 单位建筑面积非供暖能耗 ──
    r1 = calc_unit_area_non_heating_energy(latest)
    if r1.get('error'):
        # 输入无效（如建筑面积缺失）时结果为 0 值占位，直接对标会误判"先进水平"
        results['unit_area_non_heating_energy'] = {**r1, 'benchmark': None}
    else:
        bm1 = compare_with_benchmark(r1['kgce_per_m2'], inst_type, 'unit_area_non_heating',
                                     sub_type=st_non_heating)
        results['unit_area_non_heating_energy'] = {
            **r1,
            'benchmark': bm1,
        }

    # ── 指标 (2): 常规用能系统单位建筑面积电耗 ──
    r2 = calc_unit_area_electricity(latest, institution_type=inst_type, sub_type=st_elec)
    results['unit_area_electricity'] = r2

    # ── 指标 (3): 人均综合能耗 ──
    r3 = calc_per_capita_energy(latest, institution_type=inst_type, sub_type=st_capita)
    results['per_capita_energy'] = r3

    # ── 指标 (4): 取水指标（医院=床日/机关教育=人均/场馆=面积）──
    r4 = calc_water_indicator(latest, inst_type, bed_count=bed_count,
                              building_area=latest.building_area,  # venue/service 面积口径必传
                              sub_type=st_water)
    results['water_indicator'] = r4

    # ── 指标 (5): 单位采暖建筑面积供暖能耗（有供暖能耗的项目必算）──
    has_heating = any((getattr(d, 'heating_energy_heat', 0) or 0) > 0 or
                      (getattr(d, 'heating_energy_kwh', 0) or 0) > 0 for d in yearly_data)
    if has_heating:
        heating_area = _resolve_heating_area(proj)
        r5 = calc_unit_area_heating_energy(latest, heating_area=heating_area,
                                           institution_type=inst_type, sub_type=st_heating)
        results['unit_area_heating'] = r5

    # ── 5.4: 建筑能耗基准 ──
    baseline = calc_baseline(yearly_data)
    results['baseline'] = baseline

    return results


# ================================================================
#  格式化输出
# ================================================================

def format_indicators_report(results: dict) -> str:
    """生成可读的指标报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("📊 Caliber — 能耗指标计算结果")
    lines.append("=" * 60)
    lines.append(f"项目: {results.get('project', '')}")
    lines.append(f"年度: {results.get('year', '')} | 类型: {results.get('institution_type', '')}")
    lines.append(f"面积: {results.get('building_area', 0):.0f} m² | "
                 f"人数: {results.get('people_count', 0)}")
    lines.append("")

    # 指标(1)
    r1 = results.get('unit_area_non_heating_energy', {})
    bm1 = r1.get('benchmark') or {}
    lines.append(f"1. 单位建筑面积非供暖能耗: {r1.get('kgce_per_m2','-')} kgce/(m²·a)")
    lines.append(f"   对标: {bm1.get('评价结果','-')}")
    lines.append(f"   标准: {bm1.get('标准','-')} | 来源: {bm1.get('来源','-')}")
    lines.append(f"   约束值: {bm1.get('约束值','-')}  基准值: {bm1.get('基准值','-')}  引导值: {bm1.get('引导值','-')}")
    lines.append("")

    # 指标(2)
    r2 = results.get('unit_area_electricity', {})
    bm2 = r2.get('benchmark') or {}
    lines.append(f"2. 常规用能系统单位面积电耗: {r2.get('kwh_per_m2','-')} kWh/(m²·a)")
    lines.append(f"   对标: {bm2.get('评价结果','-')}")
    lines.append(f"   标准: {bm2.get('标准','-')} | 来源: {bm2.get('来源','-')}")
    lines.append(f"   约束值: {bm2.get('约束值','-')}  基准值: {bm2.get('基准值','-')}  引导值: {bm2.get('引导值','-')}")
    lines.append("")

    # 指标(3)
    r3 = results.get('per_capita_energy', {})
    bm3 = r3.get('benchmark') or {}
    lines.append(f"3. 人均综合能耗: {r3.get('kgce_per_person','-')} kgce/(人·a)")
    lines.append(f"   对标: {bm3.get('评价结果','-')}")
    lines.append(f"   约束值: {bm3.get('约束值','-')}  基准值: {bm3.get('基准值','-')}  引导值: {bm3.get('引导值','-')}")
    lines.append("")

    # 指标(4) 取水指标
    r4 = results.get('water_indicator') or results.get('per_capita_water', {})  # 旧键兼容
    bm4 = r4.get('benchmark') or {}
    if 'L_per_bed_day' in r4:
        lines.append(f"4. 单位开放床日用水量: {r4.get('L_per_bed_day','-')} L/(床·d)")
    else:
        lines.append(f"4. 人均取水量: {r4.get('m3_per_person','-')} m³/(人·a)")
    lines.append(f"   对标: {bm4.get('评价结果','-')}")
    lines.append(f"   标准: {bm4.get('标准','-')} | 来源: {bm4.get('来源','-')}")
    lines.append("")

    # 指标(5) 供暖指标（有供暖能耗才打印）
    r5 = results.get('unit_area_heating') or {}
    if r5.get('kgce_per_m2') is not None and r5.get('heating_area_m2'):
        bm5 = r5.get('benchmark') or {}
        lines.append(f"5. 单位采暖建筑面积供暖能耗: {r5.get('kgce_per_m2','-')} kgce/(m²·a)")
        lines.append(f"   对标: {bm5.get('评价结果','-')}")
        lines.append(f"   采暖建筑面积: {r5.get('heating_area_m2',0):.0f} m²")
        lines.append("")

    # 基准
    baseline = results.get('baseline', {})
    if baseline and 'usage' in baseline:
        lines.append(f"6. 建筑能耗基准 ({'、'.join(map(str, baseline.get('years', [])))}年):")
        for label, info in baseline.get('usage', {}).items():
            lines.append(f"   {label}: {info['基准值']:.2f}{info['单位']} [{info['方法']}]")

    lines.append("")
    lines.append("=" * 60)
    return '\n'.join(lines)


# ================================================================
#  公共建筑分支（浙江；不影响公共机构路径）
# ================================================================

def _report_family_context(proj: AuditProject):
    return resolve_report_family({
        "unit_type": getattr(proj.base, "unit_type", "") or "",
        "province": getattr(proj.base, "province", "") or "",
    })


def _is_public_building(proj: AuditProject) -> bool:
    return _report_family_context(proj).is_public_building


def _load_raw_project_data(project_name: str) -> dict:
    p = Path(project_name)
    data_path = (p / "data.json") if p.is_dir() else (
        Path.home() / "projects" / "energy-audit" / project_name / "data.json"
    )
    if not data_path.is_file():
        return {}
    with open(data_path, encoding="utf-8") as fh:
        return json.load(fh)


def _infer_public_subtype(base, pb: dict) -> str:
    raw = str(pb.get("subtype") or "").strip().lower()
    if raw in ("hotel", "饭店", "公寓", "宾馆", "酒店"):
        return "hotel"
    if raw in ("venue", "场馆"):
        return "venue"
    if raw in ("office", "办公"):
        return "office"
    text = f"{getattr(base, 'institution_category', '')}{getattr(base, 'specific_type', '')}"
    if any(k in text for k in ("公寓", "饭店", "宾馆", "酒店")):
        return "hotel"
    if any(k in text for k in ("场馆", "图书馆", "博物馆", "体育馆", "科技馆")):
        return "venue"
    return "office"


def build_public_building_spec(proj: AuditProject, raw: dict) -> dict:
    base = proj.base
    pb = (raw.get("public_building") or {}) if isinstance(raw, dict) else {}
    subtype = _infer_public_subtype(base, pb)
    area = float(getattr(base, "building_area", 0) or 0)
    if area <= 0:
        area = sum(float(getattr(b, "area", 0) or 0) for b in (proj.buildings or []))
    people = float(getattr(base, "people_count", 0) or 0)
    beds = float(getattr(base, "beds_count", 0) or 0)
    occupancy = float(pb.get("occupancy") or 1.0)
    people_by_year = pb.get("people_by_year") or {}
    beds_by_year = pb.get("beds_by_year") or {}
    occupancy_by_year = pb.get("occupancy_by_year") or {}
    corrections_by_year = pb.get("hotel_corrections_by_year") or {}

    years = []
    for ey in sorted(getattr(proj, "energy_yearly", []) or [], key=lambda x: x.year):
        year_key = str(ey.year)
        years.append({
            "year": ey.year,
            "electricity_kwh": float(getattr(ey, "electricity_kwh", 0) or 0),
            "monthly_electricity_kwh": _get_monthly(
                proj, ey.year, "monthly_electricity_kwh"
            ),
            "water_t": float(getattr(ey, "water_m3", 0) or 0),
            "monthly_water_m3": _get_monthly(
                proj, ey.year, "monthly_water_m3"
            ),
            "gas_m3": float(getattr(ey, "natural_gas_m3", 0) or 0),
            "monthly_natural_gas_m3": _get_monthly(
                proj, ey.year, "monthly_natural_gas_m3"
            ),
            "heat_gj": float(getattr(ey, "heating_energy_heat_gj", 0) or 0),
            "other_kgce": 0.0,
            "people": float(people_by_year.get(year_key, people) or people),
            "beds": float(beds_by_year.get(year_key, beds) or beds),
            "occupancy": float(occupancy_by_year.get(year_key, occupancy) or occupancy),
            "hotel_corrections": corrections_by_year.get(year_key) or {},
            "electricity_cost_wan": float(getattr(ey, "electricity_cost_wan", 0) or 0),
            "water_cost_wan": float(getattr(ey, "water_cost_wan", 0) or 0),
            "gas_cost_wan": float(getattr(ey, "natural_gas_cost_wan", 0) or 0),
            "heat_cost_wan": float(getattr(ey, "heating_cost_wan", 0) or 0),
        })

    return {
        "subtype": subtype,
        "level": pb.get("level") or "city",
        "venue_type": pb.get("venue_type") or "culture",
        "star": str(pb.get("star") or "3"),
        "water_category": str(pb.get("water_category") or pb.get("star") or "3"),
        "area_m2": area,
        "underground_parking_spaces": float(pb.get("underground_parking_spaces") or 0),
        "people": people,
        "beds": beds,
        "occupancy": occupancy,
        "has_canteen": bool(pb.get("has_canteen")),
        "pre2005_no_central_ac": bool(pb.get("pre2005_no_central_ac")),
        "hotel_corrections": pb.get("hotel_corrections") or {},
        "years": years,
    }


def _pick_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return 0


def _raw_year_row(raw: dict, year: int) -> dict:
    for row in (raw or {}).get("energy_yearly") or []:
        try:
            if int(row.get("year") or 0) == int(year):
                return dict(row)
        except (TypeError, ValueError):
            continue
    return {}


def _year_override(raw: dict, section: str, year: int) -> dict:
    section_data = (raw or {}).get(section) or {}
    overrides = section_data.get("years_by_year") or {}
    return dict(overrides.get(str(year)) or overrides.get(year) or {})


def _building_sum(proj: AuditProject, field: str) -> float:
    return sum(
        float(getattr(building, field, 0) or 0)
        for building in (getattr(proj, "buildings", []) or [])
    )


def _raw_building_sum(raw: dict, field: str) -> float:
    return sum(
        float(building.get(field) or 0)
        for building in ((raw or {}).get("buildings") or [])
        if isinstance(building, dict)
    )


def _shandong_public_building_subtype(base, config: dict) -> str:
    raw = str(config.get("subtype") or "").strip().lower()
    aliases = {
        "business_office": "business_office",
        "business-office": "business_office",
        "商务办公": "business_office",
        "商务写字楼": "business_office",
        "hotel": "hotel",
        "酒店": "hotel",
        "宾馆": "hotel",
        "饭店": "hotel",
        "hospital": "hospital",
        "医院": "hospital",
    }
    if raw in aliases:
        return aliases[raw]

    text = (
        f"{getattr(base, 'institution_category', '')}"
        f"{getattr(base, 'specific_type', '')}"
    )
    if "机关办公" in text:
        raise ValueError(
            "机关办公不适用山东公共建筑 DB37/T 5078-2024；"
            "机关项目应按公共机构报告族处理"
        )
    if "商务办公" in text or "商务写字楼" in text:
        return "business_office"
    if any(token in text for token in ("酒店", "宾馆", "饭店")):
        return "hotel"
    if "医院" in text:
        return "hospital"
    raise ValueError(
        "山东公共建筑必须明确 public_building.subtype="
        "business_office / hotel / hospital，拒绝按名称静默猜测"
    )


def build_shandong_public_building_spec(proj: AuditProject, raw: dict) -> dict:
    base = proj.base
    config = (raw.get("public_building") or {}) if isinstance(raw, dict) else {}
    subtype = _shandong_public_building_subtype(base, config)

    area = float(
        _pick_value(
            config.get("area_m2"),
            getattr(base, "building_area", 0),
            _building_sum(proj, "area"),
        )
        or 0
    )
    garage_area = float(
        _pick_value(
            config.get("garage_area_m2"),
            _raw_building_sum(raw, "garage_area"),
            _building_sum(proj, "garage_area"),
        )
        or 0
    )
    if area > 0 and garage_area > 0:
        area = max(0.0, area - garage_area)
    if area <= 0:
        raise ValueError("山东公共建筑面积必须大于 0")

    heating_area = float(
        _pick_value(
            config.get("heating_area_m2"),
            _raw_building_sum(raw, "heating_area"),
            _building_sum(proj, "heating_area"),
            _resolve_heating_area(proj),
            area,
        )
        or 0
    )
    beds = float(
        _pick_value(config.get("beds"), getattr(base, "beds_count", 0), 0) or 0
    )
    people = float(
        _pick_value(config.get("people"), getattr(base, "people_count", 0), 0) or 0
    )

    city = _pick_value(
        config.get("city"),
        getattr(base, "city", ""),
        getattr(base, "address", ""),
    )
    correction = {}
    for key in (
        "annual_use_hours", "area_per_person", "occupancy",
        "room_area_ratio", "equipment_hours", "ac_days",
        "outpatient_visits",
    ):
        value = _pick_value(config.get(key), 0)
        if value:
            correction[key] = value

    years = []
    for ey in sorted(getattr(proj, "energy_yearly", []) or [], key=lambda x: x.year):
        year = int(ey.year)
        year_key = str(year)
        raw_row = _raw_year_row(raw, year)
        override = _year_override(raw, "public_building", year)
        merged = {**raw_row, **override}

        electricity = float(
            _pick_value(merged.get("electricity_kwh"), ey.electricity_kwh, 0) or 0
        )
        gas = float(
            _pick_value(merged.get("natural_gas_m3"), ey.natural_gas_m3, 0) or 0
        )
        heating_electricity = float(
            _pick_value(
                merged.get("heating_electricity_kwh"),
                merged.get("heating_energy_kwh"),
                ey.heating_energy_kwh,
                0,
            ) or 0
        )
        heating_gas = float(
            _pick_value(
                merged.get("heating_gas_m3"),
                merged.get("heating_energy_gas_m3"),
                0,
            ) or 0
        )
        heating_heat_gj = float(
            _pick_value(
                merged.get("heating_heat_gj"),
                merged.get("heating_energy_heat_gj"),
                ey.heating_energy_heat_gj,
                0,
            ) or 0
        )
        non_heating_electricity = float(
            _pick_value(
                merged.get("non_heating_electricity_kwh"),
                max(0.0, electricity - heating_electricity),
            ) or 0
        )
        non_heating_gas = float(
            _pick_value(
                merged.get("non_heating_gas_m3"),
                max(0.0, gas - heating_gas),
            ) or 0
        )
        clinic_num = float(
            _pick_value(
                override.get("outpatient_visits"),
                merged.get("outpatient_visits"),
                config.get("outpatient_visits"),
                getattr(base, "clinic_num", 0),
                correction.get("outpatient_visits", 0),
                0,
            ) or 0
        )
        year_correction = {
            key: value
            for key, value in override.items()
            if key in {
                "annual_use_hours", "area_per_person", "occupancy",
                "room_area_ratio", "equipment_hours", "ac_days",
                "outpatient_visits",
            }
        }
        if clinic_num:
            year_correction["outpatient_visits"] = clinic_num

        years.append({
            "year": year,
            "area_m2": float(_pick_value(override.get("area_m2"), area) or area),
            "heating_area_m2": float(
                _pick_value(override.get("heating_area_m2"), heating_area)
                or heating_area
            ),
            "beds": float(_pick_value(override.get("beds"), beds) or beds),
            "electricity_kwh": electricity,
            "heating_electricity_kwh": heating_electricity,
            "non_heating_electricity_kwh": non_heating_electricity,
            "gas_m3": gas,
            "heating_gas_m3": heating_gas,
            "non_heating_gas_m3": non_heating_gas,
            "heating_heat_gj": heating_heat_gj,
            "heating_raw_coal_kg": float(
                _pick_value(
                    override.get("heating_raw_coal_kg"),
                    merged.get("heating_raw_coal_kg"),
                    0,
                ) or 0
            ),
            "heating_energy_kgce": float(
                _pick_value(override.get("heating_energy_kgce"), 0) or 0
            ),
            "heating_electricity_kgce_per_kwh": float(
                _pick_value(
                    override.get("heating_electricity_kgce_per_kwh"),
                    merged.get("heating_electricity_kgce_per_kwh"),
                    config.get("heating_electricity_kgce_per_kwh"),
                    0,
                )
                or 0
            ),
            "gasoline_kg": float(
                _pick_value(merged.get("petrol_kg"), ey.petrol_kg, 0) or 0
            ),
            "diesel_kg": float(
                _pick_value(merged.get("diesel_kg"), ey.diesel_kg, 0) or 0
            ),
            "raw_coal_kg": float(_pick_value(merged.get("raw_coal_kg"), 0) or 0),
            "cleaned_coal_kg": float(
                _pick_value(merged.get("cleaned_coal_kg"), 0) or 0
            ),
            "other_equivalent_electricity_kwh": float(
                _pick_value(merged.get("other_equivalent_electricity_kwh"), 0) or 0
            ),
            "correction": year_correction,
            "electricity_cost_wan": float(
                _pick_value(
                    merged.get("electricity_cost_wan"),
                    ey.electricity_cost_wan,
                    0,
                ) or 0
            ),
            "water_t": float(
                _pick_value(merged.get("water_m3"), ey.water_m3, 0) or 0
            ),
            "monthly_electricity_kwh": _get_monthly(
                proj, year, "monthly_electricity_kwh"
            ),
            "monthly_water_m3": _get_monthly(proj, year, "monthly_water_m3"),
            "monthly_natural_gas_m3": _get_monthly(
                proj, year, "monthly_natural_gas_m3"
            ),
            "water_cost_wan": float(
                _pick_value(merged.get("water_cost_wan"), ey.water_cost_wan, 0)
                or 0
            ),
            "gas_cost_wan": float(
                _pick_value(
                    merged.get("natural_gas_cost_wan"),
                    ey.natural_gas_cost_wan,
                    0,
                ) or 0
            ),
            "heat_cost_wan": float(
                _pick_value(
                    merged.get("heating_cost_wan"),
                    ey.heating_cost_wan,
                    0,
                ) or 0
            ),
        })

    return {
        "subtype": subtype,
        "city": city,
        "area_m2": area,
        "garage_area_m2": garage_area,
        "heating_area_m2": heating_area,
        "beds": beds,
        "people": people,
        "star": _pick_value(config.get("star"), ""),
        "hospital_level": _pick_value(
            config.get("hospital_level"),
            getattr(base, "children_func", ""),
            "",
        ),
        "hospital_specialty": _pick_value(
            config.get("hospital_specialty"),
            getattr(base, "specific_type", ""),
            "",
        ),
        "correction": correction,
        "years": years,
    }


def _zhejiang_public_institution_subtype(base, config: dict) -> str:
    raw = str(config.get("subtype") or "").strip().lower()
    aliases = {
        "agency": "agency",
        "government": "agency",
        "administrative": "agency",
        "机关": "agency",
        "行政机关": "agency",
        "venue": "venue",
        "场馆": "venue",
        "university": "university",
        "higher_education": "university",
        "college": "university",
        "高校": "university",
        "普通高等院校": "university",
        "hospital": "hospital",
        "medical": "hospital",
        "医院": "hospital",
        "医疗机构": "hospital",
    }
    if raw in aliases:
        return aliases[raw]

    unit_func = str(getattr(base, "unit_func", "") or "").strip().upper()
    children = str(getattr(base, "children_func", "") or "").strip().upper()
    category = str(getattr(base, "institution_category", "") or "")
    specific = str(getattr(base, "specific_type", "") or "")
    text = category + specific
    if unit_func == "C" or "医疗" in text or "医院" in text:
        return "hospital"
    if unit_func == "D" or any(token in text for token in ("党政", "机关")):
        return "agency"
    if unit_func == "B" or "场馆" in text:
        return "venue"
    if unit_func == "E" or "教育" in text or "高校" in text:
        if any(token in text for token in ("成人", "自考", "中小学", "幼儿园")):
            raise ValueError(
                "浙江公共机构包仅适用普通高等院校；成人高校、自考高校及中小学不适用"
            )
        if children in ("A", "B") or any(
            token in text for token in ("本科", "专科", "大学", "学院")
        ):
            return "university"
        raise ValueError(
            "教育类项目必须明确为普通高等院校（public_institution.subtype=university），"
            "不得把其他教育机构套用 DB33/T 737-2021"
        )
    raise ValueError(
        "浙江公共机构必须明确 subtype=agency / venue / university / hospital"
    )


def _zhejiang_agency_level(base, config: dict) -> str:
    raw = str(
        _pick_value(config.get("agency_level"), config.get("level"), "")
    ).strip().lower()
    aliases = {
        "province": "province", "省级": "province",
        "city": "city", "市级": "city",
        "county": "county", "县级": "county", "县级及以下": "county",
    }
    if raw in aliases:
        return aliases[raw]
    children = str(getattr(base, "children_func", "") or "").strip().upper()
    return {"A": "province", "B": "city", "C": "county"}.get(children, "")


def _zhejiang_venue_type(config: dict, base) -> str:
    raw = str(config.get("venue_type") or "").strip().lower()
    aliases = {
        "science": "science", "科技馆": "science",
        "culture": "culture", "文化馆": "culture",
        "museum": "museum", "博物馆": "museum",
    }
    if raw in aliases:
        return aliases[raw]
    specific = str(getattr(base, "specific_type", "") or "")
    for token, value in (("科技馆", "science"), ("文化馆", "culture"), ("博物馆", "museum")):
        if token in specific:
            return value
    return ""


def build_zhejiang_public_institution_spec(proj: AuditProject, raw: dict) -> dict:
    base = proj.base
    config = (raw.get("public_institution") or {}) if isinstance(raw, dict) else {}
    subtype = _zhejiang_public_institution_subtype(base, config)
    area = float(
        _pick_value(
            config.get("area_m2"),
            getattr(base, "building_area", 0),
            _building_sum(proj, "area"),
        )
        or 0
    )
    people = float(
        _pick_value(config.get("people"), getattr(base, "people_count", 0), 0)
        or 0
    )
    spec = {
        "subtype": subtype,
        "area_m2": area,
        "people": people,
        "beds": float(
            _pick_value(config.get("beds"), getattr(base, "beds_count", 0), 0)
            or 0
        ),
        "agency_level": _zhejiang_agency_level(base, config) if subtype == "agency" else "",
        "level": _zhejiang_agency_level(base, config) if subtype == "agency" else "",
        "venue_type": _zhejiang_venue_type(config, base) if subtype == "venue" else "",
        "hospital_level": _pick_value(
            config.get("hospital_level"),
            getattr(base, "children_func", ""),
            "",
        ),
        "specific_type": getattr(base, "specific_type", "") or "",
        "unit_name": getattr(base, "unit_name", "") or "",
        "has_canteen": bool(config.get("has_canteen")),
        "pre2005_no_central_ac": bool(config.get("pre2005_no_central_ac")),
        "outpatient_visits": float(
            _pick_value(
                config.get("outpatient_visits"),
                getattr(base, "clinic_num", 0),
                0,
            ) or 0
        ),
        "open_beds": float(
            _pick_value(config.get("open_beds"), getattr(base, "beds_count", 0), 0)
            or 0
        ),
        "years": [],
    }

    for ey in sorted(getattr(proj, "energy_yearly", []) or [], key=lambda x: x.year):
        year = int(ey.year)
        raw_row = _raw_year_row(raw, year)
        override = _year_override(raw, "public_institution", year)
        merged = {**raw_row, **override}
        spec["years"].append({
            "year": year,
            "area_m2": float(_pick_value(override.get("area_m2"), area) or area),
            "people": float(_pick_value(override.get("people"), people) or people),
            "electricity_kwh": float(
                _pick_value(merged.get("electricity_kwh"), ey.electricity_kwh, 0)
                or 0
            ),
            "gas_m3": float(
                _pick_value(merged.get("natural_gas_m3"), ey.natural_gas_m3, 0)
                or 0
            ),
            "heat_gj": float(
                _pick_value(
                    merged.get("heating_energy_heat_gj"),
                    ey.heating_energy_heat_gj,
                    0,
                ) or 0
            ),
            "lpg_kg": float(_pick_value(merged.get("lpg_kg"), 0) or 0),
            "gasoline_kg": float(
                _pick_value(merged.get("petrol_kg"), ey.petrol_kg, 0) or 0
            ),
            "diesel_kg": float(
                _pick_value(merged.get("diesel_kg"), ey.diesel_kg, 0) or 0
            ),
            "fuel_oil_kg": float(_pick_value(merged.get("fuel_oil_kg"), 0) or 0),
            "raw_coal_kg": float(_pick_value(merged.get("raw_coal_kg"), 0) or 0),
            "other_kgce": float(_pick_value(merged.get("other_kgce"), 0) or 0),
            "water_t": float(
                _pick_value(merged.get("water_m3"), ey.water_m3, 0) or 0
            ),
            "outpatient_visits": float(
                _pick_value(
                    override.get("outpatient_visits"),
                    merged.get("outpatient_visits"),
                    spec["outpatient_visits"],
                ) or 0
            ),
            "open_beds": float(
                _pick_value(
                    override.get("open_beds"),
                    merged.get("open_beds"),
                    merged.get("beds"),
                    spec["open_beds"],
                ) or 0
            ),
            "beds": float(
                _pick_value(
                    override.get("beds"),
                    merged.get("beds"),
                    spec["beds"],
                ) or 0
            ),
            "pre2005_no_central_ac": bool(
                override.get(
                    "pre2005_no_central_ac",
                    spec["pre2005_no_central_ac"],
                )
            ),
            "data_center_electricity_kwh": float(
                _pick_value(merged.get("data_center_electricity_kwh"), 0) or 0
            ),
            "it_equipment_electricity_kwh": float(
                _pick_value(merged.get("it_equipment_electricity_kwh"), 0) or 0
            ),
            "electricity_cost_wan": float(
                _pick_value(
                    merged.get("electricity_cost_wan"),
                    ey.electricity_cost_wan,
                    0,
                ) or 0
            ),
            "water_cost_wan": float(
                _pick_value(merged.get("water_cost_wan"), ey.water_cost_wan, 0)
                or 0
            ),
            "gas_cost_wan": float(
                _pick_value(
                    merged.get("natural_gas_cost_wan"),
                    ey.natural_gas_cost_wan,
                    0,
                ) or 0
            ),
            "heat_cost_wan": float(
                _pick_value(
                    merged.get("heating_cost_wan"),
                    ey.heating_cost_wan,
                    0,
                ) or 0
            ),
            "monthly_electricity_kwh": _get_monthly(
                proj, year, "monthly_electricity_kwh"
            ),
            "monthly_water_m3": _get_monthly(proj, year, "monthly_water_m3"),
            "monthly_natural_gas_m3": _get_monthly(
                proj, year, "monthly_natural_gas_m3"
            ),
        })
    return spec


def _pb_benchmark(tiers: list, labels: list[str], standard: str,
                  source: str, grade: str) -> dict:
    out = {label: (tiers[i] if i < len(tiers) else None)
           for i, label in enumerate(labels)}
    out.update({"标准": standard, "来源": source, "评价结果": grade})
    return out


def _standard_metric_node(
    latest: dict,
    value_key: str,
    quota_key: str,
    labels: list[str],
    standard: str,
    source: str,
    *,
    grade_key: Optional[str] = None,
) -> dict:
    return {
        value_key: latest["values"].get(value_key),
        "benchmark": _pb_benchmark(
            latest.get("quota", {}).get(quota_key) or [],
            labels,
            standard,
            source,
            latest.get("grade", {}).get(grade_key or quota_key, "—"),
        ),
    }


def _shandong_metrics(subtype: str) -> list[dict]:
    table = {
        "business_office": "表7.0.2（5078）",
        "hotel": "表7.0.2（5076）",
        "hospital": "表7.0.2（5079）",
    }[subtype]
    metrics = [
        {
            "key": "unit_area_heating_energy",
            "label": "单位建筑面积供暖能耗",
            "unit": "kgce/(m²·a)",
            "tier_labels": ["约束值", "先进值"],
            "anchor": table,
        },
        {
            "key": "unit_area_non_heating_electricity",
            "label": "单位建筑面积非供暖电耗",
            "unit": "kWh/(m²·a)",
            "tier_labels": ["约束值", "先进值"],
            "anchor": table,
        },
    ]
    if subtype == "hospital":
        metrics.append({
            "key": "per_bed_non_heating_electricity",
            "label": "单位床位非供暖电耗",
            "unit": "10³ kWh/(床·a)",
            "tier_labels": ["约束值", "先进值"],
            "anchor": table,
        })
    return metrics


def build_shandong_public_building_indicators_json(
    proj: AuditProject,
    spec: dict,
    results: list[dict],
) -> dict:
    latest = results[-1]
    standard = latest["standard_id"]
    source = latest["standard_table"]
    out = {
        "project": getattr(proj.base, "unit_name", ""),
        "year": latest["year"],
        "building_area": spec["area_m2"],
        "people_count": spec.get("people", 0),
        "beds_count": spec.get("beds", 0),
        "institution_type": "public_building",
        "family": "公共建筑",
        "region": "山东",
        "standard_package": (
            "energy-audit-core/references/standards/shandong/public_building/"
        ),
        "calculated_at": datetime.now().isoformat(),
        "public_building": {
            "subtype": spec["subtype"],
            "region": "山东",
            "city": spec.get("city"),
            "star": spec.get("star"),
            "hospital_level": spec.get("hospital_level"),
            "hospital_specialty": spec.get("hospital_specialty"),
            "results": results,
        },
    }
    out["unit_area_heating_energy"] = {
        "kgce_per_m2": latest["values"]["unit_area_heating_energy"],
        "benchmark": _pb_benchmark(
            latest["quota"]["unit_area_heating_energy"],
            ["约束值", "先进值"],
            standard,
            source,
            latest["grade"]["unit_area_heating_energy"],
        ),
    }
    out["unit_area_non_heating_electricity"] = {
        "kwh_per_m2": latest["values"]["unit_area_non_heating_electricity"],
        "benchmark": _pb_benchmark(
            latest["quota"]["unit_area_non_heating_electricity"],
            ["约束值", "先进值"],
            standard,
            source,
            latest["grade"]["unit_area_non_heating_electricity"],
        ),
    }
    if spec["subtype"] == "hospital":
        out["per_bed_non_heating_electricity"] = {
            "k10_kwh_per_bed": latest["values"]["per_bed_non_heating_electricity"],
            "benchmark": _pb_benchmark(
                latest["quota"]["per_bed_non_heating_electricity"],
                ["约束值", "先进值"],
                standard,
                source,
                latest["grade"]["per_bed_non_heating_electricity"],
            ),
        }
    return out


def _zhejiang_public_institution_metrics(latest: dict) -> list[dict]:
    values = latest.get("values") or {}
    three_tiers = ["约束值", "基准值", "引导值"]
    if latest.get("subtype") == "hospital":
        # 738 的主指标是“可比单位面积能耗”，原始单位面积能耗仅作过程量。
        metrics = [
            {
                "key": "comparable_unit_area_energy",
                "label": "可比单位建筑面积能耗",
                "unit": "kgce/(m²·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
            {
                "key": "per_capita_energy",
                "label": "人均综合能耗",
                "unit": "kgce/(人·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
            {
                "key": "unit_area_electricity",
                "label": "常规用能系统单位建筑面积电耗",
                "unit": "kWh/(m²·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
        ]
    else:
        metrics = [
            {
                "key": "unit_area_energy",
                "label": "单位建筑面积能耗",
                "unit": "kgce/(m²·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
            {
                "key": "per_capita_energy",
                "label": "人均综合能耗",
                "unit": "kgce/(人·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
            {
                "key": "unit_area_electricity",
                "label": "常规用能系统单位建筑面积电耗",
                "unit": "kWh/(m²·a)",
                "tier_labels": three_tiers,
                "anchor": latest["standard_table"],
            },
        ]
    if "per_capita_electricity" in values:
        metrics.append({
            "key": "per_capita_electricity",
            "label": "人均电耗",
            "unit": "kWh/(人·a)",
            "tier_labels": three_tiers,
            "anchor": latest["standard_table"],
        })
    if "eeue" in values:
        metrics.append({
            "key": "eeue",
            "label": "数据中心机房 EEUE",
            "unit": "",
            "tier_labels": three_tiers,
            "anchor": "数据中心机房能效",
        })
    if "unit_water" in values:
        metrics.append({
            "key": "unit_water",
            "label": "人均用水量",
            "unit": "m³/(人·a)",
            "tier_labels": ["通用值", "先进值"],
            "grade_key": "unit_water",
            "anchor": "浙江省用（取）水定额（2019）",
        })
    return metrics


def build_zhejiang_public_institution_indicators_json(
    proj: AuditProject,
    spec: dict,
    results: list[dict],
) -> dict:
    latest = results[-1]
    standard = latest["standard_id"]
    source = latest["standard_table"]
    out = {
        "project": getattr(proj.base, "unit_name", ""),
        "year": latest["year"],
        "building_area": spec["area_m2"],
        "people_count": spec["people"],
        "beds_count": spec.get("beds", 0),
        "institution_type": "public_institution",
        "family": "公共机构",
        "region": "浙江",
        "standard_package": (
            "energy-audit-core/references/standards/zhejiang/public_institution/"
        ),
        "calculated_at": datetime.now().isoformat(),
        "public_institution": {
            "subtype": spec["subtype"],
            "region": "浙江",
            "agency_level": spec.get("agency_level"),
            "venue_type": spec.get("venue_type"),
            "hospital_level": spec.get("hospital_level"),
            "results": results,
        },
    }
    mapping = {
        "unit_area_energy": ("kgce_per_m2", "unit_area_energy"),
        "per_capita_energy": ("kgce_per_person", "per_capita_energy"),
        "unit_area_electricity": ("kwh_per_m2", "unit_area_electricity"),
        "per_capita_electricity": (
            "kwh_per_person", "per_capita_electricity"
        ),
        "comparable_unit_area_energy": (
            "kgce_per_m2", "comparable_unit_area_energy"
        ),
        "eeue": ("ratio", "eeue"),
        "unit_water": ("m3_per_person", "unit_water"),
    }
    for key, (value_field, quota_key) in mapping.items():
        # 738 的医院主指标是修正后的“可比单位建筑面积能耗”。原始
        # unit_area_energy 只保留在 results[] 中作为过程量，避免写作端
        # 把未修正的数值当作主指标引用。
        if (
            key == "unit_area_energy"
            and latest.get("subtype") == "hospital"
        ):
            continue
        if value_field not in latest["values"]:
            continue
        labels = (
            ["通用值", "先进值"] if key == "unit_water"
            else ["约束值", "基准值", "引导值"]
        )
        out[key] = {
            value_field: latest["values"][value_field],
            "benchmark": _pb_benchmark(
                latest["quota"].get(quota_key) or [],
                labels,
                (
                    "浙江省用（取）水定额（2019）"
                    if key == "unit_water" else standard
                ),
                (
                    "表57"
                    if key == "unit_water" and spec["subtype"] in ("agency", "venue", "university")
                    else "表47"
                    if key == "unit_water"
                    else source
                ),
                latest["grade"].get(quota_key, "—"),
            ),
        }
    if "unit_water" in latest["values"]:
        out["water_indicator"] = out["unit_water"]
    return out


def _standard_chapter5_assets(
    proj: AuditProject,
    spec: dict,
    out_dir: Path,
    skip_charts: bool,
) -> tuple[dict, dict]:
    chart_dir = out_dir / "charts"
    config = {
        "unit_name": getattr(proj.base, "unit_name", ""),
        "building_area": spec.get("area_m2", 0),
        "people_count": spec.get("people", 0),
        "chart_dir": str(chart_dir),
        "chapter5_manifest_path": str(out_dir / "chapter5_figures.json"),
        "energy_flow_trees": list(getattr(proj, "energy_flow_trees", []) or []),
        "equipment": [
            {
                "category": getattr(eq, "category", ""),
                "name": getattr(eq, "name", ""),
                "quantity": getattr(eq, "quantity", 0) or 0,
            }
            for eq in (getattr(proj, "equipment", []) or [])
        ],
    }
    chart_data = {"energy_data": {}, "cost_data": {}}
    for year in spec.get("years", []):
        year_key = str(year["year"])
        chart_data["energy_data"][year_key] = {
            "electricity": {
                "total": float(year.get("electricity_kwh") or 0),
                "monthly": year.get("monthly_electricity_kwh") or [],
            },
            "water": {
                "total": float(year.get("water_t") or 0),
                "monthly": year.get("monthly_water_m3") or [],
            },
            "natural_gas": {
                "total": float(year.get("gas_m3") or 0),
                "monthly": year.get("monthly_natural_gas_m3") or [],
            },
            "heat": {
                "total": float(year.get("heat_gj") or year.get("heating_heat_gj") or 0),
                "monthly": [],
            },
        }
        chart_data["cost_data"][year_key] = {
            "electricity": {"name": "电费", "total": float(year.get("electricity_cost_wan") or 0)},
            "water": {"name": "水费", "total": float(year.get("water_cost_wan") or 0)},
            "natural_gas": {"name": "燃气费", "total": float(year.get("gas_cost_wan") or 0)},
            "heat": {"name": "热费", "total": float(year.get("heat_cost_wan") or 0)},
        }
    manifest = load_chapter5_manifest(config, str(chart_dir))
    if not skip_charts:
        manifest = generate_charts(chart_data, config, str(chart_dir))
    return config, manifest


def _save_standard_chapter5(
    *,
    proj: AuditProject,
    spec: dict,
    results: list[dict],
    out_dir: Path,
    standard_id: str,
    standard_title: str,
    metrics: list[dict],
    skip_charts: bool,
) -> Path:
    config, manifest = _standard_chapter5_assets(proj, spec, out_dir, skip_charts)
    chapter5 = render_standard_chapter5(
        spec=spec,
        results=results,
        unit_name=getattr(proj.base, "unit_name", ""),
        standard_id=standard_id,
        standard_title=standard_title,
        metrics=metrics,
        figures_manifest=manifest,
    )
    path = out_dir / "chapter5.md"
    path.write_text(chapter5, encoding="utf-8")
    return path


def run_shandong_public_building_caliber(
    project_name: str,
    proj: AuditProject,
    skip_charts: bool = False,
    output_dir: Optional[str] = None,
) -> dict:
    if not PUBLIC_BUILDING_AVAILABLE:
        return {"error": "山东公共建筑标准模块不可用"}
    family = _report_family_context(proj)
    if not family.is_shandong_public_building:
        return {"error": "当前项目不是山东公共建筑报告族"}
    raw = _load_raw_project_data(project_name)
    spec = build_shandong_public_building_spec(proj, raw)
    quota = load_shandong_public_building_quota()
    results = compute_shandong_public_building_indicators(spec, quota)
    indicators = build_shandong_public_building_indicators_json(proj, spec, results)
    out_dir = (
        Path(output_dir)
        if output_dir
        else Path.home() / "projects" / "energy-audit" / project_name
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = out_dir / "indicators.json"
    indicators_path.write_text(
        json.dumps(indicators, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    latest = results[-1]
    chapter5_path = _save_standard_chapter5(
        proj=proj,
        spec=spec,
        results=results,
        out_dir=out_dir,
        standard_id=latest["standard_id"],
        standard_title=quota[
            {
                "business_office": "db37_t_5078_2024",
                "hotel": "db37_t_5076_2024",
                "hospital": "db37_t_5079_2024",
            }[spec["subtype"]]
        ]["title"],
        metrics=_shandong_metrics(spec["subtype"]),
        skip_charts=skip_charts,
    )
    return {
        "indicators_path": str(indicators_path),
        "chapter5_path": str(chapter5_path),
        "indicators": indicators,
    }


def run_zhejiang_public_institution_caliber(
    project_name: str,
    proj: AuditProject,
    skip_charts: bool = False,
    output_dir: Optional[str] = None,
) -> dict:
    if not PUBLIC_BUILDING_AVAILABLE:
        return {"error": "浙江公共机构标准模块不可用"}
    family = _report_family_context(proj)
    if not family.is_zhejiang_public_institution:
        return {"error": "当前项目不是浙江公共机构报告族"}
    raw = _load_raw_project_data(project_name)
    spec = build_zhejiang_public_institution_spec(proj, raw)
    results = compute_zhejiang_public_institution_indicators(spec)
    indicators = build_zhejiang_public_institution_indicators_json(proj, spec, results)
    out_dir = (
        Path(output_dir)
        if output_dir
        else Path.home() / "projects" / "energy-audit" / project_name
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    indicators_path = out_dir / "indicators.json"
    indicators_path.write_text(
        json.dumps(indicators, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    latest = results[-1]
    titles = {
        "DB33/T 736-2021": "行政机关、场馆能耗定额及计算方法",
        "DB33/T 737-2021": "普通高等院校能耗定额及计算方法",
        "DB33/T 738-2021": "医疗机构能耗定额及计算方法",
    }
    chapter5_path = _save_standard_chapter5(
        proj=proj,
        spec=spec,
        results=results,
        out_dir=out_dir,
        standard_id=latest["standard_id"],
        standard_title=titles[latest["standard_id"]],
        metrics=_zhejiang_public_institution_metrics(latest),
        skip_charts=skip_charts,
    )
    return {
        "indicators_path": str(indicators_path),
        "chapter5_path": str(chapter5_path),
        "indicators": indicators,
    }


def build_public_building_indicators_json(proj: AuditProject, spec: dict,
                                          results: list) -> dict:
    latest = results[-1]
    subtype = spec["subtype"]
    out = {
        "project": getattr(proj.base, "unit_name", ""),
        "year": latest["year"],
        "building_area": spec["area_m2"],
        "people_count": spec["people"],
        "institution_type": "public_building",
        "family": "公共建筑",
        "calculated_at": datetime.now().isoformat(),
        "public_building": {
            "subtype": subtype,
            "level": spec.get("level"),
            "venue_type": spec.get("venue_type"),
            "star": spec.get("star"),
            "results": results,
        },
    }

    if subtype in ("office", "venue"):
        standard = "DB33/T 736-2021"
        source = "表1/表3（736）"
        out["unit_area_non_heating_energy"] = {
            "kgce_per_m2": latest["values"]["unit_area_energy"],
            "benchmark": _pb_benchmark(
                latest["quota"]["unit_area_energy"],
                ["约束值", "基准值", "引导值"], standard, source,
                latest["grade"]["unit_area_energy"]),
        }
        out["unit_area_electricity"] = {
            "kwh_per_m2": latest["values"]["unit_area_electricity"],
            "benchmark": _pb_benchmark(
                latest["quota"]["unit_area_electricity"],
                ["约束值", "基准值", "引导值"], standard, "表3（736）",
                latest["grade"]["unit_area_electricity"]),
        }
        out["per_capita_energy"] = {
            "kgce_per_person": latest["values"]["per_capita_energy"],
            "benchmark": _pb_benchmark(
                latest["quota"]["per_capita_energy"],
                ["约束值", "基准值", "引导值"], standard, "表1（736）",
                latest["grade"]["per_capita_energy"]),
        }
        out["per_capita_electricity"] = {
            "kwh_per_person": latest["values"]["per_capita_electricity"],
            "benchmark": _pb_benchmark(
                latest["quota"]["per_capita_electricity"],
                ["约束值", "基准值", "引导值"], standard, "表3（736）",
                latest["grade"]["per_capita_electricity"]),
        }
        out["water_indicator"] = {
            "m3_per_person": latest["values"]["unit_water"],
            "benchmark": _pb_benchmark(
                latest["quota"]["unit_water"],
                ["通用值", "先进值"], "浙江省用（取）水定额（2019）", "表57",
                latest["grade"]["unit_water"]),
        }
    else:
        out["unit_energy"] = {
            "kgce_per_m2": latest["values"]["unit_energy"],
            "benchmark": None,
        }
        out["unit_comparable_energy"] = {
            "kgce_per_m2": latest["values"]["unit_comparable_energy"],
            "benchmark": _pb_benchmark(
                latest["quota"]["unit_comparable_energy"],
                ["3级（限额值）", "2级（约束值）", "1级（先进值）"],
                "DB33/T 760-2023", "表1",
                latest["grade"]["unit_comparable_energy"]),
        }
        out["water_indicator"] = {
            "m3_per_bed": latest["values"]["water_per_bed"],
            "benchmark": _pb_benchmark(
                latest["quota"]["water"],
                ["通用值", "先进值"], "浙江省用（取）水定额（2019）", "表47",
                latest["grade"]["water"]),
        }
    return out


def run_public_building_caliber(project_name: str, proj: AuditProject,
                                skip_charts: bool = False,
                                output_dir: Optional[str] = None) -> dict:
    if not PUBLIC_BUILDING_AVAILABLE:
        return {"error": "公共建筑模块不可用"}
    try:
        family = _report_family_context(proj)
    except ReportFamilyUnsupported as exc:
        return {"error": str(exc)}
    if not family.is_public_building:
        return {"error": "当前项目不是浙江公共建筑报告族"}

    print(f"\n{'='*60}")
    print("📊 Caliber — 公共建筑（浙江）指标计算")
    print(f"{'='*60}")
    print(f"项目: {project_name}")

    raw = _load_raw_project_data(project_name)
    spec = build_public_building_spec(proj, raw)
    results = compute_public_building_indicators(spec)
    indicators = build_public_building_indicators_json(proj, spec, results)

    out_dir = Path(output_dir) if output_dir else Path.home() / "projects" / "energy-audit" / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    indicators_path = out_dir / "indicators.json"
    with open(indicators_path, "w", encoding="utf-8") as fh:
        json.dump(indicators, fh, ensure_ascii=False, indent=2, default=str)

    chart_dir = out_dir / "charts"
    manifest_path = out_dir / "chapter5_figures.json"
    config = {
        "unit_name": getattr(proj.base, "unit_name", project_name),
        "building_area": spec.get("area_m2", 0),
        "people_count": spec.get("people", 0),
        "chart_dir": str(chart_dir),
        "chapter5_manifest_path": str(manifest_path),
        "energy_flow_trees": list(getattr(proj, "energy_flow_trees", []) or []),
        "equipment": [
            {
                "category": getattr(eq, "category", ""),
                "name": getattr(eq, "name", ""),
                "quantity": getattr(eq, "quantity", 0) or 0,
            }
            for eq in (getattr(proj, "equipment", []) or [])
        ],
    }
    chart_data = {"energy_data": {}, "cost_data": {}}
    for year in spec.get("years", []):
        year_key = str(year["year"])
        chart_data["energy_data"][year_key] = {
            "electricity": {
                "total": float(year.get("electricity_kwh") or 0),
                "monthly": year.get("monthly_electricity_kwh") or [],
            },
            "water": {
                "total": float(year.get("water_t") or 0),
                "monthly": year.get("monthly_water_m3") or [],
            },
            "natural_gas": {
                "total": float(year.get("gas_m3") or 0),
                "monthly": year.get("monthly_natural_gas_m3") or [],
            },
            "heat": {
                "total": float(year.get("heat_gj") or 0),
                "monthly": [],
            },
        }
        chart_data["cost_data"][year_key] = {
            "electricity": {
                "name": "电费",
                "total": float(year.get("electricity_cost_wan") or 0),
            },
            "water": {
                "name": "水费",
                "total": float(year.get("water_cost_wan") or 0),
            },
            "natural_gas": {
                "name": "燃气费",
                "total": float(year.get("gas_cost_wan") or 0),
            },
            "heat": {
                "name": "热费",
                "total": float(year.get("heat_cost_wan") or 0),
            },
        }
    figures_manifest = load_chapter5_manifest(config, str(chart_dir))
    if not skip_charts:
        figures_manifest = generate_charts(
            chart_data, config, str(chart_dir)
        )
        available = sum(
            1 for item in figures_manifest.get("figures", [])
            if item.get("status") != "missing"
        )
        missing = sum(
            1 for item in figures_manifest.get("figures", [])
            if item.get("status") == "missing"
        )
        print(f"  ✅ 图表: {chart_dir}（可用 {available}，缺图 {missing}）")

    chapter5_path = out_dir / "chapter5.md"
    chapter5 = render_public_building_chapter5(
        spec,
        results,
        getattr(proj.base, "unit_name", project_name),
        figures_manifest=figures_manifest,
    )
    with open(chapter5_path, "w", encoding="utf-8") as fh:
        fh.write(chapter5)

    report_lines = [
        f"项目: {indicators['project']}（{spec['subtype']}）",
        f"年度: {indicators['year']} | 面积: {spec['area_m2']:.2f} m²",
        "",
    ]
    for r in results:
        report_lines.append(f"{r['year']}年：")
        for key, value in r["values"].items():
            if key in ("water_per_bed", "water_per_bed_normalized"):
                grade_key = "water"
            elif key == "unit_energy":
                grade_key = None
            else:
                grade_key = key
            grade = r["grade"].get(grade_key, "参考指标") if grade_key else "参考指标"
            report_lines.append(f"  {key}: {value}  [{grade}]")
        report_lines.append("")
    report_path = out_dir / "indicators_report.txt"
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(report_lines))

    print(f"  ✅ 指标: {indicators_path}")
    print(f"  ✅ 第5章: {chapter5_path}")
    print("\n".join(report_lines))
    return {
        "indicators_path": str(indicators_path),
        "chapter5_path": str(chapter5_path),
        "indicators": indicators,
    }


# ================================================================
#  完整流程
# ================================================================

def run_caliber(
    project_name: str,
    skip_charts: bool = False,
    output_dir: Optional[str] = None,
) -> dict:
    """执行完整的指标计算与第5章生成流程"""
    if not TOOLS_AVAILABLE:
        return {"error": "工具导入失败"}

    print(f"\n{'='*60}")
    print(f"📊 Caliber — 能耗指标计算与第5章生成")
    print(f"{'='*60}")
    print(f"项目: {project_name}")

    # Step 1: 加载
    print("[1/5] 📂 加载项目数据...")
    proj = load_project(project_name)
    if proj is None:
        msg = f"项目 '{project_name}' 数据不存在"
        print(f"  ❌ {msg}")
        return {"error": msg}
    print(f"  ✅ 加载成功 | 建筑: {len(getattr(proj, 'buildings', []))}栋 | "
          f"能耗: {len(getattr(proj, 'energy_yearly', []))}年")

    try:
        family = _report_family_context(proj)
    except ReportFamilyUnsupported as exc:
        return {"error": str(exc)}

    # 四类报告族严格分诊：省份和报告族共同决定标准包，建筑功能本身不够。
    if family.is_shandong_public_building:
        return run_shandong_public_building_caliber(
            project_name=project_name,
            proj=proj,
            skip_charts=skip_charts,
            output_dir=output_dir,
        )
    if family.is_zhejiang_public_building:
        return run_public_building_caliber(
            project_name=project_name,
            proj=proj,
            skip_charts=skip_charts,
            output_dir=output_dir,
        )
    if family.is_zhejiang_public_institution:
        return run_zhejiang_public_institution_caliber(
            project_name=project_name,
            proj=proj,
            skip_charts=skip_charts,
            output_dir=output_dir,
        )

    # Step 2: 提取
    print("[2/5] 🔄 提取年度能耗数据...")
    yearly_data = extract_yearly_data(proj)
    if not yearly_data:
        print("  ❌ 无有效年度能耗数据")
        return {"error": "无能耗数据"}
    years = sorted(d.year for d in yearly_data)
    print(f"  ✅ {len(yearly_data)} 年 ({', '.join(map(str, years))})")

    # Step 3: 计算指标
    print("[3/5] 🧮 计算5项指标 + 定额对标 + 能耗基准...")
    results = calc_all_indicators(proj, yearly_data)

    # 输出指标预览
    r1 = results.get('unit_area_non_heating_energy', {})
    r2 = results.get('unit_area_electricity', {})
    bm1 = r1.get('benchmark') or {}
    bm2 = r2.get('benchmark') or {}
    print(f"  ✅ 非供暖能耗: {r1.get('kgce_per_m2','-')} kgce/m² [{bm1.get('评价结果','-')}]")
    print(f"  ✅ 常规电耗: {r2.get('kwh_per_m2','-')} kWh/m² [{bm2.get('评价结果','-')}]")
    print(f"  ✅ 人均能耗: {results.get('per_capita_energy',{}).get('kgce_per_person','-')} kgce/人")
    r4 = results.get('water_indicator') or results.get('per_capita_water', {})  # 旧键兼容
    if 'L_per_bed_day' in r4:
        print(f"  ✅ 床日用水: {r4.get('L_per_bed_day','-')} L/(床·d)")
    else:
        print(f"  ✅ 人均取水: {r4.get('m3_per_person','-')} m³/(人·a)")

    # Step 4: 生成第5章
    print("[4/5] 📝 生成第5章 Markdown...")
    out_dir = Path(output_dir) if output_dir else Path.home() / 'projects' / 'energy-audit' / project_name
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 费用数据（万元）：proj.energy_yearly 费用字段 → chapter5_agent cost_data 格式
        # 表5.1 + 费用占比饼图依赖此数据，缺则 5.2 费用节空壳（2026-09-05 修复）
        cost_data = {}
        for ey in getattr(proj, 'energy_yearly', []):
            cost_data[str(ey.year)] = {
                'electricity': {'name': '电费', 'unit': '万元',
                                'total': float(getattr(ey, 'electricity_cost_wan', 0) or 0),
                                'monthly': [0] * 12},
                'water': {'name': '水费', 'unit': '万元',
                          'total': float(getattr(ey, 'water_cost_wan', 0) or 0),
                          'monthly': [0] * 12},
                'natural_gas': {'name': '天然气费', 'unit': '万元',
                                'total': float(getattr(ey, 'natural_gas_cost_wan', 0) or 0),
                                'monthly': [0] * 12},
                'heat': {'name': '热费', 'unit': '万元',
                         'total': float(getattr(ey, 'heating_cost_wan', 0) or 0),
                         'monthly': [0] * 12},
                'gasoline': {'name': '汽油费', 'unit': '万元',
                             'total': float(getattr(ey, 'petrol_cost_wan', 0) or 0),
                             'monthly': [0] * 12},
                'diesel': {'name': '柴油费', 'unit': '万元',
                           'total': float(getattr(ey, 'diesel_cost_wan', 0) or 0),
                           'monthly': [0] * 12},
            }
        # 供暖电耗明细（kWh）：energy_data dict 无法承载"总电的子集"，走 config 顶层 map 通道
        heating_energy_kwh_map = {str(d.year): float(getattr(d, 'heating_energy_kwh', 0) or 0)
                                  for d in yearly_data}
        energy_data_dict = _build_energy_data_dict(yearly_data, proj)
        config = {
            'building_area': getattr(proj.base, 'building_area', 0),
            'people_count': getattr(proj.base, 'people_count', 0),
            'unit_name': getattr(proj.base, 'unit_name', project_name),
            'chart_dir': str(out_dir / 'charts'),
            # 机构类型与床位数：5.3.4 取水公式分支依据（2026-09-05 修复：
            # 漏传导致非机关项目 md 按机关口径，与 indicators.json 打架）
            'institution_category': getattr(proj.base, 'institution_category', '') or '',
            'beds_count': getattr(proj.base, 'beds_count', 0) or 0,
            # 二级维度定档（2026-09-20）：平台字典码 + 地址（+行政区划代码），
            # 供 chapter5 拼 sub_type；否则教育类只能取默认档
            'unit_func': getattr(proj.base, 'unit_func', '') or '',
            'children_func': getattr(proj.base, 'children_func', '') or '',
            'city': getattr(proj.base, 'city', '') or '',
            'district': getattr(proj.base, 'district', '') or '',
            'address': getattr(proj.base, 'address', '') or '',
            'district_id': getattr(proj.base, 'district_id', '') or '',
            # 折标系数（data.json 持久化，三年一致取最新年）：md 与
            # indicators.json 同口径（2026-09-05 修复）
            'coefficients': dict(getattr(yearly_data[-1], 'coefficients', {}) or {}),
            # 采暖建筑面积：_resolve_heating_area 口径判别（5.3.5 供暖指标分母；
            # 缺失/全 0 时 generate_chapter5_md 走建筑总面积兜底）
            'heating_area': _resolve_heating_area(proj),
            # 地下车库面积：建筑表 garage_area 聚合（D8：5.3.1/5.3.2 分母剔除）
            'garage_area': sum(float(getattr(b, 'garage_area', 0) or 0)
                               for b in getattr(proj, 'buildings', []) or []),
            'heating_energy_kwh_map': heating_energy_kwh_map,
            # 图5.1 数据源（2026-09-24 接入）：data.json 的能源流向树（平台为客户登记的
            # ts_energy_flow/_level）→ chapter5 直接画库树；为空则画两层简化图。
            # 同时补传设备清单（此前**整条链没人传 equipment**，graphviz 兜底图只能
            # 用硬编码默认设备名，如烟台法院被写成"分体式空调"）。
            'energy_flow_trees': list(getattr(proj, 'energy_flow_trees', []) or []),
            'equipment': [dict(category=getattr(e, 'category', ''), name=getattr(e, 'name', ''),
                               quantity=getattr(e, 'quantity', 0) or 0)
                          for e in (getattr(proj, 'equipment', []) or [])],
            'manual': {
                'energy_data': energy_data_dict,
                'cost_data': cost_data,
                'sub_items': {},
            },
        }
        chapter5_md = gen_chapter5(
            config,
            str(out_dir / 'chapter5.md'),
            skip_charts=skip_charts,
        )
        print(f"  ✅ 第5章: {len(chapter5_md)} 字符 → {out_dir / 'chapter5.md'}")
    except Exception as e:
        print(f"  ⚠️ 第5章生成失败: {e}")
        chapter5_md = f"# 第5章\n\n⚠️ 生成失败: {e}\n"

    # Step 5: 持久化
    print("[5/5] 💾 保存结果...")
    # 指标 JSON
    indicators_path = out_dir / 'indicators.json'
    with open(indicators_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✅ 指标: {indicators_path}")

    # 文本报告
    report = format_indicators_report(results)
    report_path = out_dir / 'indicators_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  ✅ 报告: {report_path}")

    # 打印总结
    print(report)

    return {
        'indicators_path': str(indicators_path),
        'chapter5_path': str(out_dir / 'chapter5.md'),
        'indicators': results,
    }


def _build_energy_data_dict(yearly_data: List[YearlyEnergyData], proj: AuditProject) -> dict:
    """将 YearlyEnergyData 列表转为 chapter5_agent 所需的 energy_data dict 格式"""
    energy_data = {}
    for d in yearly_data:
        y = str(d.year)
        energy_data[y] = {
            'electricity': {
                'name': '电能', 'unit': 'kWh',
                'total': d.electricity_kwh,
                'monthly': _get_monthly(proj, d.year, 'monthly_electricity_kwh'),
            },
            'water': {
                'name': '水', 'unit': 'm³',
                'total': d.water_m3,
                'monthly': _get_monthly(proj, d.year, 'monthly_water_m3'),
            },
            'natural_gas': {
                'name': '天然气', 'unit': 'm³',
                'total': d.natural_gas_m3,
                'monthly': _get_monthly(proj, d.year, 'monthly_natural_gas_m3'),
            },
            'heat': {
                'name': '热能', 'unit': 'GJ',
                'total': d.heating_energy_heat,
                'monthly': [0]*12,
            },
        }
        # 汽油/柴油（kg）：>0 才写入，避免 0 值类型污染 5.1/5.2 输出
        if getattr(d, 'transportation_petrol_kg', 0) > 0:
            energy_data[y]['gasoline'] = {
                'name': '汽油', 'unit': 'kg',
                'total': d.transportation_petrol_kg,
                'monthly': [0]*12,
            }
        if getattr(d, 'transportation_diesel_kg', 0) > 0:
            energy_data[y]['diesel'] = {
                'name': '柴油', 'unit': 'kg',
                'total': d.transportation_diesel_kg,
                'monthly': [0]*12,
            }
    return energy_data


def _get_monthly(proj, year: int, field: str) -> List[float]:
    """从 AuditProject 中提取某年的月度数据"""
    for ey in getattr(proj, 'energy_yearly', []):
        if getattr(ey, 'year', 0) == year:
            vals = getattr(ey, field, None) or []
            if isinstance(vals, list) and len(vals) == 12:
                return [float(v or 0) for v in vals]
    return [0] * 12


# ================================================================
#  CLI
# ================================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Caliber — 能耗指标计算与第5章生成")
    parser.add_argument('project_name', help='项目名称')
    parser.add_argument('--skip-charts', action='store_true', help='跳过图表生成')
    parser.add_argument('--output-dir', help='输出目录')
    args = parser.parse_args()

    result = run_caliber(
        project_name=args.project_name,
        skip_charts=args.skip_charts,
        output_dir=args.output_dir,
    )
    if 'error' in result:
        print(f"\n❌ {result['error']}")
        sys.exit(1)
