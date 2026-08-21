"""
报告数据完整性检查

由 data_collection_cli.py 在 build_and_save_project 之后调用，
发现缺失项时打印清晰提示并返回缺失清单（不阻断报告生成）。
"""

from typing import List, Dict, Tuple
import json


def check_completeness(report_data: dict) -> Tuple[bool, List[str]]:
    """检查 report_data 是否完整。返回 (完整?, 缺失项列表)"""
    missing = []

    # 封面
    cover = report_data.get('cover', {})
    if not cover.get('title'): missing.append("封面 → 报告标题")

    # 三张表
    tabs = report_data.get('audit_info_tables', {})
    if not tabs.get('institution', {}).get('name'): missing.append("表1 → 被审计单位名称")
    if not tabs.get('team_members'): missing.append("表2 → 审计组人员名单（当前显示【待补充】）")

    # 第1章
    ch1 = report_data.get('chapter1', {})
    if not ch1.get('audited_unit_short'): missing.append("1.1 → 被审计单位简称")
    if not ch1.get('address'): missing.append("1.2 → 地址")
    if not ch1.get('audit_cycle'): missing.append("1.3 → 审计周期")
    if not ch1.get('energy_types'): missing.append("1.2 → 能源类型（电/水/气/…）")

    # 第2章
    ch2 = report_data.get('chapter2', {})
    if not ch2.get('building_area'): missing.append("2.1 → 建筑面积")
    if not ch2.get('people_count'): missing.append("2.1 → 用能人数")
    if not ch2.get('buildings'): missing.append("2.2 → 建筑列表（至少1栋）")

    # 第5章
    ch5 = report_data.get('chapter5', {})
    if not ch5.get('energy_data'):
        missing.append("5.x → 能耗数据（完全缺失，无法生成指标表和图表）"
                       "\n     数据来源：DB ts_institution_energy_main/data → Excel → 用户手动输入")

    # 第6章
    ch6 = report_data.get('chapter6', {})
    if not ch6 and not ch6.get('_equipment'):
        missing.append("6.1 → 设备清单（完全缺失，无法生成设备表和系统描述）")

    return (len(missing) == 0, missing)


def print_missing_report(missing: List[str]) -> str:
    """打印数据缺失报告"""
    if not missing:
        return ""

    lines = [
        "=" * 55,
        "⚠️  数据完整性检查 — 发现 {} 项缺失".format(len(missing)),
        "=" * 55,
    ]
    for i, m in enumerate(missing, 1):
        lines.append(f"  {i}. {m}")
    lines.append("")
    lines.append("请补充上述数据后重新运行流水线。")
    lines.append("=" * 55)
    return '\n'.join(lines)
