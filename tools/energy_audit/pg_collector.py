"""
PG数据采集器 —— datacollection agent v2 tool
先查PG数据库中已有的项目数据，再报告缺失项供用户补充。

作者: 马天远 | 版本: 2.1.0 | 日期: 2026-08-03
prod - serial number - 3
"""

import sys

from tools.energy_audit import PgDataQuery
from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401
from typing import Any, Dict

from tools.energy_audit.project_data import (
    AuditProject, ProjectBase, BuildingInfo, EnergyYearly,
    Equipment, MeteringInfo, ManagementInfo,
    save_project, SourceResolver, first_non_empty_source,
    is_valid_coefficient,
)
from tools.energy_audit.indicators import compute_project_indicators


# ============================================================
# collect_from_pg — 从 PG 数据库采集项目数据
# ============================================================

def collect_from_pg(project_name: str) -> Dict[str, Any]:
    """从PG数据库采集指定项目的全部数据。

    返回: {found: {...}, missing: [...], project_id: ...}
    连接生命周期由本函数统一管理：try/finally 保证任意分支/异常下均释放连接。
    """
    pg = PgDataQuery()
    pg.connect()
    try:
        return _collect_from_pg_impl(pg, project_name)
    finally:
        pg.disconnect()


def _yn(v, yes='有', no='无'):
    if v is None:
        return ''
    try:
        return yes if int(v) == 1 else no
    except (TypeError, ValueError):
        return ''


def _bool_cn(v, yes='是', no='否'):
    return _yn(v, yes, no)


def _num(v, default=0.0):
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v, default=0):
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _date(v):
    if v is None:
        return ''
    try:
        return v.isoformat()
    except AttributeError:
        return str(v) if v else ''


def _sunshade(v):
    if v is None or v == '':
        return ''
    s = str(v).strip()
    mapping = {'1': '外遮阳', '2': '中遮阳', '3': '内遮阳',
               '外': '外遮阳', '中': '中遮阳', '内': '内遮阳'}
    return mapping.get(s, s)


