"""
PG数据采集器 —— datacollection agent v2 tool
先查PG数据库中已有的项目数据，再报告缺失项供用户补充。

作者: 马天远 | 版本: 2.1.0 | 日期: 2026-08-03
prod - serial number - 3
"""

from datetime import datetime
import calendar
import re
import sys

from dataclasses import fields
from typing import Any, Dict, List, Tuple

from tools.energy_audit import PgDataQuery
from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401

from tools.energy_audit.project_data import (
    AuditProject, ProjectBase, BuildingInfo, EnergyYearly, EnergyMonthly,
    Equipment, MeteringInfo, ManagementInfo, EnergySaving, SharedOfficeUnit,
    TeamMember, CoopMember, ImageItem,
    save_project, SourceResolver, first_non_empty_source,
    is_valid_coefficient, total_building_area,
)
from tools.energy_audit.indicators import compute_project_indicators
from tools.energy_audit.institution_classifier import classify_institution
from tools.energy_audit.file_resolver import (
    enrich_energy_saving_images,
    enrich_management_info,
    enrich_meter_ledger,
    parse_file_ids,
    resolve_attachment_urls,
    download_attachment_images,
)

# ts_customer_info.field_type → ProjectBase.unit_type（审计类型）
_FIELD_TYPE_UNIT = {
    '10': '公共机构',
    '20': '公共建筑',
    '30': '工业企业',
}


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


def _resolve_auditor(sr, pg_project: dict, excel_data: dict) -> str:
    """审计机构名称解析：PG 中疑似测试数据（含'测试'）时回退默认正式机构名。"""
    val = sr.resolve('auditor',
                     ('PG', pg_project),
                     ('Excel', excel_data),
                     ('default', '同方德诚（山东）科技股份公司'))
    if val and '测试' in str(val):
        return '同方德诚（山东）科技股份公司'
    return val


def _expand_energy_monthly(energy_yearly) -> list:
    """从 EnergyYearly 的 monthly_* 列表展开为 EnergyMonthly 行（第5章图表用）。"""
    rows = []
    for ey in energy_yearly:
        me = getattr(ey, 'monthly_electricity_kwh', None) or []
        mw = getattr(ey, 'monthly_water_m3', None) or []
        mg = getattr(ey, 'monthly_natural_gas_m3', None) or []
        for m in range(12):
            rows.append(EnergyMonthly(
                year=ey.year, month=m + 1,
                electricity_kwh=float(me[m]) if m < len(me) else 0,
                water_m3=float(mw[m]) if m < len(mw) else 0,
                natural_gas_m3=float(mg[m]) if m < len(mg) else 0,
            ))
    return rows


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


def parse_audit_year_range(audit_year) -> Tuple[str, str]:
    """把 ts_institution_project.audit_year 解析为 (audit_start, audit_end)。

    示例：
      2022-5~2022-10  → ('2022年5月', '2022年10月')
      2023~2024       → ('2023年', '2024年')
      2025            → ('2025年', '2025年')
    """
    if audit_year is None:
        return '', ''
    text = str(audit_year).strip()
    if not text:
        return '', ''
    parts = [p.strip() for p in re.split(r'[~～至—–]+', text) if p.strip()]
    if not parts:
        return '', ''
    start = _format_audit_year_part(parts[0])
    end = _format_audit_year_part(parts[1] if len(parts) > 1 else parts[0])
    return start, end


def _format_audit_year_part(part: str) -> str:
    matched = re.match(r'^(\d{4})(?:[-./年](\d{1,2}))?月?$', part.strip())
    if not matched:
        return part
    year, month = matched.group(1), matched.group(2)
    if month:
        return f"{year}年{int(month)}月"
    return f"{year}年"


def parse_data_year_range(data_year) -> Tuple[str, str]:
    """把单个年度字段解析为 (data_start, data_end) ISO 日期。

    示例：
      2023~2024       → ('2023-01-01', '2024-12-31')
      2022-5~2022-10  → ('2022-05-01', '2022-10-31')
      2025            → ('2025-01-01', '2025-12-31')
    """
    if data_year is None:
        return '', ''
    text = str(data_year).strip()
    if not text:
        return '', ''
    parts = [p.strip() for p in re.split(r'[~～至—–]+', text) if p.strip()]
    if not parts:
        return '', ''
    start = _format_data_year_part(parts[0], is_end=False)
    end = _format_data_year_part(parts[1] if len(parts) > 1 else parts[0], is_end=True)
    return start, end


def parse_data_period(reference_year, audit_year) -> Tuple[str, str]:
    """合并 reference_year + audit_year：起点取最早，终点取最晚。

    示例：reference_year=2023~2024, audit_year=2025
      → ('2023-01-01', '2025-12-31')
    """
    starts, ends = [], []
    for raw in (reference_year, audit_year):
        start, end = parse_data_year_range(raw)
        if start:
            starts.append(start)
        if end:
            ends.append(end)
    if not starts or not ends:
        return '', ''
    return min(starts), max(ends)


