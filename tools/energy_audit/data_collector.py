#!/usr/bin/env python3
"""DataCollection 核心调度器 — 多源统一采集引擎

作者: 马天远 | 版本: 2.0.0 | 日期: 2026-07-31
prod - serial number - 2
"""

import json, sys, os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import asdict
from datetime import datetime

from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401

try:
    from tools.energy_audit.pg_collector import collect_from_pg
    from tools.energy_audit.project_data import (
        AuditProject, ProjectBase, BuildingInfo, EnergyYearly, EnergyMonthly,
        Equipment, MeteringInfo, ManagementInfo, IndoorEnv, save_project,
        _PROJECTS_ROOT, SourceResolver, first_non_empty_source,
        is_valid_coefficient,
    )
    from tools.energy_audit.data_check import check_completeness
except ImportError as e:
    print(f"[错误] 导入失败: {e}")
    print(f"[信息] 项目根目录: {PROJECT_ROOT}")
    print(f"[信息] sys.path[0]: {sys.path[0] if sys.path else '空'}")
    sys.exit(1)


# ============================================================
# 异常检测
# ============================================================

def detect_anomalies(energy_yearly: List[dict]) -> List[dict]:
    """检测能耗数据中的异常"""
    anomalies = []
    if len(energy_yearly) < 2:
        return anomalies

    last_year = None
    for ey in sorted(energy_yearly, key=lambda x: x.get('year', 0)):
        year = ey.get('year', 0)
        if last_year and last_year.get('year'):
            # 用电环比
            cur_elec = ey.get('electricity_kwh', 0) or 0
            prev_elec = last_year.get('electricity_kwh', 0) or 0
            if prev_elec > 0:
                ratio = (cur_elec - prev_elec) / prev_elec * 100
                if abs(ratio) > 30:
                    anomalies.append({
                        'type': '环比异常', 'year': year,
                        '能源': '用电', '变化率': f'{ratio:+.1f}%',
                        '当前值': cur_elec, '上年值': prev_elec,
                        '等级': '严重' if abs(ratio) > 50 else '警告',
                    })
            # 用水环比
            cur_water = ey.get('water_m3', 0) or 0
            prev_water = last_year.get('water_m3', 0) or 0
            if prev_water > 0:
                ratio = (cur_water - prev_water) / prev_water * 100
                if abs(ratio) > 30:
                    anomalies.append({
                        'type': '环比异常', 'year': year,
                        '能源': '用水', '变化率': f'{ratio:+.1f}%',
                        '当前值': cur_water, '上年值': prev_water,
                        '等级': '严重' if abs(ratio) > 50 else '警告',
                    })
            # 月度全零检查
            for month_field, ename in [('monthly_electricity_kwh', '用电'),
                                        ('monthly_water_m3', '用水'),
                                        ('monthly_natural_gas_m3', '天然气')]:
                monthly = ey.get(month_field, [])
                if monthly and all(v == 0 for v in monthly):
                    anomalies.append({
                        'type': '月度全零', 'year': year,
                        '能源': ename, '等级': '警告',
                        '说明': f'{year}年{ename}逐月数据全为0，可能漏录',
                    })
        last_year = ey
    return anomalies


def detect_area_mismatch(buildings: List[dict], declared_area: float) -> Optional[str]:
    """检测建筑面积合计 vs 声明总面积是否一致"""
    if not buildings:
        return None
    sum_area = sum(b.get('area', 0) or 0 for b in buildings)
    if declared_area > 0 and abs(sum_area - declared_area) / declared_area > 0.05:
        return (f"建筑面积不匹配：各建筑合计 {sum_area:.0f}m²，"
                f"声明的总面积 {declared_area:.0f}m²，偏差 {abs(sum_area - declared_area):.0f}m²")
    return None


# ============================================================
# 采集报告格式化
# ============================================================

