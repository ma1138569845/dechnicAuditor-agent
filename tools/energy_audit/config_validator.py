"""
Config JSON 校验

在 run_pipeline.py 加载 config 后、运行前校验，提供友好错误提示。
"""

import json
from typing import List, Tuple

# ============================================================
# 必填/可选字段定义
# ============================================================

REQUIRED = [
    'unit_name',
    'institution_category',
    'building_area',
    'people_count',
    'audit_start',
    'audit_end',
]

OPTIONAL = [
    'unit_short', 'address', 'unit_type', 'specific_type',
    'contact_person', 'contact_phone', 'auditor', 'report_date',
    'province', 'data_start', 'data_end', 'admin_affiliation',
    'buildings', 'energy_yearly', 'equipment', 'metering',
    'management', 'energy_saving', 'images', 'chapter_texts',
]

FIELD_TYPES = {
    'unit_name': str,
    'unit_short': str,
    'address': str,
    'unit_type': str,
    'institution_category': str,
    'specific_type': str,
    'contact_person': str,
    'contact_phone': str,
    'auditor': str,
    'report_date': str,
    'province': str,
    'audit_start': str,
    'audit_end': str,
    'data_start': str,
    'data_end': str,
    'admin_affiliation': str,
    'building_area': (int, float),
    'people_count': (int, float),
    'buildings': list,
    'energy_yearly': list,
    'equipment': list,
    'metering': dict,
    'management': dict,
    'energy_saving': list,
    'images': list,
    'chapter_texts': dict,
}


def validate_config(config: dict) -> Tuple[bool, List[str]]:
    """校验 config JSON。返回 (有效?, 问题列表)"""
    errors = []

    # 1. 必填项检查
    for field in REQUIRED:
        if not config.get(field):
            errors.append(f"缺少必填字段: {field}")
        elif isinstance(config[field], str) and not config[field].strip():
            errors.append(f"字段为空: {field}")

    # 2. 类型检查
    for field, expected_type in FIELD_TYPES.items():
        if field not in config or not config.get(field):
            continue
        val = config[field]
        if isinstance(expected_type, tuple):
            if not isinstance(val, expected_type):
                types_str = ' 或 '.join(t.__name__ for t in expected_type)
                errors.append(f"类型错误: {field} 应为 {types_str}，实际为 {type(val).__name__}")
        else:
            if not isinstance(val, expected_type):
                errors.append(f"类型错误: {field} 应为 {expected_type.__name__}，实际为 {type(val).__name__}")

    # 3. 数值范围
    if config.get('building_area', 0) <= 0:
        errors.append("建筑面积必须大于0")
    if config.get('people_count', 0) <= 0:
        errors.append("用能人数必须大于0")

    # 4. 能耗数据完整性
    energy = config.get('energy_yearly', [])
    if not energy:
        errors.append("缺少能耗数据: energy_yearly 为空（报告第5章将无法生成指标）")
    else:
        years = [e.get('year') for e in energy if e.get('year')]
        if len(years) < 1:
            errors.append("energy_yearly 中缺少有效的年份数据")
        elif len(years) < 3:
            errors.append(f"energy_yearly 仅有 {len(years)} 年数据，建议提供3年数据用于基准计算")

    return (len(errors) == 0, errors)