def _format_data_year_part(part: str, is_end: bool) -> str:
    matched = re.match(r'^(\d{4})(?:[-./年](\d{1,2}))?月?$', part.strip())
    if not matched:
        return ''
    year = int(matched.group(1))
    month = int(matched.group(2)) if matched.group(2) else None
    if month:
        if is_end:
            last = calendar.monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-{last:02d}"
        return f"{year:04d}-{month:02d}-01"
    if is_end:
        return f"{year:04d}-12-31"
    return f"{year:04d}-01-01"


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
    # 审计时间：DB 创建项目时间 ~ 报告生成时间（2026-09-03 用户确认）
    # 审计期/基准期：项目表 audit_year / reference_year，格式 YYYY年M月-YYYY年M月
    def _fmt_ym(dt):
        try:
            return f"{dt.year}年{dt.month}月"
        except AttributeError:
            return str(dt) if dt else ''
    ct = proj.get('create_time')
    if ct:
        result['found']['project']['audit_start'] = _fmt_ym(ct)
    result['found']['project']['audit_end'] = _fmt_ym(datetime.now())
    if proj.get('audit_year'):
        result['found']['project']['audit_year'] = proj['audit_year']
        a_start, a_end = parse_audit_year_range(proj['audit_year'])
        # create_time 为空时审计开始时间回退审计期起点
        if not ct and a_start:
            result['found']['project']['audit_start'] = a_start
        if a_start and a_end:
            result['found']['project']['audit_period'] = f"{a_start}-{a_end}"
    if proj.get('reference_year'):
        result['found']['project']['data_year'] = proj['reference_year']
        r_start, r_end = parse_audit_year_range(proj['reference_year'])
        if r_start and r_end:
            result['found']['project']['base_period'] = f"{r_start}-{r_end}"
    data_start, data_end = parse_data_period(
        proj.get('reference_year'), proj.get('audit_year')
    )
    if data_start:
        result['found']['project']['data_start'] = data_start
    if data_end:
        result['found']['project']['data_end'] = data_end
    result['found']['project'].update({
        'commission_person': proj.get('commission_person', ''),
        'commission_tel': proj.get('commission_tel', ''),
        'status': proj.get('status', ''),
        'remark': proj.get('remark', ''),
        'energy_codes': proj.get('energy_codes', ''),
        'audit_template': proj.get('audit_template', ''),
    })

    # ---- 1.3 审计机构信息（能源审计机构信息表数据源，2026-09-03 用户确认新链路）----
    # ① 优先：按项目 id 查 ts_project_dept（机构名称/地址/负责人/联系方式），有值逐字段采用；
    # ② 名称/地址兜底：按 project 的 audit_dept_name 查 ts_register_dept（含"测试"过滤，
    #    取同品牌"德诚"不含"测试"的最新记录）；
    # ③ 负责人/联系方式：仅 ts_project_dept 一个来源，无值则空，不查其他表。
    audit_org = {}
    # ① 项目级审计机构信息表
    try:
        pd_rows = pg.get_project_dept(project_id=result['project_id']) or []
        if pd_rows:
            pd = pd_rows[0]
            if pd.get('dept_name'):
                audit_org['audit_org_name'] = pd['dept_name']
            if pd.get('address'):
                audit_org['audit_org_address'] = pd['address']
            audit_org['audit_org_contact'] = pd.get('contact') or ''
            audit_org['audit_org_phone'] = pd.get('mobile') or ''
    except Exception:
        pass
    # ② 名称/地址兜底：ts_register_dept
    if not audit_org.get('audit_org_name') or not audit_org.get('audit_org_address'):
        try:
            regs = pg.get_register_info(dept_name=proj.get('audit_dept_name', '')) or []
            if regs:
                reg = regs[0]
                if not audit_org.get('audit_org_name') and '测试' not in str(reg.get('dept_name', '')):
                    audit_org['audit_org_name'] = reg.get('dept_name', '')
                if not audit_org.get('audit_org_address') and reg.get('address'):
                    audit_org['audit_org_address'] = reg.get('address')
            if not audit_org.get('audit_org_name'):
                # 名称含"测试"或未查到：取 register_dept 中同品牌（德诚）不含"测试"的最新记录
                try:
                    regs_all = pg.get_register_info(dept_name='德诚') or []
                    for r in regs_all:
                        if r.get('dept_name') and '测试' not in str(r.get('dept_name')):
                            audit_org['audit_org_name'] = r.get('dept_name')
                            if not audit_org.get('audit_org_address') and r.get('address'):
                                audit_org['audit_org_address'] = r.get('address')
                            break
                except Exception:
                    pass
        except Exception:
            pass
    # 兜底：仍无机构名时取项目表 audit_dept_name
    if not audit_org.get('audit_org_name'):
        audit_org['audit_org_name'] = proj.get('audit_dept_name', '')
    # ③ 负责人/联系方式：仅 ts_project_dept，无值保持空（不查别的表）
    audit_org.setdefault('audit_org_contact', '')
    audit_org.setdefault('audit_org_phone', '')
    result['found']['project'].update(audit_org)

    # ---- 1.5 客户信息 ----
    if customer_id:
        cust = pg.get_customer_info(customer_id=customer_id)
        if cust:
            customer = dict(cust[0])
            district_id = customer.get('district_id')
            division = {}
            getter = getattr(pg, 'get_admin_division_by_district_id', None)
            if callable(getter):
                try:
                    raw = getter(district_id)
                except Exception:
                    raw = None
                if isinstance(raw, dict):
                    division = raw
            province_full = str(division.get('province_full') or '').strip()
            if not province_full:
                try:
                    province_full = str(pg.get_province_name_by_district_id(district_id) or '').strip()
                except Exception:
                    province_full = ''
            if province_full:
                customer['admin_affiliation'] = province_full
                customer['province'] = (
                    str(division.get('province') or '').strip()
                    or PgDataQuery.short_province_name(province_full)
                )
            if str(division.get('city') or '').strip():
                customer['city'] = str(division.get('city')).strip()
            if str(division.get('district') or '').strip():
                customer['district'] = str(division.get('district')).strip()
            result['found']['customer_info'] = customer
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
        # build_img 不属于 BuildingInfo 数据模型，单独存放供图片采集段使用
        if b.get('build_img'):
            result.setdefault('found', {}).setdefault('building_images', []).append(
                {'build_name': b.get('build_name') or '', 'build_img': b.get('build_img')})

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
            # 折标煤系数（实物量记录 dt=1/4/5 统一记录；heat 单位归一 kgce/GJ → tce/GJ）
            if dt in (1, 4, 5):
                coeff = rec.get('standard_coal_coefficient')
                if is_valid_coefficient(coeff):
                    cval = float(coeff)
                    if coeff_type == 'heat' and cval > 1:
                        cval = cval / 1000  # DB 存 kgce/GJ（如 34.12），指标计算用 tce/GJ（0.03412）
                    yearly_map[year].setdefault('coefficients', {})[coeff_type] = cval
                    yearly_map[year].setdefault('coefficient_sources', {})[coeff_type] = 'PG'
            if dt == 1:
                yearly_map[year][field] = total
                if building_value:
                    yearly_map[year][f'building_{field}'] = building_value
                if monthly_field and any(v > 0 for v in monthly):
                    yearly_map[year][monthly_field] = monthly
            elif dt == 2:
                cost_map = {
                    '电能': 'electricity_cost_wan', '45': 'electricity_cost_wan', '电': 'electricity_cost_wan',
                    '水': 'water_cost_wan', '01': 'water_cost_wan',
                    '热能': 'heating_cost_wan', '50': 'heating_cost_wan', '热力': 'heating_cost_wan',
                    '天然气': 'natural_gas_cost_wan', '25': 'natural_gas_cost_wan',
                    '柴油': 'diesel_cost_wan', '300302': 'diesel_cost_wan',
                    '汽油': 'petrol_cost_wan', '300301': 'petrol_cost_wan',
                }
                cost_field = cost_map.get(code_name) or cost_map.get(code_id)
                if cost_field:
                    # 费用取 real_value（单位实际费用值，unit_total_value）；版本归一带最新正式版本
                    yearly_map[year][cost_field] = round(
                        float(rec.get('unit_total_value') or 0) / 10000, 4)
            elif dt == 7 and field == 'heating_energy_heat_gj':
                # 供热费用（dt=7 单独记录）：取 real_value
                yearly_map[year]['heating_cost_wan'] = round(
                    float(rec.get('unit_total_value') or 0) / 10000, 4)
            elif dt == 8 and field == 'petrol_kg':
                # 交通费用（dt=8 单独记录）：取 real_value
                yearly_map[year]['petrol_cost_wan'] = round(
                    float(rec.get('unit_total_value') or 0) / 10000, 4)
            elif dt == 4 and field in ('heating_energy_heat_gj',):
                # 供热能耗（GJ）：real_value 与 total_value 一致
                yearly_map[year][field] = total
            elif dt == 4 and field == 'electricity_kwh':
                # 供热能耗的电部分：供暖电耗 kWh（供暖循环泵/风机），
                # 计算非供暖能耗/常规电耗时须从总电量中剔除
                yearly_map[year]['heating_energy_kwh'] = total
            elif dt == 5 and field == 'petrol_kg':
                # 交通能耗：DB 存吨（t），统一换算为 kg
                yearly_map[year][field] = round(total * 1000, 2)
            elif dt == 5 and field == 'diesel_kg':
                yearly_map[year][field] = round(total * 1000, 2)

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
    # 字段映射（对齐 author 写作取值键 role/name/education/certification/major）：
    # ts_project_audit_user: position(组内职务)→role, degree→education, qualifications→certification
    audit_users = [{'role': r.get('position'), 'name': r.get('name'),
                    'education': r.get('degree'), 'certification': r.get('qualifications'),
                    'major': r.get('major')}
                   for r in pg.get_project_audit_users(project_id=result['project_id'])]
    if audit_users:
        result['found']['team_members'] = audit_users

    # ts_project_audited_user: group_position(组内职务)→role, department→dept,
    #                          sex→gender, position(职务)→position
    audited_users = [{'role': r.get('group_position'), 'dept': r.get('department'),
                      'name': r.get('name'), 'gender': r.get('sex'),
                      'position': r.get('position')}
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
            'has_household_metering': scene.get('split_measure') == 1 if scene.get('split_measure') is not None else False,
            'has_household_payment': scene.get('split_payment') == 1 if scene.get('split_payment') is not None else False,
            'has_shared_office': scene.get('mode') == 1 if scene.get('mode') is not None else False,
            'independent_light_socket': scene.get('light_socket_meter') == 1,
            'independent_power': scene.get('power_meter') == 1,
            'independent_aircon': scene.get('aircon_meter') == 1,
            'independent_special': scene.get('special_meter') == 1,
            'independent_other_special': (scene.get('other_special_meter') or '').strip()
            if scene.get('other_special_meter') else '',
            'independent_construction_elec': scene.get('construction_elec_meter') == 1,
            'independent_construction_water': scene.get('construction_water_meter') == 1,
            'install_position': _int(scene.get('install_position')),
            'position_reasonable': _int(scene.get('position_reasonable')),
            'metering_standard': _int(scene.get('metering_standard')),
            'partition_payment': scene.get('partition_payment') == 1 if scene.get('partition_payment') is not None else False,
            'electric_pay_type': scene.get('electric_pay_type') or '',
            'service_staff': '' if str(scene.get('service_staff') or '') in ('', '0', 'None', '无') else str(scene.get('service_staff')),
            'scene_desc': '' if str(scene.get('scene_desc') or '') in ('', '未知', 'None') else str(scene.get('scene_desc')),
            'record_attach_id': _int(scene.get('record_attach_id')),
            'aircon_staff_num': _int(scene.get('aircon_staff_num')),
            'light_staff_num': _int(scene.get('light_staff_num')),
            'power_room_staff_num': _int(scene.get('power_room_staff_num')),
        }
        result['found']['metering'] = metering
        if scene.get('work_staff'):
            result['found']['people_count'] = scene.get('work_staff')
        mode_rows = pg.get_institution_scene_mode(
            customer_id=customer_id, scene_id=scene.get('id'),
        ) or []
        shared_offices = [PgDataQuery._fmt_scene_mode(r) for r in mode_rows]
        if shared_offices:
            result['found']['shared_offices'] = shared_offices
        elif metering['has_shared_office']:
            result['missing'].append('合署办公明细（ts_institution_scene_mode 无记录）')
        heat_missing = []
        if not scene.get('heat_area'):
            heat_missing.append('供热面积')
        if not scene.get('heat_day'):
            heat_missing.append('供热天数')
        if not scene.get('heat_price'):
            heat_missing.append('热价')
        if heat_missing:
            result['missing'].append(f"供暖信息（{'/'.join(heat_missing)}未记录）")

    # ---- 6.5 表具计量信息 ----
    meters = pg.get_energy_meter(customer_id=customer_id)
    if meters:
        result['found']['energy_meter'] = meters
        # 台账附件文件 id（电/水表记录拼接）→ 供 enrich_meter_ledger 下载提炼
        _ledger_ids = []
        for _m in meters:
            _lids = [x.strip() for x in str(_m.get('ledger_files') or '').split(',') if x.strip()]
            _ledger_ids.extend(_lids)
        result['found'].setdefault('metering', {})['ledger_files'] = ','.join(dict.fromkeys(_ledger_ids))

    # ---- 6.5b 缴费发票（主表 + 图片明细双表）----
    invoices = pg.get_institution_energy_invoice(customer_id=customer_id)
    if invoices:
        _inv_ids = [r['id'] for r in invoices]
        _img_rows = pg.get_institution_energy_invoice_images(_inv_ids)
        _img_by_record: dict = {}
        for _ir in _img_rows:
            _img_by_record.setdefault(_ir['record_id'], []).append(_ir)
        for _inv in invoices:
            _inv['images'] = _img_by_record.get(_inv['id'], [])
        result['found']['energy_invoices'] = invoices

    # ---- 6.6 折标系数 ----
    standards = pg.get_energy_standards()
    if standards:
        result['found']['energy_standards'] = standards
    else:
        result['missing'].append('能源折标系数（ts_energy_standard）')

    # ---- 6.7 节能管理信息 ----
    energy_saving = pg.get_institution_energy_saving(customer_id=customer_id)
    if energy_saving:
        result['found']['energy_saving'] = [
            {
                'statistical_year': _int(r.get('statistical_year')),
                'energy_management': r.get('energy_management'),
                'energy_pain_points': r.get('energy_pain_points') or '',
                'management_files': r.get('management_files') or '',
                'has_awards': _int(r.get('has_awards')),
                'award_name': r.get('award_name') or '',
                'award_certificate': r.get('award_certificate') or '',
                'other_measures': r.get('other_measures') or '',
                'third_party_system': r.get('third_party_system') or '',
                'charging_pile': _int(r.get('charging_pile')),
                'charging_settlement': r.get('charging_settlement') or '',
                'charging_installation': r.get('charging_installation') or '',
                'third_party_outsource': _int(r.get('third_party_outsource')),
                'outsource_content': r.get('outsource_content') or '',
                'outsource_settlement': r.get('outsource_settlement') or '',
                'lighting_replacement': _int(r.get('lighting_replacement')),
                'ac_replacement': _int(r.get('ac_replacement')),
                'water_saving_fixture_replacement': _int(r.get('water_saving_fixture_replacement')),
                'central_ac_control': _int(r.get('central_ac_control')),
            }
            for r in energy_saving
        ]

    # ---- 7. 整理缺失清单 ----
    req = [
        ('buildings', '建筑信息（ts_institution_build）'),
        ('energy_yearly', '能耗数据（ts_institution_energy_main）'),
        ('equipment', '设备数据（ts_institution_device_*）'),
        ('metering', '计量信息'),
        ('energy_meter', '表具计量信息（ts_institution_energy_meter）'),
        ('energy_saving', '节能管理信息（ts_institution_energy_saving）'),
    ]
    for key, label in req:
        if key not in result['found']:
            result['missing'].append(label)

    return result