def format_collection_report(pg_result: dict, anomalies: List[dict],
                               area_issue: Optional[str], config_used: bool) -> str:
    """生成格式化的采集报告"""
    lines = []
    lines.append("=" * 50)
    lines.append("📊 DataCollection 采集报告")
    lines.append("=" * 50)
    lines.append("")

    # PG连接状态
    project = pg_result.get('found', {}).get('project', {})
    proj_id = pg_result.get('project_id')
    lines.append(f"📌 项目: {project.get('unit_name', '未指定')}")
    lines.append(f"📡 PG 连接: {'[✔] 成功' if proj_id else '[✘] 失败/无匹配'}")

    # 已采集
    found = pg_result.get('found', {})
    found_count = len(found)
    lines.append(f"\n✅ 已采集到 ({found_count} 类):")
    if project:
        lines.append(f"  · 基本信息: {project.get('unit_name', '')}")
        if 'contact_person' in project:
            lines.append(f"    ├ 联系人: {project.get('contact_person', '')}")
        if 'auditor' in project:
            lines.append(f"    └ 审计机构: {project.get('auditor', '')}")
    buildings = found.get('buildings', [])
    if buildings:
        total_area = sum(b.get('area', 0) or 0 for b in buildings)
        lines.append(f"  · 建筑: {len(buildings)} 栋 (合计 {total_area:.0f} m²)")
        for b in buildings[:5]:
            area_str = f"{b.get('area',0):.0f}m²" if b.get('area', 0) else "面积未知"
            lines.append(f"    ├ {b.get('name', '未命名')} ({area_str})")
        if len(buildings) > 5:
            lines.append(f"    └ ... 还有 {len(buildings)-5} 栋")
    else:
        lines.append("  · 建筑: [无]")

    energy_yearly = found.get('energy_yearly', [])
    if energy_yearly:
        years = [e.get('year', '?') for e in energy_yearly]
        lines.append(f"  · 能耗: {len(years)} 年 ({', '.join(str(y) for y in years)})")
    else:
        lines.append("  · 能耗: [无]")

    equipment = found.get('equipment', [])
    if equipment:
        cats = {}
        for e in equipment:
            cat = e.get('category', '其他')
            cats[cat] = cats.get(cat, 0) + 1
        cat_str = ', '.join(f'{k} {v}条' for k, v in cats.items())
        lines.append(f"  · 设备: {len(equipment)} 台/类 ({cat_str})")
    else:
        lines.append("  · 设备: [无]")

    metering = found.get('metering', {})
    if metering:
        lines.append(f"  · 计量: {'有监测系统' if metering.get('has_monitoring_system') else '无监测系统'}"
                      f", {'有分项计量' if metering.get('has_separate_metering') else '不分项'}")

    # 缺失项
    missing = pg_result.get('missing', [])
    if missing:
        lines.append(f"\n⚠️ 缺失项 ({len(missing)} 项):")
        for m in missing:
            lines.append(f"  · {m}")
    else:
        lines.append("\n✅ 无缺失项（PG数据完整）")

    # 异常
    if anomalies:
        lines.append(f"\n🔍 数据异常 ({len(anomalies)} 项):")
        for a in anomalies:
            lines.append(f"  · [{a.get('等级','信息')}] {a.get('type','')}: "
                          f"{a.get('year','')}年{a.get('能源','')} {a.get('变化率','')}")
    else:
        lines.append("\n✅ 无数据异常")

    if area_issue:
        lines.append(f"\n⚠️ {area_issue}")

    # 配置补充
    if config_used:
        lines.append("\n📋 Config JSON 已作为补充数据源")

    # 保存路径
    lines.append(f"\n📁 数据持久化位置: {_PROJECTS_ROOT}")
    lines.append("=" * 50)
    return '\n'.join(lines)


# ============================================================
# 多源合并构建
# ============================================================