def _collect_from_pg_impl(pg: PgDataQuery, project_name: str) -> Dict[str, Any]:
    """collect_from_pg 的实现体。统一通过 PgDataQuery 查询，避免硬编码字段与实际表结构不一致。"""
    result = {
        'found': {},
        'missing': [],
        'project_id': None,
    }

    # ---- 1. 查找项目 ----
    proj = pg.find_project_by_name(project_name)
    if not proj:
        result['missing'].append('项目基本信息（未在PG中找到该项目）')
        return result

    result['project_id'] = proj['id']
    customer_id = proj.get('customer_id')

    result['found']['project'] = {
        'unit_name': proj.get('audited_name', ''),
        'contact_person': proj.get('audited_person', ''),
        'contact_phone': proj.get('audited_tel', ''),
        'auditor': proj.get('audit_dept_name', ''),
    }
    if proj.get('audit_year'):
        result['found']['project']['audit_year'] = proj['audit_year']
    if proj.get('reference_year'):
        result['found']['project']['data_year'] = proj['reference_year']
    result['found']['project'].update({
        'commission_person': proj.get('commission_person', ''),
        'commission_tel': proj.get('commission_tel', ''),
        'status': proj.get('status', ''),
        'remark': proj.get('remark', ''),
        'energy_codes': proj.get('energy_codes', ''),
        'audit_template': proj.get('audit_template', ''),
    })

    # ---- 1.5 客户信息 ----
    if customer_id:
        cust = pg.get_customer_info(customer_id=customer_id)
        if cust:
            result['found']['customer_info'] = cust[0]
        else:
            result['missing'].append('客户信息（ts_customer_info 无记录）')
    else:
        result['missing'].append('客户信息（项目未关联 customer_id）')

    # ---- 2. 建筑信息 ----
    buildings = []
    for b in pg.get_institution_build(customer_id=customer_id):
        up_floor = _num(b.get('up_floor'), 0)
        down_floor = _num(b.get('down_floor'), 0)
        floors = (f"地上{_int(up_floor)}层" if up_floor else '') + (
            f"地下{_int(down_floor)}层" if down_floor else ''
        )

        buildings.append({
            'name': b.get('build_name') or '',
            'address': b.get('address') or '',
            'year': _int(b.get('build_year')),
            'function': b.get('build_func') or '',
            'function_zoning': b.get('build_func_region') or '',
            'other_function_zoning': b.get('other_build_func_region') or '',
            'up_floor': _int(up_floor),
            'down_floor': _int(down_floor),
            'floors': floors,
            'height': str(b.get('build_height')) if b.get('build_height') is not None else '',
            'orientation': b.get('build_face') or '',
            'area': _num(b.get('build_area'), 0.0),
            'use_area': _num(b.get('use_area'), 0.0),
            'cooling_area': _num(b.get('cold_area'), 0.0),
            'heating_area': _num(b.get('heat_area'), 0.0),
            'cold_terminal_area': _num(b.get('cold_terminal_area'), 0.0),
            'heat_terminal_area': _num(b.get('heat_terminal_area'), 0.0),
            'structure': b.get('stru_type') or '',
            'other_structure': b.get('other_stru_type') or '',
            'wall_body_material': b.get('wallbody_thickness') or '',
            'other_wall_body_material': b.get('other_wallbody_thickness') or '',
            'window_type': b.get('wallwin_type') or '',
            'other_window_type': b.get('other_wallwin_type') or '',
            'insulation': b.get('wallwarm_type') or '',
            'other_insulation': b.get('other_wallwarm_type') or '',
            'wall_material': b.get('warm_material') or '',
            'other_warm': b.get('other_warm') or '',
            'warm_thickness': str(b.get('warm_thickness')) if b.get('warm_thickness') is not None else '',
            'warm_state': b.get('warm_state') or '',
            'wall_insulation_change': _int(b.get('wallwarm_change')),
            'roof_insulation': _yn(b.get('is_roomwarm')),
            'roof_insulation_material': b.get('roomwarm_material') or '',
            'roof_insulation_thickness': str(b.get('roomwarm_thickness')) if b.get('roomwarm_thickness') is not None else '',
            'roof_insulation_state': b.get('roomwarm_state') or '',
            'roof_insulation_change': _int(b.get('roomwarm_change')),
            'sunshade_type': _sunshade(b.get('build_sunshade')),
            'sunshade_material': b.get('sunshade_thickness') or '',
            'sunshade_install': b.get('sunshade_install') or '',
            'cooling_source': b.get('cold_source') or '',
            'cold_time': b.get('cold_time') or '',
            'cold_date': b.get('cold_date') or '',
            'heating_source': b.get('heat_source') or '',
            'heat_time': b.get('heat_time') or '',
            'heat_date': b.get('heart_date') or '',
            'cooling_terminal': b.get('air_type') or '',
            'heating_terminal': b.get('heat_type') or '',
            'water_system': b.get('water_supply') or '',
            'fire_system': b.get('fire_water_supply') or '',
            'hot_water': b.get('hot_water_supply') or '',
            'monitoring': _yn(b.get('energy_system')),
            'storey_metrology': _bool_cn(b.get('storey_metrology')),
            'run_time': b.get('build_run_time') or '',
            'begin_date': _date(b.get('use_begin_date')),
            'end_date': _date(b.get('use_end_date')),
            'garage': _yn(b.get('garage')),
            'garage_area': _num(b.get('garage_area'), 0.0),
        })

    if buildings:
        result['found']['buildings'] = buildings

    # ---- 3. 能耗数据 ----
    main_records = pg.get_institution_energy(customer_id=customer_id)

    yearly_map = {}
    for rec in main_records:
        year_str = rec['year']
        year = _int(year_str) if year_str and str(year_str).isdigit() else 0
        if year == 0:
            continue
        dt = _int(rec.get('data_type'))
        total = float(rec['unit_total_value'] or 0)
        monthly = [rec.get(f'value{i}', 0.0) for i in range(1, 13)]

        if year not in yearly_map:
            yearly_map[year] = {}

        code_map = {
            # energy_name/code_id: (quantity_field, monthly_field, coeff_type)
            '电能': ('electricity_kwh', 'monthly_electricity_kwh', 'electricity'),
            '45': ('electricity_kwh', 'monthly_electricity_kwh', 'electricity'),
            '水': ('water_m3', 'monthly_water_m3', 'water'),
            '01': ('water_m3', 'monthly_water_m3', 'water'),
            '天然气': ('natural_gas_m3', 'monthly_natural_gas_m3', 'natural_gas'),
            '25': ('natural_gas_m3', 'monthly_natural_gas_m3', 'natural_gas'),
            '热能': ('heating_energy_heat_gj', None, 'heat'),
            '50': ('heating_energy_heat_gj', None, 'heat'),
            '汽油': ('petrol_kg', None, 'gasoline'),
            '300301': ('petrol_kg', None, 'gasoline'),
            '柴油': ('diesel_kg', None, 'diesel'),
            '300302': ('diesel_kg', None, 'diesel'),
        }

        code_name = rec.get('energy_name') or ''
        code_id = rec.get('energy_code') or ''

        matched = code_map.get(code_name) or code_map.get(code_id)
        if matched:
            field, monthly_field, coeff_type = matched
            building_total = float(rec.get('building_total_value') or 0)
            unit_total = total
            building_value = building_total if building_total > unit_total else 0
            if dt == 1:
                yearly_map[year][field] = total
                if building_value:
                    yearly_map[year][f'building_{field}'] = building_value
                if monthly_field and any(v > 0 for v in monthly):
                    yearly_map[year][monthly_field] = monthly
                # 记录折标煤系数及其来源（仅保存有效值）
                coeff = rec.get('standard_coal_coefficient')
                if is_valid_coefficient(coeff):
                    yearly_map[year].setdefault('coefficients', {})[coeff_type] = float(coeff)
                    yearly_map[year].setdefault('coefficient_sources', {})[coeff_type] = 'PG'
            elif dt == 2:
                cost_map = {
                    '电能': 'electricity_cost_wan', '45': 'electricity_cost_wan',
                    '水': 'water_cost_wan', '01': 'water_cost_wan',
                    '热能': 'heating_cost_wan', '50': 'heating_cost_wan',
                    '柴油': 'diesel_cost_wan', '300302': 'diesel_cost_wan',
                    '汽油': 'petrol_cost_wan', '300301': 'petrol_cost_wan',
                }
                cost_field = cost_map.get(code_name) or cost_map.get(code_id)
                if cost_field:
                    yearly_map[year][cost_field] = total / 10000

    energy_yearly = []
    for year in sorted(yearly_map.keys()):
        d = yearly_map[year]
        d['year'] = year
        energy_yearly.append(d)

    if energy_yearly:
        result['found']['energy_yearly'] = energy_yearly

    # ---- 4. 设备数据 ----
    equipment = pg.get_formatted_equipment(customer_id=customer_id)
    if equipment:
        result['found']['equipment'] = equipment

    # ---- 5. 人员 ----
    audit_users = [{'name': r.get('name'), 'position': r.get('position'),
                    'degree': r.get('degree'), 'qualification': r.get('qualifications'),
                    'major': r.get('major')}
                   for r in pg.get_project_audit_users(project_id=result['project_id'])]
    if audit_users:
        result['found']['team_members'] = audit_users

    audited_users = [{'name': r.get('name'), 'position': r.get('position'),
                      'department': r.get('department')}
                     for r in pg.get_project_audited_users(project_id=result['project_id'])]
    if audited_users:
        result['found']['audited_users'] = audited_users

    # ---- 6. 用能场景（计量/供暖） ----
    scenes = pg.get_institution_scene(customer_id=customer_id)
    if scenes:
        scene = scenes[0]
        metering = {
            'has_monitoring_system': scene.get('energy_metering') == 1 if scene.get('energy_metering') is not None else False,
            'has_separate_metering': scene.get('separate_meter') == 1 if scene.get('separate_meter') is not None else False,
            'has_household_metering': scene.get('mode') == 1 if scene.get('mode') is not None else False,
        }
        result['found']['metering'] = metering
        if not scene.get('heat_day'):
            result['missing'].append('供暖信息（供热面积/供热天数/热价未记录）')

    # ---- 6.5 表具计量信息 ----
    meters = pg.get_energy_meter(customer_id=customer_id)
    if meters:
        result['found']['energy_meter'] = meters

    # ---- 6.6 折标系数 ----
    standards = pg.get_energy_standards()
    if standards:
        result['found']['energy_standards'] = standards
    else:
        result['missing'].append('能源折标系数（ts_energy_standard）')

    # ---- 7. 整理缺失清单 ----
    req = [
        ('buildings', '建筑信息（ts_institution_build）'),
        ('energy_yearly', '能耗数据（ts_institution_energy_main）'),
        ('equipment', '设备数据（ts_institution_device_*）'),
        ('metering', '计量信息'),
        ('energy_meter', '表具计量信息（ts_institution_energy_meter）'),
    ]
    for key, label in req:
        if key not in result['found']:
            result['missing'].append(label)

    return result