def build_and_save_project(project_name: str, excel_data: dict = None, pg_result: dict = None) -> AuditProject:
    """
    datacollection Agent v2：先查PG，缺失的用Excel补充。

    注意：本函数带持久化副作用 —— 内部会 save_project(proj) 落盘，
    并触发附件图片下载 / LLM 提炼（网络副作用），不纯是内存构建。

    Args:
        pg_result: 可选的已采集结果（collect_from_pg 返回值）。
            传入时跳过内部二次查询，供调用方复用采集结果。
    """
    print(f"[datacollection v2] 正在从PG查询项目: {project_name}")
    if pg_result is None:
        pg_result = collect_from_pg(project_name)

    found_count = len(pg_result['found'])
    missing_count = len(pg_result['missing'])
    print(f"[datacollection v2] PG查询完成: 找到{found_count}类数据, 缺失{missing_count}项")

    if pg_result['missing']:
        print("\n⚠️ 以下数据未在PG中找到，需手动补充：")
        for m in pg_result['missing']:
            print(f"  · {m}")
        print()

    excel_data = excel_data or {}
    sr = SourceResolver()

    pg_project = pg_result['found'].get('project', {})
    pg_customer = pg_result['found'].get('customer_info', {}) or {}
    pg_buildings = pg_result['found'].get('buildings', [])
    pg_energy = pg_result['found'].get('energy_yearly', [])
    pg_equipment = pg_result['found'].get('equipment', [])
    pg_metering = pg_result['found'].get('metering', {})
    pg_energy_saving = pg_result['found'].get('energy_saving', [])
    pg_shared_offices = pg_result['found'].get('shared_offices', [])
    pg_building_area = total_building_area(pg_buildings)

    # unit_type：来自 ts_customer_info.field_type（10/20/30）
    # institution_category / specific_type：PG 无中文字段，按单位名分类器识别
    unit_for_class = pg_project.get('unit_name') or project_name
    classified_cat, classified_spec = classify_institution(unit_for_class)
    ft = str(pg_customer.get('field_type') or '').strip()
    pg_unit_type = _FIELD_TYPE_UNIT.get(ft, '')
    pg_institution_category = classified_cat if classified_cat != '未分类' else ''
    pg_specific_type = classified_spec if classified_spec != '其他' else ''

    # ---- 图片采集：建筑外观（build_img）/ 计量器具照片（device_img）----
    # file id → ts_attachment.attach_url → base_url 拼接 → 下载到 reports/attachments/
    # base_url 未配置时返回空列表，不阻塞采集（照片缺失由 photo_manager 检查提示）。
    photo_items: List[ImageItem] = []
    _photo_id_map = []  # [(file_id, category)]
    for bi in pg_result['found'].get('building_images', []) or []:
        for fid in parse_file_ids(bi.get('build_img') or ''):
            _photo_id_map.append((fid, '建筑外观'))
    for mr in pg_result['found'].get('energy_meter', []) or []:
        for fid in parse_file_ids(mr.get('device_img') or ''):
            _photo_id_map.append((fid, '计量器具'))
    # 发票照片（ts_institution_energy_invoice + invoice_image 双表）→ 分类'缴费发票'，
    # caption 带能源类型与期间（如"电费 1月~2月"），附录按 caption 前缀分组排列。
    _INVOICE_TYPE_CN = {
        '01': '水费', '10': '煤炭费', '25': '燃气费', '45': '电费',
        '50': '供暖费', '300301': '油费', '300302': '油费',
    }
    _invoice_records = pg_result['found'].get('energy_invoices', []) or []
    for inv in _invoice_records:
        _type_cn = _INVOICE_TYPE_CN.get(str(inv.get('energy_type') or '').strip(), '能源费')
        for _img in inv.get('images', []) or []:
            _fid = _img.get('file_id')
            if not _fid:
                continue
            for fid in parse_file_ids(_fid):
                _period = _img.get('period_name') or _img.get('period_code') or ''
                _photo_id_map.append((fid, ('缴费发票', f"{_type_cn} {_period}".strip())))
    # 设备分表照片（_img 列）→ 第6章分系统分类（2026-09-04 补，此前正文无设备照片）
    _DEVICE_PHOTO_CATEGORY = {
        '空调': '制冷设备', '照明': '照明设备', '办公': '办公设备',
        '动力': '其他用电设备', '生活热水': '其他用电设备',
        '其他设备': '制冷设备', '输配设备': '制冷设备', '蒸汽': '制冷设备',
        '特殊设备': '信息机房',
        # 卫生器具（用水系统）暂不映射：DB 无照片记录，后续有需要再加'用水设备'分类
    }
    for eq in pg_result['found'].get('equipment', []) or []:
        _cat = _DEVICE_PHOTO_CATEGORY.get(eq.get('category') or '')
        if not _cat:
            continue
        for fid in (eq.get('img_ids') or []):
            _photo_id_map.append((fid, _cat))
    if _photo_id_map:
        _atts = resolve_attachment_urls([fid for fid, _ in _photo_id_map])
        _path_by_id = {}
        for att in _atts:
            for pth in download_attachment_images([att]):
                _path_by_id[att['group_id']] = pth
        for fid, cat in _photo_id_map:
            pth = _path_by_id.get(fid)
            if pth:
                if isinstance(cat, tuple):  # (category, caption) — 缴费发票等带图注分类
                    photo_items.append(ImageItem(path=pth, category=cat[0], caption=cat[1]))
                else:
                    photo_items.append(ImageItem(path=pth, category=cat))
    if photo_items:
        _cats = sorted({im.category for im in photo_items})
        print(f"[datacollection v2] 已采集照片 {len(photo_items)} 张（{'/'.join(_cats)}）")
    elif _photo_id_map:
        print("[datacollection v2] 照片未采集：file base_url 未配置或附件下载失败，缺失项由 photo_manager 检查提示")

    proj = AuditProject(
        base=ProjectBase(
            name=f"{project_name}能源审计",
            unit_name=sr.resolve('unit_name',
                                 ('PG', pg_project),
                                 ('Excel', excel_data),
                                 ('default', project_name)),
            unit_short=sr.resolve('unit_short',
                                  ('Excel', excel_data),
                                  ('default', project_name)),
            address=sr.resolve('address',
                               ('PG', pg_customer),
                               ('Excel', excel_data),
                               ('default', '')),
            unit_type=sr.resolve('unit_type',
                                 ('PG', pg_unit_type),
                                 ('Excel', excel_data),
                                 ('default', '公共机构')),
            institution_category=sr.resolve('institution_category',
                                            ('PG', pg_institution_category),
                                            ('Excel', excel_data),
                                            ('default', '')),
            specific_type=sr.resolve('specific_type',
                                     ('PG', pg_specific_type),
                                     ('Excel', excel_data),
                                     ('default', '')),
            basic_situation=sr.resolve('basic_situation',
                                       ('PG', pg_customer),
                                       ('Excel', excel_data),
                                       ('default', '')),
            contact_person=sr.resolve('contact_person',
                                      ('PG', pg_project),
                                      ('Excel', excel_data),
                                      ('default', '')),
            contact_phone=sr.resolve('contact_phone',
                                     ('PG', pg_project),
                                     ('Excel', excel_data),
                                     ('default', '')),
            auditor=_resolve_auditor(sr, pg_project, excel_data),
            # 审计机构信息（能源审计机构信息表）：name/address 来自 ts_register_info（PG），
            # 负责人/联系方式由用户提问提供（Excel 中可预填），表内 contact/mobile 作预填参考。
            audit_org_name=sr.resolve('audit_org_name',
                                      ('PG', pg_project),
                                      ('Excel', excel_data),
                                      ('default', '')),
            audit_org_address=sr.resolve('audit_org_address',
                                         ('PG', pg_project),
                                         ('Excel', excel_data),
                                         ('default', '')),
            audit_org_contact=sr.resolve('audit_org_contact',
                                         ('PG', pg_project),
                                         ('Excel', excel_data),
                                         ('default', '')),
            audit_org_phone=sr.resolve('audit_org_phone',
                                       ('PG', pg_project),
                                       ('Excel', excel_data),
                                       ('default', '')),
            audit_org_contact_hint=sr.resolve('audit_org_contact_hint',
                                              ('PG', pg_project),
                                              ('default', '')),
            audit_org_phone_hint=sr.resolve('audit_org_phone_hint',
                                            ('PG', pg_project),
                                            ('default', '')),
            building_area=sr.resolve('building_area',
                                     ('PG', pg_building_area),
                                     ('Excel', excel_data),
                                     ('default', 0)),
            people_count=sr.resolve('people_count',
                                    ('PG', pg_result['found'].get('people_count')),
                                    ('Excel', excel_data),
                                    ('default', 300)),
            beds_count=sr.resolve('beds_count',
                                  ('Excel', excel_data),
                                  ('default', 0)),
            admin_affiliation=sr.resolve('admin_affiliation',
                                         ('PG', pg_customer),
                                         ('Excel', excel_data),
                                         ('default', '')),
            province=sr.resolve('province',
                                ('PG', pg_customer),
                                ('Excel', excel_data),
                                ('default', '山东')),
            city=sr.resolve('city',
                            ('PG', pg_customer),
                            ('Excel', excel_data),
                            ('default', '')),
            district=sr.resolve('district',
                                ('PG', pg_customer),
                                ('Excel', excel_data),
                                ('default', '')),
            audit_start=sr.resolve('audit_start',
                                   ('PG', pg_project),
                                   ('Excel', excel_data),
                                   ('default', '')),
            audit_end=sr.resolve('audit_end',
                                 ('PG', pg_project),
                                 ('Excel', excel_data),
                                 ('default', '')),
            audit_period=sr.resolve('audit_period',
                                    ('PG', pg_project),
                                    ('Excel', excel_data),
                                    ('default', '')),
            base_period=sr.resolve('base_period',
                                   ('PG', pg_project),
                                   ('Excel', excel_data),
                                   ('default', '')),
            data_start=sr.resolve('data_start',
                                  ('PG', pg_project),
                                  ('Excel', excel_data),
                                  ('default', '')),
            data_end=sr.resolve('data_end',
                                ('PG', pg_project),
                                ('Excel', excel_data),
                                ('default', '')),
            report_date=sr.resolve('report_date',
                                   ('Excel', excel_data),
                                   ('default', '')),
        ),
        buildings=_merge_buildings(pg_buildings, excel_data.get('buildings', [])),
        energy_yearly=_merge_energy(pg_energy, excel_data.get('energy_yearly', [])),
        energy_monthly=_expand_energy_monthly(
            _merge_energy(pg_energy, excel_data.get('energy_yearly', []))),
        equipment=_merge_equipment(pg_equipment, excel_data.get('equipment', [])),
        shared_offices=_merge_shared_offices(pg_shared_offices, excel_data.get('shared_offices', [])),
        management=ManagementInfo(),
        energy_saving=_merge_energy_saving(pg_energy_saving, excel_data.get('energy_saving', [])),
        energy_meter=pg_result['found'].get('energy_meter', []) or [],
        # meter 表数据按 data_type 回填表数（4.2 表数来源；Excel 同名键可覆盖）
        metering=_merge_metering(_fill_meter_counts(pg_metering, pg_result['found'].get('energy_meter', [])),
                                 excel_data.get('metering', {})),
        audit_team=[_dataclass_from_dict(TeamMember, m)
                    for m in pg_result['found'].get('team_members', [])],
        cooperation=[_dataclass_from_dict(CoopMember, c)
                     for c in pg_result['found'].get('audited_users', [])],
        images=photo_items,
    )

    # 解析节能管理信息中的附件文件 ID（management_files / award_certificate）
    # → 下载图片到 reports/attachments/，回填 EnergySaving 的 *_images 字段。
    # file.base_url 未配置时自动跳过，不阻塞采集。
    enrich_energy_saving_images(proj)
    # 有能源管理制度（energy_management==1）且制度文件存在时：
    # 下载制度文档 → 提取文字 → LLM 提炼，回填 proj.management（3.1 机构职责 / 3.2 目标方针）。
    # 缺 key / 文件 / 提取失败均静默降级，不阻塞采集。
    enrich_management_info(proj)
    # 计量器具台账附件：下载台账文档 → 提取文字 → 回填 proj.metering.ledger_text（4.2 表4.1 取数）
    enrich_meter_ledger(proj)

    # 记录集合/对象级数据来源
    proj.data_sources = sr.sources
    proj.data_sources['name'] = 'derived'
    proj.data_sources['buildings'] = first_non_empty_source(
        ('PG', pg_buildings),
        ('Excel', excel_data.get('buildings', [])),
    )
    proj.data_sources['energy_yearly'] = first_non_empty_source(
        ('PG', pg_energy),
        ('Excel', excel_data.get('energy_yearly', [])),
    )
    proj.data_sources['equipment'] = first_non_empty_source(
        ('PG', pg_equipment),
        ('Excel', excel_data.get('equipment', [])),
    )
    proj.data_sources['metering'] = first_non_empty_source(
        ('PG', pg_metering),
        ('Excel', excel_data.get('metering', {})),
    )
    proj.data_sources['shared_offices'] = first_non_empty_source(
        ('PG', pg_shared_offices),
        ('Excel', excel_data.get('shared_offices', [])),
    )
    proj.data_sources['energy_saving'] = first_non_empty_source(
        ('PG', pg_energy_saving),
        ('Excel', excel_data.get('energy_saving', [])),
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


# ============================================================
# 多源合并辅助（PG > Excel）
# ============================================================

def _merge_buildings(*sources: List[dict]) -> List[BuildingInfo]:
    """多源建筑信息合并（去重：同名保留第一个来源的）"""
    seen = set()
    result = []
    for src in sources:
        for b in src:
            name = b.get('name', '')
            if name and name not in seen:
                seen.add(name)
                result.append(BuildingInfo(**b))
    return result


def _merge_energy(pg: List[dict], excel: List[dict]) -> List[EnergyYearly]:
    """多源能耗数据合并（同一年保留第一个来源的整对象；coefficients 按能源类型跨来源合并）。

    优先级 PG > Excel：同一年份以 PG 的整对象为准，但折标煤系数按能源类型
    跨来源合并（PG 缺失某类系数时用 Excel 补）。
    """
    seen = {}
    coeff_merges = {}  # year -> {energy_type: (value, source_name)}
    for source_name, src in [('PG', pg), ('Excel', excel)]:
        for e in src:
            year = e.get('year', 0)
            if year and year not in seen:
                seen[year] = e
            # 按能源类型合并系数，优先级 PG > Excel
            for k, v in e.get('coefficients', {}).items():
                if is_valid_coefficient(v) and k not in coeff_merges.get(year, {}):
                    coeff_merges.setdefault(year, {})[k] = (
                        float(v),
                        e.get('coefficient_sources', {}).get(k, source_name),
                    )

    result = []
    for year, e in seen.items():
        merged = dict(e)
        coeffs = coeff_merges.get(year, {})
        if coeffs:
            merged['coefficients'] = {k: v for k, (v, _) in coeffs.items()}
            merged['coefficient_sources'] = {k: src for k, (_, src) in coeffs.items()}
        result.append(EnergyYearly(**merged))
    return result


def _dataclass_from_dict(cls, data: dict):
    """只取 dataclass 已声明字段，忽略 PG/Excel 多出来的列。"""
    allowed = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in allowed})