def build_audit_project(project_name: str, config: dict = None,
                         excel_data: dict = None) -> AuditProject:
    """多源数据合并构建 AuditProject

    优先级: PG > Excel > Config > 默认
    """
    # Step 1: PG采集
    print(f"[DataCollection] Step 1/4: PG 数据库采集 ...")
    pg_result = collect_from_pg(project_name)
    pg_found = pg_result.get('found', {})
    missing = pg_result.get('missing', [])
    print(f"  → 找到 {len(pg_found)} 类, 缺失 {len(missing)} 项")

    config = config or {}
    excel_data = excel_data or {}

    # Step 2: 按优先级解析字段并记录来源
    sr = SourceResolver()
    pg_project = pg_found.get('project', {})
    pg_building_area = sum(b.get('area', 0) for b in pg_found.get('buildings', []))

    proj = AuditProject(
        base=ProjectBase(
            name=f"{project_name}能源审计",
            unit_name=sr.resolve('unit_name',
                                 ('PG', pg_project),
                                 ('Excel', excel_data),
                                 ('Config', config),
                                 ('default', project_name)),
            unit_short=sr.resolve('unit_short',
                                  ('Excel', excel_data),
                                  ('Config', config),
                                  ('default', '')),
            address=sr.resolve('address',
                               ('Excel', excel_data),
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
            province=sr.resolve('province',
                                ('Config', config),
                                ('default', '山东')),
            building_area=sr.resolve('building_area',
                                     ('PG', pg_building_area),
                                     ('Excel', excel_data),
                                     ('Config', config),
                                     ('default', 0)),
            people_count=sr.resolve('people_count',
                                    ('Excel', excel_data),
                                    ('Config', config),
                                    ('default', 0)),
            beds_count=sr.resolve('beds_count',
                                  ('Excel', excel_data),
                                  ('Config', config),
                                  ('default', 0)),
            admin_affiliation=sr.resolve('admin_affiliation',
                                         ('Config', config),
                                         ('default', '')),
            department_count=sr.resolve('department_count',
                                        ('Config', config),
                                        ('default', '')),
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
        buildings=_merge_buildings(
            pg_found.get('buildings', []),
            excel_data.get('buildings', []),
            config.get('buildings', [])
        ),
        energy_yearly=_merge_energy(
            pg_found.get('energy_yearly', []),
            excel_data.get('energy_yearly', []),
            config.get('energy_yearly', [])
        ),
        equipment=_merge_equipment(
            pg_found.get('equipment', []),
            excel_data.get('equipment', []),
            config.get('equipment', [])
        ),
        metering=_merge_metering(
            pg_found.get('metering', {}),
            excel_data.get('metering', {}),
            config.get('metering', {})
        ),
    )

    # 记录集合/对象级数据来源
    proj.data_sources = sr.sources
    proj.data_sources['name'] = 'derived'
    proj.data_sources['buildings'] = first_non_empty_source(
        ('PG', pg_found.get('buildings', [])),
        ('Excel', excel_data.get('buildings', [])),
        ('Config', config.get('buildings', [])),
    )
    proj.data_sources['energy_yearly'] = first_non_empty_source(
        ('PG', pg_found.get('energy_yearly', [])),
        ('Excel', excel_data.get('energy_yearly', [])),
        ('Config', config.get('energy_yearly', [])),
    )
    proj.data_sources['equipment'] = first_non_empty_source(
        ('PG', pg_found.get('equipment', [])),
        ('Excel', excel_data.get('equipment', [])),
        ('Config', config.get('equipment', [])),
    )
    proj.data_sources['metering'] = first_non_empty_source(
        ('PG', pg_found.get('metering', {})),
        ('Excel', excel_data.get('metering', {})),
        ('Config', config.get('metering', {})),
    )

    return proj


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


def _merge_energy(pg: List[dict], excel: List[dict], config: List[dict]) -> List[EnergyYearly]:
    """多源能耗数据合并（同一年保留第一个来源的整对象；coefficients 按能源类型跨来源合并）。"""
    seen = {}
    coeff_merges = {}  # year -> {energy_type: (value, source_name)}
    for source_name, src in [('PG', pg), ('Excel', excel), ('Config', config)]:
        for e in src:
            year = e.get('year', 0)
            if year and year not in seen:
                seen[year] = e
            # 按能源类型合并系数，优先级 PG > Excel > Config
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


def _merge_equipment(*sources: List[dict]) -> List[Equipment]:
    """多源设备合并（类别去重：同类别以后续来源补充）"""
    seen_cats = set()
    result = []
    for src in sources:
        for e in src:
            cat = e.get('category', '')
            if cat not in seen_cats:
                seen_cats.add(cat)
                result.append(Equipment(**e))
    return result


def _merge_metering(*sources: dict) -> MeteringInfo:
    """多源计量信息合并（优先非空值）"""
    merged = {}
    for src in sources:
        for k, v in src.items():
            if v not in (None, '', 0, False) and not merged.get(k):
                merged[k] = v
    return MeteringInfo(**merged)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python data_collector.py <项目名> [config.json]")
        sys.exit(1)

    project_name = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else None
    config = None
    if config_path:
        with open(config_path, encoding='utf-8') as f:
            config = json.load(f)

    # 采集
    pg_result = collect_from_pg(project_name)
    anomalies = detect_anomalies(pg_result.get('found', {}).get('energy_yearly', []))
    area_issue = detect_area_mismatch(
        pg_result.get('found', {}).get('buildings', []),
        config.get('building_area', 0) if config else 0
    )

    # 报告
    report = format_collection_report(pg_result, anomalies, area_issue, config is not None)
    print(report)

    # 构建并保存
    proj = build_audit_project(project_name, config)
    path = save_project(proj)
    print(f"\n[DataCollection] 数据已持久化: {path}")

    # 完整性检查
    ok, issues = check_completeness(asdict(proj))
    if not ok:
        print(f"\n⚠️ 数据完整性: {len(issues)} 项待补充:")
        for i in issues:
            print(f"  · {i}")
