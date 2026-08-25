#!/usr/bin/env python3
"""DataCollection 命令行调度入口 — 采集编排 + 数据质量检查

采集与构建逻辑在 pg_collector（collect_from_pg / build_and_save_project），
本模块只负责「面向人的流程编排」，不含数据库查询逻辑：
  1. 采集 PG 结果并复用给构建（不重复查询）
  2. 质量检查：能耗异常 / 建筑面积校验 / 完整性检查
  3. 采集报告格式化
  4. CLI 入口串联整个流程

用法:
    python data_collection_cli.py <项目名>

示例:
    python data_collection_cli.py 莘县县政府

执行流程:
    collect_from_pg（PG 取数）
      → 能耗异常检测 / 建筑面积校验
      → 格式化采集报告（打印）
      → build_and_save_project（构建 AuditProject + 持久化，复用采集结果）
      → check_completeness（完整性检查，列出待补充项）

作者: 马天远 | 版本: 2.1.0 | 日期: 2026-08-19
prod - serial number - 2
"""

import sys
from dataclasses import asdict
from typing import Dict, List, Optional

from tools.energy_audit._paths import PROJECT_ROOT  # noqa: F401

try:
    from tools.energy_audit.pg_collector import build_and_save_project, collect_from_pg
    from tools.energy_audit.project_data import _PROJECTS_ROOT, total_building_area
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
    sum_area = total_building_area(buildings)
    if declared_area > 0 and abs(sum_area - declared_area) / declared_area > 0.05:
        return (f"建筑面积不匹配：各建筑合计 {sum_area:.0f}m²，"
                f"声明的总面积 {declared_area:.0f}m²，偏差 {abs(sum_area - declared_area):.0f}m²")
    return None


# ============================================================
# 采集报告格式化
# ============================================================

def format_collection_report(pg_result: dict, anomalies: List[dict],
                               area_issue: Optional[str] = None) -> str:
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
        total_area = total_building_area(buildings)
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
                      f", {'有独立计量电表' if metering.get('has_separate_metering') else '无独立计量电表'}")

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

    # 保存路径
    lines.append(f"\n📁 数据持久化位置: {_PROJECTS_ROOT}")
    lines.append("=" * 50)
    return '\n'.join(lines)


# ============================================================
# 命令行入口
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python data_collection_cli.py <项目名>")
        sys.exit(1)

    project_name = sys.argv[1]

    # 采集
    pg_result = collect_from_pg(project_name)
    anomalies = detect_anomalies(pg_result.get('found', {}).get('energy_yearly', []))

    # 报告
    report = format_collection_report(pg_result, anomalies)
    print(report)

    # 构建并保存（复用第一轮采集结果，避免二次查询 PG）
    proj = build_and_save_project(project_name, pg_result=pg_result)
    print(f"\n[DataCollection] 数据已持久化: {_PROJECTS_ROOT}")

    # 完整性检查
    ok, issues = check_completeness(asdict(proj))
    if not ok:
        print(f"\n⚠️ 数据完整性: {len(issues)} 项待补充:")
        for i in issues:
            print(f"  · {i}")