def _merge_equipment(*sources: List[dict]) -> List[Equipment]:
    """多源设备合并。同名同类同规格保留先出现的来源（PG 优先于 Excel）。"""
    seen = set()
    result = []
    for src in sources:
        for e in src:
            key = (
                e.get('category') or '',
                e.get('name') or '',
                e.get('spec') or '',
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(_dataclass_from_dict(Equipment, e))
    return result


def _fill_meter_counts(metering: dict, energy_meter: List[dict]) -> dict:
    """meter 表（ts_institution_energy_meter）数据回填计量信息：

    data_type 1=电表 2=水表；表数取版本归一后记录的 meter_count。
    """
    m = dict(metering or {})
    for rec in energy_meter or []:
        dt = rec.get('data_type')
        mc = _int(rec.get('meter_count'))
        if dt == 1 and mc:
            m.setdefault('electric_meters', mc)
        elif dt == 2 and mc:
            m.setdefault('water_meters', mc)
    return m


def _merge_metering(*sources: dict) -> MeteringInfo:
    """多源计量信息合并（优先采用第一个非空源，保留 False/0 等有效值）"""
    for src in sources:
        if src:
            return _dataclass_from_dict(MeteringInfo, src)
    return MeteringInfo()


def _merge_shared_offices(*sources: List[dict]) -> List[SharedOfficeUnit]:
    """多源合署办公明细合并。同单位同楼层保留先出现的来源（PG 优先于 Excel）。"""
    seen = set()
    result = []
    for src in sources:
        for row in src:
            key = (row.get('dept_name') or '', row.get('building') or '')
            if key in seen:
                continue
            seen.add(key)
            result.append(_dataclass_from_dict(SharedOfficeUnit, row))
    return result


def _merge_energy_saving(*sources: List[dict]) -> List[EnergySaving]:
    """多源节能管理信息合并。

    去重：统计年有效时按年去重；统计年为空的记录不再丢弃（DB 该列允许 NULL，
    法院等项目的节能管理记录即无年份），按整条内容指纹去重。
    版本归一已在上游 get_institution_energy_saving 完成，此处仅合并多源。
    """
    seen = set()
    result = []
    for src in sources:
        for es in src:
            year = es.get('statistical_year')
            if year:
                key = ('year', year)
            else:
                try:
                    key = ('noyear', frozenset((k, str(v)) for k, v in es.items()))
                except Exception:
                    key = ('noyear', len(result))  # 兜底：不可哈希时不去重
            if key not in seen:
                seen.add(key)
                result.append(EnergySaving(**es))
    return result


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
