# -*- coding: utf-8 -*-
"""数据质量守卫测试：设备功率单位校验（W/kW 量级）。

背景事故：设备清单把 W 写成 kW（40.00 kW×224 面板灯、150 kW×105 电脑、
120 kW×20 打印机、120 kW×5 电梯、20 kW×163 云桌面），数值放大 1000 倍。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.energy_audit.data_collection_cli import detect_equipment_power_unit_issue


def test_flags_small_power_devices_with_kw_scale():
    """照明/办公/电梯等小功率设备出现 kW 级功率 → 标记可疑"""
    equipment = [
        {"name": "面板灯", "category": "照明", "spec": "40.00 kW"},
        {"name": "台式机", "category": "办公", "spec": "150.00 kW"},
        {"name": "打印机", "category": "办公", "spec": "120.00 kW"},
        {"name": "电梯", "category": "动力", "spec": "120.00 kW"},
        {"name": "云桌面", "category": "办公", "spec": "20.00 kW"},
    ]
    issues = detect_equipment_power_unit_issue(equipment)
    assert len(issues) == 5, f"应标记 5 台，实际 {len(issues)}"
    assert all(i["type"] == "功率单位可疑" for i in issues)


def test_does_not_flag_large_kw_devices():
    """真正的大功率设备（冷水机组/水泵）kW 级不误报"""
    equipment = [
        {"name": "冷水机组", "category": "空调", "spec": "麦克维尔 187 kW"},
        {"name": "冷冻水泵", "category": "空调", "spec": "45 kW"},
        {"name": "冷却塔", "category": "空调", "spec": "22 kW"},
    ]
    issues = detect_equipment_power_unit_issue(equipment)
    assert issues == [], f"不应误报大功率设备，实际 {issues}"


def test_watt_scale_values_not_flagged():
    """W 级功率（数值可能 >100）不标记——但 spec 未标 kW 单位时跳过"""
    equipment = [
        {"name": "面板灯", "category": "照明", "spec": "40 W"},
        {"name": "电脑", "category": "办公", "spec": "150 W"},
    ]
    issues = detect_equipment_power_unit_issue(equipment)
    assert issues == [], f"W 单位不应标记，实际 {issues}"


def test_empty_and_missing_fields():
    assert detect_equipment_power_unit_issue([]) == []
    assert detect_equipment_power_unit_issue(None) == []
    assert detect_equipment_power_unit_issue(
        [{"name": "某设备", "category": "其他", "spec": ""}]) == []