def build_from_pg_and_config(project_name: str, config: dict = None) -> AuditProject:
    """
    datacollection Agent v2：先查PG，缺失的用config补充。
    """
    print(f"[datacollection v2] 正在从PG查询项目: {project_name}")
    pg_data = collect_from_pg(project_name)

    found_count = len(pg_data['found'])
    missing_count = len(pg_data['missing'])
    print(f"[datacollectionv2] PG查询完成: 找到{found_count}类数据, 缺失{missing_count}项")

    if pg_data['missing']:
        print("\n⚠️ 以下数据未在PG中找到，需从config或手动补充：")
        for m in pg_data['missing']:
            print(f"  · {m}")
        print()

    config = config or {}
    sr = SourceResolver()

    pg_project = pg_data['found'].get('project', {})
    pg_buildings = pg_data['found'].get('buildings', [])
    pg_energy = pg_data['found'].get('energy_yearly', [])
    pg_equipment = pg_data['found'].get('equipment', [])
    pg_metering = pg_data['found'].get('metering', {})
    pg_building_area = sum(b['area'] for b in pg_buildings) or 0

    proj = AuditProject(
        base=ProjectBase(
            name=f"{project_name}能源审计",
            unit_name=sr.resolve('unit_name',
                                 ('PG', pg_project),
                                 ('Config', config),
                                 ('default', project_name)),
            unit_short=sr.resolve('unit_short',
                                  ('Config', config),
                                  ('default', project_name)),
            address=sr.resolve('address',
                               ('Config', config),
                               ('default', '')),
            unit_type=sr.resolve('unit_type',
                                 ('Config', config),
                                 ('default', '公共机构')),
            institution_category=sr.resolve('institution_category',
                                            ('Config', config),
                                            ('default', '')),
            specific_type=sr.resolve('specific_type',
                                     ('Config', config),
                                     ('default', '')),
            contact_person=sr.resolve('contact_person',
                                      ('PG', pg_project),
                                      ('Config', config),
                                      ('default', '')),
            contact_phone=sr.resolve('contact_phone',
                                     ('PG', pg_project),
                                     ('Config', config),
                                     ('default', '')),
            auditor=sr.resolve('auditor',
                               ('PG', pg_project),
                               ('Config', config),
                               ('default', '同方德诚（山东）科技股份公司')),
            building_area=sr.resolve('building_area',
                                     ('PG', pg_building_area),
                                     ('Config', config),
                                     ('default', 0)),
            people_count=sr.resolve('people_count',
                                    ('Config', config),
                                    ('default', 300)),
            beds_count=sr.resolve('beds_count',
                                  ('Config', config),
                                  ('default', 0)),
            province=sr.resolve('province',
                                ('Config', config),
                                ('default', '山东')),
            audit_start=sr.resolve('audit_start',
                                   ('Config', config),
                                   ('default', '')),
            audit_end=sr.resolve('audit_end',
                                 ('Config', config),
                                 ('default', '')),
            data_start=sr.resolve('data_start',
                                  ('Config', config),
                                  ('default', '')),
            data_end=sr.resolve('data_end',
                                ('Config', config),
                                ('default', '')),
            report_date=sr.resolve('report_date',
                                   ('Config', config),
                                   ('default', '')),
        ),
        buildings=[BuildingInfo(**b) for b in pg_buildings],
        energy_yearly=[EnergyYearly(**ey) for ey in pg_energy],
        equipment=[Equipment(**e) for e in pg_equipment],
        metering=MeteringInfo(**pg_metering),
        management=ManagementInfo(),
    )

    if not proj.buildings and config.get('buildings'):
        proj.buildings = [BuildingInfo(**b) for b in config['buildings']]
    if not proj.energy_yearly and config.get('energy_yearly'):
        proj.energy_yearly = [EnergyYearly(**ey) for ey in config['energy_yearly']]
    pg_cats = {e.category for e in proj.equipment}
    for e in config.get('equipment', []):
        if e.get('category') not in pg_cats:
            proj.equipment.append(Equipment(**e))

    # 记录集合/对象级数据来源
    proj.data_sources = sr.sources
    proj.data_sources['name'] = 'derived'
    proj.data_sources['buildings'] = first_non_empty_source(
        ('PG', pg_buildings),
        ('Config', config.get('buildings', [])),
    )
    proj.data_sources['energy_yearly'] = first_non_empty_source(
        ('PG', pg_energy),
        ('Config', config.get('energy_yearly', [])),
    )
    proj.data_sources['equipment'] = first_non_empty_source(
        ('PG', pg_equipment),
        ('Config', config.get('equipment', [])),
    )
    proj.data_sources['metering'] = first_non_empty_source(
        ('PG', pg_metering),
    )
    proj.data_sources['management'] = 'default'

    try:
        proj.indicators = compute_project_indicators(proj)
        proj.data_sources['indicators'] = 'computed'
        if proj.indicators.get('status') == 'ok':
            print(f"[datacollection v2] 项目指标已预计算完成：{len(proj.indicators.get('yearly', []))} 个年度")
        else:
            print(f"[datacollection v2] 项目指标待补充：{proj.indicators.get('reason', '')}")
    except Exception as e:
        print(f"[datacollection v2] 指标计算阶段异常（不影响数据保存）: {e}")
        proj.indicators = {'status': 'pending', 'reason': str(e)}
        proj.data_sources['indicators'] = 'failed'

    save_project(proj)
    return proj


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "莘县县政府"
    result = collect_from_pg(name)
    print(f"\n=== PG查询结果: {name} ===")
    for k, v in result['found'].items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} 条记录")
        elif isinstance(v, dict):
            print(f"  {k}: {list(v.keys())[:5]}...")
    if result['missing']:
        print(f"\n  缺失: {len(result['missing'])} 项")
        for m in result['missing']:
            print(f"    - {m}")
