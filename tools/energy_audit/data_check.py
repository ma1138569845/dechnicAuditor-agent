"""
报告数据完整性检查

由 data_collection_cli.py 在 build_and_save_project 之后调用，
发现缺失项时打印清晰提示并返回缺失清单（不阻断报告生成）。
"""

from typing import List, Dict, Tuple
import json


def _is_project_shape(data: dict) -> bool:
    """入参是不是 AuditProject 结构（asdict(project)）。"""
    return any(k in data for k in ("base", "buildings", "energy_yearly", "equipment"))


def check_completeness(report_data: dict) -> Tuple[bool, List[str]]:
    """检查数据完整性。返回 (完整?, 缺失项列表)

    兼容两种入参（2026-10-13 修）：
      · **AuditProject 结构**（`asdict(project)`：base/buildings/energy_yearly/equipment/…）
        —— 采集 CLI `data_collection_cli.py` 实传这种。修前它直接按下面的旧键路径查，
        每条都查空，于是把数据齐全的项目报成"5.x 能耗数据完全缺失 / 6.1 设备清单缺失"
        等**假警报**（岚山区人民医院实测：energy_yearly 3 条、monthly 36 条、equipment 28 条
        全在，却报了 15 项缺失）。
      · 旧 report_data（cover / audit_info_tables / chapterN /…）—— V1 的
        `mode_data_check.project_to_report_data()` 转换后的形态，仍走原逻辑。
    缺失项**文案保持不变**：V1 按关键词映射严重级别（见 mode_data_check.py）。
    """
    if _is_project_shape(report_data):
        return _check_project(report_data)
    return _check_legacy(report_data)


def _check_project(d: dict) -> Tuple[bool, List[str]]:
    """AuditProject 结构（v2）的完整性检查——与旧口径逐项对齐。"""
    missing: List[str] = []
    base = d.get("base") or {}
    team = d.get("audit_team") or []
    coop = d.get("cooperation") or []
    energy = d.get("energy_yearly") or []
    equipment = d.get("equipment") or []

    def _blank(v) -> bool:
        s = str(v or "").strip()
        return (not s) or s in ("【待补充】", "待补充")

    if _blank(base.get("unit_name")):
        missing.append("封面 → 报告标题")
    if _blank(base.get("audit_org_name")):
        missing.append("审计机构名称")
    for field, label in (("audit_org_address", "审计机构详细地址"),
                         ("audit_org_contact", "审计机构负责人"),
                         ("audit_org_phone", "审计机构联系方式")):
        if _blank(base.get(field)):
            missing.append(f"审计机构信息表：{label}（缺失或占位）")
    if not any(not _blank(m.get("name")) for m in team):
        missing.append("审计组人员名单（当前显示【待补充】）")
    if not any(not _blank(c.get("name")) for c in coop):
        missing.append("审计配合人员名单（当前显示【待补充】）")

    # 第1章
    if _blank(base.get("unit_short")) and _blank(base.get("unit_name")):
        missing.append("1.1 → 被审计单位简称")
    if _blank(base.get("address")):
        missing.append("1.2 → 地址")
    if _blank(base.get("audit_period")):
        missing.append("1.3 → 审计期")
    if _blank(base.get("base_period")):
        missing.append("1.3 → 基准期")
    has_energy = any(
        float(r.get("electricity_kwh") or 0) or float(r.get("water_m3") or 0)
        or float(r.get("natural_gas_m3") or 0) or float(r.get("heating_cost_wan") or 0)
        or float(r.get("petrol_kg") or 0) or float(r.get("diesel_kg") or 0)
        for r in energy)
    if not has_energy:
        missing.append("1.2 → 能源类型（电/水/气/…）")

    # 第2章
    if not base.get("building_area"):
        missing.append("2.1 → 建筑面积")
    if not base.get("people_count"):
        missing.append("2.1 → 用能人数")
    if not (d.get("buildings") or []):
        missing.append("2.2 → 建筑列表（至少1栋）")

    # 第5章
    if not energy:
        missing.append("5.x → 能耗数据（完全缺失，无法生成指标表和图表）"
                       "\n     数据来源：DB ts_institution_energy_main/data → Excel → 用户手动输入")

    # 第6章
    if not equipment:
        missing.append("6.1 → 设备清单（完全缺失，无法生成设备表和系统描述）")

    return (len(missing) == 0, missing)


def _check_legacy(report_data: dict) -> Tuple[bool, List[str]]:
    """旧 report_data 结构的完整性检查（V1 转换后的入参走这里，逻辑与文案不变）。"""
    missing = []

    # 封面
    cover = report_data.get('cover', {})
    if not cover.get('title'): missing.append("封面 → 报告标题")

    # 三张表（审计基本信息）
    tabs = report_data.get('audit_info_tables', {})
    inst = tabs.get('institution', {})
    if not inst.get('name'): missing.append("审计机构名称")
    for field, label in (('address', '审计机构详细地址'), ('contact', '审计机构负责人'), ('phone', '审计机构联系方式')):
        val = str(inst.get(field, '') or '').strip()
        if not val or val in ('【待补充】', '待补充'):
            missing.append(f"审计机构信息表：{label}（缺失或占位）")
    team = tabs.get('team_members') or []
    # 逐人检查：名单为空或任一人姓名为空/占位，都视为未提供
    if not team or not any(str(m.get('name', '') or '').strip() not in ('', '【待补充】', '待补充') for m in team):
        missing.append("审计组人员名单（当前显示【待补充】）")
    coop = tabs.get('cooperation') or []
    if not coop or not any(str(c.get('name', '') or '').strip() not in ('', '【待补充】', '待补充') for c in coop):
        missing.append("审计配合人员名单（当前显示【待补充】）")

    # 第1章
    ch1 = report_data.get('chapter1', {})
    if not ch1.get('audited_unit_short'): missing.append("1.1 → 被审计单位简称")
    if not ch1.get('address'): missing.append("1.2 → 地址")
    if not ch1.get('audit_period'): missing.append("1.3 → 审计期")
    if not ch1.get('base_period'): missing.append("1.3 → 基准期")
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
    if not ch6 and not (ch6 or {}).get('_equipment'):
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
