"""
能源审计项目数据模型 —— dataCollection agent 输出规范

位置: ~/projects/energy-audit/<project_name>/data.json
追溯: 每个字段记录 source (DB/Excel/用户) + timestamp

作者: 马天远 | 版本: 2.0.0 | 日期: 2026-07-31

prod - serial number - 1
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
import hashlib
import json
import re
import uuid
from pathlib import Path


# ============================================================
# 照片分类（单一权威契约）
# 采集器、photo_manager、照片归置器和报告生成器都只使用这里的规范名；
# 旧 data.json 的别名在读取边界统一归一，避免同一概念在链路中换名。
# ============================================================
PHOTO_CATEGORIES = (
    '单位整体外观',   # 第2章 2.1 段落后紧跟（ts_institution_scene.scene_img_id，图2.1）
    '建筑外观',      # 第2章 建筑全景/主立面照；逐栋归属写入 building_name
    '管理文件/荣誉',  # 第3章 能源管理制度文件、节能荣誉证书
    '计量器具',      # 第4章 电表、水表、气表等计量仪表照片
    '缴费发票',      # 第5章 电费、水费、燃气费等缴费发票示例
    '制冷设备',      # 第6章 冷水机组/多联机外机/分体空调等
    '照明设备',      # 第6章 典型照明灯具照片
    '办公设备',      # 第6章 电脑、打印机等办公设备
    '信息机房',      # 第6章 数据中心/信息机房设备
    '医疗设备',      # 第6章 CT、X射线等医疗专用设备
    '其他用电设备',  # 第6章 电梯、热水器等零散用电设备
    '特殊设备',      # 旧分类兜底：无法细分用途的特殊设备
    '变压器/配电',   # 第6章 变压器室、配电柜等
    '水泵/水箱',     # 第6章 生活水泵、消防水箱等
    '厨房设备',      # 第6章 厨房设备
    '用水设施',      # 第6章 6.2 绿化灌溉、其他用水设施
    '燃气设备',      # 第6章 6.4 燃气锅炉、燃气热水器等
    '节能改造示意',  # 第7章 改造前现状照片（可选对比）
)

# 旧版 data.json 只做读取兼容；新采集和新报告一律写规范名。
LEGACY_PHOTO_CATEGORY_ALIASES = {
    '能耗账单': '缴费发票',
    '各建筑外观': '建筑外观',
}

# 设备照片上传字段 → 报告图注中的“字段名称”。
# 同一设备存在多个非空上传字段时，图注按“设备名称 + 字段名称”展示；
# 只有一个非空字段时仍只展示设备名称。字段名以平台字段含义为准，
# 不把内部列名（如 motor_img）直接暴露给报告读者。
# EA-CHECKPOINT-ITEM2-PHOTO-FIELD-CAPTION：中文命名待审，
# 变更前先看 docs/checkpoints/2026-10-23-item2-chapter6-photo-field-caption.md。
EQUIPMENT_IMAGE_FIELD_LABELS = {
    'device_img': '设备图片',
    'system_img': '系统图片',
    'water_pump_img': '循环水泵图片',
    'air_pump_img': '空气源热泵铭牌图片',
    'tower_img': '参数铭牌/自动阀门图片',
    'fan_img': '参数铭牌/手动阀门图片',
    'heat_change_img': '换热器照片',
    'motor_img': '电机铭牌图片',
    'pump_img': '泵体图片',
}

EQUIPMENT_IMAGE_FIELD_LABELS_BY_CATEGORY = {
    # 这两张表中的 device_img 明确表示“设备整体图片”。
    ('其他设备', 'device_img'): '设备整体图片',
    ('输配设备', 'device_img'): '设备整体图片',
}

# 平台各设备表把“其他设备”的真实名称放在不同字段。这里按报告设备分类
# 固化来源，避免只认 other_device_name 而漏掉办公设备等表。
OTHER_EQUIPMENT_REAL_NAME_FIELDS = {
    '空调': ('other_device_name',),
    '末端设备': ('other_device_name',),
    '照明': ('other_device_name',),
    '办公': ('device_name',),
    '其他设备': ('other_device_name',),
    '特殊设备': ('other_device_name',),
}

# 平台下拉框中的泛化选项名；这类值不能作为报告标题。
OTHER_EQUIPMENT_GENERIC_NAMES = frozenset({
    '其他',
    '其它',
    '其他设备',
    '其它设备',
    '其他特殊设备',
    '其它特殊设备',
    '其他特殊末端设备',
    '其它特殊末端设备',
    '其他特殊办公设备',
    '其它特殊办公设备',
    '其他特殊灯具',
    '其它特殊灯具',
    '其他特殊灯具等',
    '其它特殊灯具等',
})


def _clean_equipment_text(record: Dict[str, Any], field_name: str) -> str:
    return str(record.get(field_name) or '').strip()


def _is_other_equipment_generic(value: str) -> bool:
    return re.sub(r'\s+', '', value) in OTHER_EQUIPMENT_GENERIC_NAMES


def equipment_display_name(record: Dict[str, Any], category: str = '') -> str:
    """返回设备在报告中的真实名称。

    平台不同设备表保存真实名称的字段不同：冷热源、末端、照明、特殊设备
    使用 ``other_device_name``，办公设备使用 ``device_name``（泛化选项
    存于 ``type``）。只有主名称是泛化选项时才替换；普通设备名不被覆盖。
    """
    primary = _clean_equipment_text(record, 'device_name')
    generic_primary = (
        not primary
        or primary == '未命名'
        or _is_other_equipment_generic(primary)
    )
    # 办公设备表的 device_name 本身就是真实名称，泛化选项在 type。
    generic_office = (
        category == '办公'
        and _is_other_equipment_generic(_clean_equipment_text(record, 'type'))
    )
    if not (generic_primary or generic_office):
        return primary or '未命名'

    for field_name in OTHER_EQUIPMENT_REAL_NAME_FIELDS.get(category, ('other_device_name',)):
        real_name = _clean_equipment_text(record, field_name)
        if real_name and not _is_other_equipment_generic(real_name):
            return real_name

    # 泛化名没有配套真实名称时，保留原登记值，交由数据核查处理；
    # 不能静默拼接或生成一个看似真实的设备名。
    return primary or '未命名'


def extract_equipment_image_fields(
    record: Dict[str, Any],
    category: str = '',
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """从设备原始记录提取图片 field 语义与扁平 file-id 列表。

    返回 ``(img_ids, img_fields)``。``img_fields`` 保持数据库字段顺序：
    ``[{"field": "motor_img", "label": "电机铭牌图片", "ids": [101]}]``。
    ``img_ids`` 继续作为旧链路兼容键。
    """
    img_ids: List[Any] = []
    img_fields: List[Dict[str, Any]] = []
    for field_name, raw_value in record.items():
        if not field_name.endswith('_img') or raw_value in (None, ''):
            continue
        raw_text = str(raw_value).strip()
        if not raw_text:
            continue
        ids: List[Any] = []
        for raw_id in re.split(r'[,，;；\s]+', raw_text.strip('[]')):
            raw_id = raw_id.strip().strip('"\'')
            if not raw_id:
                continue
            try:
                ids.append(int(raw_id))
            except ValueError:
                ids.append(raw_id)
        if not ids:
            continue
        label = (
            EQUIPMENT_IMAGE_FIELD_LABELS_BY_CATEGORY.get((category, field_name))
            or EQUIPMENT_IMAGE_FIELD_LABELS.get(field_name)
            or field_name.removesuffix('_img').replace('_', ' ')
        )
        img_fields.append({
            'field': field_name,
            'label': label,
            'ids': ids,
        })
        img_ids.extend(ids)
    return img_ids, img_fields


INFORMATION_ROOM_STRONG_KEYWORDS = (
    '数据中心',
    '信息中心',
    '信息机房',
    '数据机房',
    '服务器',
    '网络设备',
    '存储设备',
)
MEDICAL_INSTITUTION_KEYWORDS = ('医疗', '医院')
MEDICAL_EQUIPMENT_KEYWORDS = (
    '医疗设备', '医疗', 'CT', 'X光', 'X射线', '磁共振', 'MRI', 'DSA',
)
HOSPITAL_LEVEL_ALIASES = {
    'A': 'A', 'B': 'B', 'C': 'C',
    '一级': 'A', '二级': 'B', '三级': 'C',
}


def _equipment_evidence_text(record: Dict[str, Any]) -> Tuple[str, str]:
    text = ' '.join(str(record.get(key) or '') for key in (
        'name',
        'device_name',
        'other_device_name',
        'spec',
        'type',
        'location',
        'remark',
    ))
    return text, text.lower()


def is_information_room_equipment(record: Dict[str, Any]) -> bool:
    """只按明确的信息中心证据分类，普通“机房”不构成证据。"""
    text, lowered = _equipment_evidence_text(record or {})
    return (
        any(keyword in text for keyword in INFORMATION_ROOM_STRONG_KEYWORDS)
        or 'data center' in lowered
        or 'server room' in lowered
    )


def is_medical_equipment_record(record: Dict[str, Any]) -> bool:
    text, lowered = _equipment_evidence_text(record or {})
    return (
        any(keyword in text for keyword in MEDICAL_EQUIPMENT_KEYWORDS)
        or any(keyword in lowered for keyword in ('medical', 'radiology'))
    )


def is_medical_institution(
    unit_func: str,
    institution_category: str = '',
    unit_name: str = '',
) -> bool:
    """平台码优先；只有平台码为空时才允许类别或单位名回退。"""
    code = str(unit_func or '').strip().upper()
    if code:
        return code == 'C'
    fallback_text = f"{institution_category or ''} {unit_name or ''}"
    return any(
        keyword in fallback_text
        for keyword in MEDICAL_INSTITUTION_KEYWORDS
    )


def normalize_hospital_level(value: str) -> str:
    text = str(value or '').strip().upper()
    if not text:
        return ''
    if text in HOSPITAL_LEVEL_ALIASES:
        return HOSPITAL_LEVEL_ALIASES[text]
    for keyword, code in HOSPITAL_LEVEL_ALIASES.items():
        if keyword not in ('A', 'B', 'C') and keyword in text:
            return code
    return ''


def equipment_photo_slots(equipment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把一个设备的每个非空附件 ID 展开成独立图片槽位。"""
    record = dict(equipment or {})

    def _file_ids(value: Any) -> List[str]:
        if isinstance(value, (list, tuple, set)):
            return [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]
        return [
            item
            for item in re.split(
                r'[,，;；\s]+',
                str(value or '').strip('[]'),
            )
            if item.strip()
        ]

    fields: List[Dict[str, Any]] = []
    for raw_field in record.get('img_fields') or []:
        if not isinstance(raw_field, dict):
            continue
        field = str(raw_field.get('field') or 'img_ids').strip()
        label = str(raw_field.get('label') or '').strip()
        file_ids = _file_ids(raw_field.get('ids'))
        if file_ids:
            fields.append({'field': field or 'img_ids', 'label': label, 'ids': file_ids})

    flat_ids = _file_ids(record.get('img_ids'))
    if not fields and flat_ids:
        fields = [{'field': 'img_ids', 'label': '', 'ids': flat_ids}]
    elif fields and flat_ids:
        covered_ids = {
            file_id
            for field in fields
            for file_id in field['ids']
        }
        missing_flat_ids = [
            file_id for file_id in flat_ids
            if file_id not in covered_ids
        ]
        if missing_flat_ids:
            if len(fields) == 1:
                fields[0]['ids'].extend(missing_flat_ids)
            else:
                synthetic = next(
                    (
                        field for field in fields
                        if field['field'] == 'img_ids'
                    ),
                    None,
                )
                if synthetic is None:
                    synthetic = {
                        'field': 'img_ids',
                        'label': '',
                        'ids': [],
                    }
                    fields.append(synthetic)
                synthetic['ids'].extend(missing_flat_ids)

    use_field_label = len(fields) > 1
    name = str(
        record.get('name')
        or record.get('other_device_name')
        or record.get('device_name')
        or ''
    ).strip()
    source_ref = str(record.get('image_source_ref') or 'equipment[]').strip()
    slots: List[Dict[str, Any]] = []
    seen = set()
    for field in fields:
        caption_label = (
            f"{name}{field['label'] or '图片'}"
            if use_field_label
            else name
        )
        for attachment_index, file_id in enumerate(field['ids']):
            key = (field['field'], str(file_id))
            if key in seen:
                continue
            seen.add(key)
            slots.append({
                'equipment': record,
                'name': name,
                'category': str(record.get('category') or '').strip(),
                'field': field['field'],
                'field_label': field['label'],
                'caption_label': caption_label,
                'file_id': str(file_id),
                'attachment_index': attachment_index,
                'image_source_ref': source_ref,
            })
    return slots


def normalize_photo_category(value: Any, *, strict: bool = False) -> str:
    """把旧分类归一为规范名。

    strict=False 用于读取旧项目：未知分类原样保留，避免静默丢数据。
    strict=True 用于采集/归置写入口：未知分类直接报错，防止脏口径继续扩散。
    """
    category = str(value or '').strip()
    category = LEGACY_PHOTO_CATEGORY_ALIASES.get(category, category)
    if strict and category and category not in PHOTO_CATEGORIES:
        raise ValueError(f"未知照片分类: {category!r}；合法分类: {PHOTO_CATEGORIES}")
    return category


def photo_category_for_equipment(
    category: str,
    *,
    name: str = '',
    spec: str = '',
    use_type: str = '',
    location: str = '',
    remark: str = '',
) -> str:
    """设备台账分类 → 第6章照片分类（数据库字段到报告路由的唯一映射）。"""
    category = str(category or '').strip()
    if category in PHOTO_CATEGORIES and category != '特殊设备':
        return category

    direct = {
        '空调': '制冷设备',
        '照明': '照明设备',
        '办公': '办公设备',
        '厨房': '厨房设备',
        '生活热水': '其他用电设备',
        '输配设备': '制冷设备',
        '蒸汽': '制冷设备',
        '变配电': '变压器/配电',
    }
    if category != '特殊设备' and category != '动力':
        return direct.get(category, '')

    record = {
        'name': name,
        'spec': spec,
        'use_type': use_type,
        'location': location,
        'remark': remark,
    }
    text = ' '.join(str(v or '') for v in
                    (name, spec, use_type, location, remark))
    if category == '动力':
        if any(k in text for k in ('水泵', '水箱')):
            return '水泵/水箱'
        return '其他用电设备'

    # “特殊设备”表同时承载数据中心和医疗设备，必须按内容细分。
    if is_information_room_equipment(record):
        return '信息机房'
    if is_medical_equipment_record(record):
        return '医疗设备'
    return '特殊设备'


# 第6章设备事实小节与照片目标小节的单一字典。
# 设备正文按“设备事实”落位；同一照片可优先进入更具体的 6.2 用水 / 6.4 燃气。
CHAPTER6_SECTIONS = {
    'air_heating': {
        'equipment_title': '空调与供暖系统',
        'photo_title': '空调与供暖系统',
    },
    'lighting': {
        'equipment_title': '照明系统',
        'photo_title': '照明系统',
    },
    'office': {
        'equipment_title': '办公设备系统',
        'photo_title': '办公设备系统',
    },
    'information_room': {
        'equipment_title': '信息机房系统',
        'photo_title': '信息机房系统',
    },
    'medical_equipment': {
        'equipment_title': '医疗设备系统',
        'photo_title': '医疗设备系统',
    },
    'substation': {
        'equipment_title': '变配电系统',
        'photo_title': '变配电系统',
    },
    'other_energy': {
        'equipment_title': '其他用电设备',
        'photo_title': '其他用电设备',
    },
    'water_system': {
        'equipment_title': '用水系统',
        'photo_title': '用水系统',
    },
    'gas_system': {
        'equipment_title': '用燃气系统',
        'photo_title': '用燃气系统',
    },
}

WATER_AUX_PHOTO_LABELS = {
    'greening': '绿化灌溉设施',
    'other': '其他用水设施',
    'road': '道路冲洗设施',
}


def chapter6_water_aux_photo_items(water_aux: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把 6.2 附属用水照片转成统一的第6章照片绑定项。"""
    def _photo_ids(raw_value: Any) -> List[Any]:
        if isinstance(raw_value, (list, tuple, set)):
            raw_text = ' '.join(str(item or '') for item in raw_value)
        else:
            raw_text = str(raw_value or '')
        ids: List[Any] = []
        for raw_id in re.split(r'[,，;；\s]+', raw_text.strip('[]')):
            raw_id = raw_id.strip().strip('"\'')
            if not raw_id:
                continue
            try:
                ids.append(int(raw_id))
            except ValueError:
                ids.append(raw_id)
        return ids

    items: List[Dict[str, Any]] = []
    for group, base_label in WATER_AUX_PHOTO_LABELS.items():
        for record in (water_aux or {}).get(group, []) or []:
            if not isinstance(record, dict):
                continue
            img_fields: List[Dict[str, Any]] = []
            for raw_field in record.get('img_fields') or []:
                if not isinstance(raw_field, dict):
                    continue
                ids = _photo_ids(raw_field.get('ids'))
                if ids:
                    img_fields.append({
                        'field': str(raw_field.get('field') or 'img_ids').strip(),
                        'label': str(raw_field.get('label') or '').strip(),
                        'ids': ids,
                    })
            if img_fields:
                img_ids = [
                    file_id
                    for field in img_fields
                    for file_id in field['ids']
                ]
            else:
                img_ids, img_fields = extract_equipment_image_fields(
                    record,
                    '用水设施',
                )
            if not img_fields:
                continue
            items.append({
                'name': base_label,
                'category': '用水设施',
                'img_ids': img_ids,
                'img_fields': img_fields,
                'equipment_section_key': 'water_system',
                'equipment_section_title': CHAPTER6_SECTIONS['water_system']['equipment_title'],
                'photo_section_key': 'water_system',
                'photo_section_title': CHAPTER6_SECTIONS['water_system']['photo_title'],
                'routing_reason': f'water_aux_{group}',
                'image_source_ref': f'water_aux.{group}[]',
            })
    return items


def _number_or_none(value: Any) -> Optional[float]:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def special_power_summary(record: Dict[str, Any]) -> Dict[str, Any]:
    """汇总特殊设备四类功率明细，只在单位明确时换算为 kW。

    平台历史数据同时存在 W 与 kW 两种输入尺度，且部分行没有 ``power_unit``。
    为避免把 500 W 猜成 500 kW，缺少明确单位时保留原始明细，但
    ``total_power_kw`` 必须为 ``None``。
    """
    components: List[Dict[str, Any]] = []
    for key, label in (
        ('server', '服务器'),
        ('network', '网络设备'),
        ('storage', '存储设备'),
        ('air', '空调设备'),
    ):
        quantity = _number_or_none(record.get(f'{key}_num'))
        unit_power = _number_or_none(record.get(f'{key}_power'))
        if quantity is None and unit_power is None:
            continue
        components.append({
            'name': label,
            'field': key,
            'quantity': quantity,
            'unit_power': unit_power,
        })

    raw_unit = str(record.get('power_unit') or '').strip()
    unit = raw_unit.lower().replace('千瓦', 'kw').replace('瓦', 'w')
    total_power_kw: Optional[float] = None
    power_error = ''
    if unit in ('w', 'kw'):
        complete = components and all(
            item['quantity'] is not None and item['unit_power'] is not None
            for item in components
        )
        if complete:
            divisor = 1000.0 if unit == 'w' else 1.0
            total_power_kw = round(sum(
                item['quantity'] * item['unit_power'] / divisor
                for item in components
            ), 6)
        else:
            power_error = 'power_components_incomplete'
    elif components:
        power_error = 'power_unit_missing'

    return {
        'power_unit': raw_unit,
        'power_components': components,
        'total_power_kw': total_power_kw,
        'routing_power_error': power_error,
    }


def _chapter6_route(
    section_key: str,
    *,
    photo_category: str,
    photo_section_key: Optional[str] = None,
    routing_reason: str = '',
) -> Dict[str, str]:
    photo_key = photo_section_key or section_key
    return {
        'photo_category': photo_category,
        'equipment_section_key': section_key,
        'equipment_section_title': CHAPTER6_SECTIONS[section_key]['equipment_title'],
        'photo_section_key': photo_key,
        'photo_section_title': CHAPTER6_SECTIONS[photo_key]['photo_title'],
        'routing_reason': routing_reason,
    }


def chapter6_route_for_equipment(
    equipment: Dict[str, Any],
    unit_func: str = '',
    children_func: str = '',
    institution_category: str = '',
    unit_name: str = '',
) -> Dict[str, str]:
    """设备记录 → 第6章设备事实小节与照片目标小节的唯一路由。"""
    record = dict(equipment or {})
    category = str(record.get('category') or '').strip()
    name = str(record.get('name') or record.get('device_name') or '').strip()

    if category == '变配电':
        return _chapter6_route(
            'substation',
            photo_category='变压器/配电',
            routing_reason='substation',
        )

    if category == '照明':
        return _chapter6_route(
            'lighting',
            photo_category='照明设备',
            routing_reason='lighting',
        )

    if category == '办公':
        return _chapter6_route(
            'office',
            photo_category='办公设备',
            routing_reason='office',
        )

    # 卫生器具表整体属于 6.2 用水系统，不能作为普通“其他用电设备”漏回 6.1。
    if category == '卫生器具':
        return _chapter6_route(
            'water_system',
            photo_category='用水设施',
            routing_reason='hygiene_fixture',
        )

    if category == '动力' and any(
        key in name for key in ('生活水泵', '给水泵', '供水泵')
    ):
        return _chapter6_route(
            'other_energy',
            photo_category='水泵/水箱',
            routing_reason='domestic_water_pump',
        )

    is_named_gas_equipment = (
        any(key in name for key in ('燃气', '天然气', '液化气', '燃油'))
        and any(key in name for key in ('锅炉', '吸收式', '热水器', '灶'))
        or category in ('蒸汽', '厨房')
        and any(key in name for key in ('燃气', '天然气', '液化气', '燃油'))
    )
    has_recorded_combustion = any(
        (_number_or_none(record.get(key)) or 0) > 0
        for key in ('gas_value', 'fuel_value')
    )
    is_combustion_absorption = any(
        key in name for key in ('吸收式', '溴化锂', '直燃')
    )
    is_recorded_combustion_equipment = (
        is_combustion_absorption and has_recorded_combustion
    )

    # 生活热水系统表的设备事实仍按能源形式归属，但照片统一进入 6.2
    # 用水系统，避免燃气热水设备被 6.4 的燃气路由提前截走。
    if category == '生活热水':
        is_combustion_hot_water = (
            is_named_gas_equipment or is_recorded_combustion_equipment
        )
        return _chapter6_route(
            'gas_system' if is_combustion_hot_water else 'other_energy',
            photo_category='用水设施',
            photo_section_key='water_system',
            routing_reason=(
                'hot_water_combustion_photo_to_water_system'
                if is_combustion_hot_water
                else 'non_combustion_hot_water'
            ),
        )

    if is_named_gas_equipment or is_recorded_combustion_equipment:
        return _chapter6_route(
            'gas_system',
            photo_category=(
                '厨房设备'
                if category == '厨房' or '灶' in name
                else '燃气设备'
            ),
            routing_reason=(
                'gas_equipment'
                if is_named_gas_equipment
                else 'recorded_combustion_equipment'
            ),
        )

    if category == '末端设备':
        return _chapter6_route(
            'air_heating',
            photo_category='制冷设备',
            routing_reason='terminal_equipment',
        )

    if category in ('空调', '输配设备'):
        return _chapter6_route(
            'air_heating',
            photo_category='制冷设备',
            routing_reason=f'{category}_equipment',
        )

    if category == '其他设备' and any(
        key in name for key in ('冷却塔', '空调系统补水装置')
    ):
        return _chapter6_route(
            'air_heating',
            photo_category='制冷设备',
            routing_reason='air_heating_auxiliary',
        )

    if category == '其他设备':
        return _chapter6_route(
            'other_energy',
            photo_category='其他用电设备',
            routing_reason='other_equipment',
        )

    if category == '特殊设备':
        if is_information_room_equipment(record):
            total_power_kw = _number_or_none(record.get('total_power_kw'))
            if total_power_kw is not None and total_power_kw > 100:
                return _chapter6_route(
                    'information_room',
                    photo_category='信息机房',
                    routing_reason='information_room_power_gt_100kw',
                )
            reason = (
                'information_room_power_gt_100kw'
                if total_power_kw is not None and total_power_kw > 100
                else (
                    'information_room_power_le_100kw'
                    if total_power_kw is not None
                    else 'information_room_power_unconfirmed'
                )
            )
            return _chapter6_route(
                'other_energy',
                photo_category='信息机房',
                routing_reason=reason,
            )

        is_medical_equipment = is_medical_equipment_record(record)
        medical_institution = is_medical_institution(
            unit_func,
            institution_category,
            unit_name,
        )
        hospital_level = normalize_hospital_level(children_func)
        if (
            is_medical_equipment
            and medical_institution
            and hospital_level in ('B', 'C')
        ):
            return _chapter6_route(
                'medical_equipment',
                photo_category='医疗设备',
                routing_reason=f'hospital_level_{hospital_level}',
            )
        if is_medical_equipment:
            return _chapter6_route(
                'other_energy',
                photo_category='医疗设备',
                routing_reason=(
                    'medical_equipment_requires_secondary_or_tertiary_hospital'
                ),
            )
        return _chapter6_route(
            'other_energy',
            photo_category='特殊设备',
            routing_reason='special_equipment_unclassified',
        )

    photo_category = photo_category_for_equipment(
        category,
        name=name,
        spec=str(record.get('spec') or ''),
        use_type=str(record.get('use_type') or ''),
        location=str(record.get('location') or ''),
        remark=str(record.get('remark') or ''),
    )
    return _chapter6_route(
        'other_energy',
        photo_category=photo_category or '其他用电设备',
        routing_reason='other_energy',
    )


# ============================================================
# 数据模型
# ============================================================

@dataclass
class ProjectBase:
    """项目基本信息"""
    name: str                          # 项目名称 ex: "莘县县政府能源审计"
    unit_name: str                     # 被审计单位全称
    unit_short: str = ""               # 被审计单位简称
    address: str = ""                  # 地址
    unit_type: str = "公共机构"          # 审计类型: 公共机构/公共建筑/工业企业
    institution_category: str = ""     # 机构类别: 医疗/教育/党政机关/场馆/体育/政务服务中心
    specific_type: str = ""            # 具体类型: 医院/大学/法院/机关...
    # ---- 平台单位类型字典码（ts_customer_info，2026-09-20 新增）----
    # customer_func: 一级码 A政务/B场馆/C医疗/D党政/E教育（字典 client_dept_type）
    # children_func: 二级码，含义随一级码而异（字典 client_dept_type_<一级码>）：
    #   教育 A本科及以上/B专科/C普通非寄宿制/D普通寄宿制/E职业学校/F初等教育/
    #        G学前教育/H其他教育  ← DB37/T 2671-2019 的 8 个分档
    #   医疗 A一级/B二级/C三级；党政 A省级/B市级/C市级以下；场馆 A图书馆…E科技馆；
    #   政务 A市级及以上/B市级以下
    # 用途：定额对标按「一级类型 + 二级分档」选行（见 tools/energy_audit/dept_dict.py）
    unit_func: str = ""
    children_func: str = ""
    basic_situation: str = ""          # 单位基本情况概述（来自 ts_customer_info.basic_situation）
    contact_person: str = ""           # 联系人
    contact_phone: str = ""            # 联系电话
    # ---- 委托单位（2026-09-29 接线）----
    # 来源：ts_institution_project.commission_id → ts_commission_unit(unit_name, area_name)。
    # 口径（用户 2026-09-29 定）：**直接使用平台数据，不做质量过滤**；
    # 报告 1.1 委托句「有值写单位名、无值写"委托……对该单位"」（见 chapter-guides-1-4.md）。
    entrust_unit: str = ""             # 委托单位名称（平台登记值）
    entrust_unit_area: str = ""        # 委托单位所属地区
    entrust_person: str = ""           # 委托单位联系人（平台 commission_person）
    audit_start: str = ""              # 审计起始时间 ex: "2025年6月"
    audit_end: str = ""                # 审计结束时间 ex: "2025年7月"
    audit_period: str = ""             # 审计期 ex: "2025年1月—2026年9月"（audit_year）
    base_period: str = ""               # 基准期 ex: "2023年1月—2024年1月"（reference_year）
    data_start: str = ""               # 数据起始年份 ex: "2022-01-01"
    data_end: str = ""                 # 数据结束年份 ex: "2024-12-31"
    building_area: float = 0           # 总建筑面积 m²
    people_count: int = 0              # 用能人数/职工数
    beds_count: int = 0                # 床位数（医院用）
    # 用能人数口径分项（2026-09-22 新增）：平台把口径要素拆在 ts_institution_scene，
    # 医疗机构用能人数 = 在岗员工 + 编外人员 + 门诊人数 + 床位数（见 pg_collector._pg_people_count）。
    # 四个分项落盘是为了让 people_count 的来源可审计（不再出现"值 820 却标 PG"这种错标）。
    work_staff: int = 0                 # 在岗员工数量 — scene.work_staff
    logistics_staff: int = 0            # 编外人员数量 — scene.logistics_staff
    clinic_num: int = 0                 # 门诊人数 — scene.clinic_num
    flow_staff: int = 0                 # 流动人员数量 — scene.flow_staff（当前不计入用能人数口径）
    admin_affiliation: str = ""        # 行政归属 ex: "山东省卫生健康委员会"
    department_count: str = ""         # 内设机构/科室 ex: "23个临床科室、7个医技科室"
    project_manager: str = ""          # 审计项目负责人
    auditor: str = ""                  # 审计机构名称
    # ---- 审计机构信息（能源审计机构信息表数据源）----
    # 来源: ts_register_info（dept_name/address）；负责人/联系方式由用户提问提供，
    # 表内 contact/mobile 仅作提问预填参考（audit_org_*_hint）。
    audit_org_name: str = ""           # 审计机构名称 — ts_register_info.dept_name
    audit_org_address: str = ""        # 审计机构详细地址 — ts_register_info.address（缺失→向用户提问）
    audit_org_contact: str = ""        # 审计机构负责人（用户提问提供，不静默【待补充】）
    audit_org_phone: str = ""          # 审计机构联系方式（用户提问提供，不静默【待补充】）
    audit_org_contact_hint: str = ""   # ts_register_info.contact（提问预填参考）
    audit_org_phone_hint: str = ""     # ts_register_info.mobile（提问预填参考）
    report_date: str = ""              # 报告日期 ex: "2026年6月"
    province: str = "山东"             # 所在省份（用于规章检索与同类报告匹配）
    city: str = ""                     # 地市，如 烟台
    district: str = ""                 # 区县，如 芝罘 / 经济技术开发区
    district_id: str = ""              # 行政区划代码（ts_customer_info.district_id），
                                       # 如 370611；气候区判定首选依据（地址常不含城市名、city 常为空）


@dataclass
class BuildingInfo:
    """建筑信息 —— 对应 PG 表 ts_institution_build

    所有字段都对齐 ts_institution_build 表结构，新增字段均带默认值，
    保证对已有项目数据（缺少新字段）的向后兼容。
    """
    # ---- 基本信息 ----
    name: str                          # 建筑名称 — build_name
    address: str = ""                  # 地址 — address
    year: int = 0                      # 竣工年份 — build_year (int，保留兼容性)
    function: str = ""                 # 建筑功能 — build_func
    function_zoning: str = ""          # 建筑功能分区 — build_func_region
    other_function_zoning: str = ""    # 其他建筑功能分区 — other_build_func_region
    floors: str = ""                   # 层数描述 (合成字段：地上X层地下Y层)
    up_floor: int = 0                  # 地上层数 — up_floor
    down_floor: int = 0                # 地下层数 — down_floor
    height: str = ""                   # 建筑高度 — build_height (numeric 保留原字符串便于精度显示)
    orientation: str = ""              # 建筑朝向 — build_face
    area: float = 0                    # 建筑面积 m² — build_area
    use_area: float = 0                # 使用面积 m² — use_area
    cooling_area: float = 0            # 供冷面积 m² — cold_area
    heating_area: float = 0           # 供热面积 m² — heat_area
    cold_terminal_area: float = 0      # 供冷末端面积 m² — cold_terminal_area
    heat_terminal_area: float = 0      # 供热末端面积 m² — heat_terminal_area

    # ---- 建筑结构 ----
    structure: str = ""                # 结构形式 — stru_type
    other_structure: str = ""          # 其他结构形式 — other_stru_type
    wall_body_material: str = ""       # 外墙主体材料 — wallbody_thickness
    other_wall_body_material: str = "" # 其他外墙主体材料 — other_wallbody_thickness

    # ---- 围护结构（透明/不透明） ----
    window_type: str = ""              # 建筑透明维护结构 — wallwin_type
    other_window_type: str = ""        # 其他透明维护结构 — other_wallwin_type
    insulation: str = ""               # 外墙保温形式 — wallwarm_type
    other_insulation: str = ""         # 其他外墙保温形式 — other_wallwarm_type
    wall_material: str = ""            # 外墙保温材料 — warm_material
    other_warm: str = ""               # 其他保温材料 — other_warm
    warm_thickness: str = ""          # 外墙保温材料厚度 — warm_thickness
    warm_state: str = ""               # 外墙保温材料现状 — warm_state
    wall_insulation_change: int = 0    # 外墙保温审计周期内变化 — wallwarm_change (0:无 1:有)

    # ---- 屋面保温 ----
    roof_insulation: str = ""          # 有无屋面保温 — is_roomwarm ('有'/'无')
    roof_insulation_material: str = "" # 屋面保温材料 — roomwarm_material
    roof_insulation_thickness: str = "" # 屋面保温材料厚度 — roomwarm_thickness
    roof_insulation_state: str = ""    # 屋面保温材料现状 — roomwarm_state
    roof_insulation_change: int = 0    # 屋面保温审计周期内变化 — roomwarm_change (0:无 1:有)

    # ---- 遮阳 ----
    sunshade_type: str = ""            # 建筑遮阳形式 — build_sunshade ('外'/'中'/'内')
    sunshade_material: str = ""        # 遮阳材料 — sunshade_thickness
    sunshade_install: str = ""         # 遮阳安装形式 — sunshade_install

    # ---- 暖通空调 ----
    cooling_source: str = ""           # 夏季空调冷源 — cold_source
    cold_time: str = ""                # 供冷时间 — cold_time
    cold_date: str = ""                # 每日供冷时间 — cold_date (08:00:00~18:00:00)
    heating_source: str = ""           # 冬季供暖热源 — heat_source
    heat_time: str = ""                # 供暖时间 — heat_time
    heat_date: str = ""                # 每日供暖时间 — heart_date
    cooling_terminal: str = ""         # 夏季空调末端 — air_type
    heating_terminal: str = ""         # 冬季供暖末端 — heat_type

    # ---- 水系统 ----
    water_system: str = ""             # 建筑给水系统 — water_supply
    fire_system: str = ""              # 消防给水系统 — fire_water_supply
    hot_water: str = ""                # 生活热水系统 — hot_water_supply

    # ---- 运行/计量/监管 ----
    monitoring: str = ""               # 能耗在线监测系统 — energy_system ('有'/'无')
    storey_metrology: str = ""         # 楼层单独计量 — storey_metrology ('是'/'否')
    run_time: str = ""                 # 建筑运行时间 — build_run_time

    # ---- 使用期限 ----
    begin_date: str = ""               # 使用开始时间 — use_begin_date
    end_date: str = ""                 # 使用结束时间 — use_end_date

    # ---- 地下车库 ----
    garage: str = ""                   # 地下车库 — garage ('有'/'无')
    garage_area: float = 0             # 地下车库面积 m² — garage_area


@dataclass
class EnergyAnomaly:
    """平台登记的能耗数据异常（2026-10-13 接入）。

    来源：`ts_institution_energy_main.anomaly_status`（0 无异常 / 1 存在异常 / 2 异常已修改）
          + `ts_institution_energy_exception`（is_special=1 且 exception_desc 非空）。
    口径：只在 `is_special=1 且 desc 非空` 时落盘；`anomaly_status` 一并带出供参考，
          **不参与过滤**（实测命中记录基本是 2，=1 全库仅 18 条）。
    用途（用户 2026-10-13 定）：报告 5.2 的**异常说明**——
          `period_type == "year"` → 年际段后另起一段；`"month"` → 逐月段后另起一行；
          **只作异常说明，不算归因**（不突破「归因下沉三律」）。
    """
    period: str = ""            # exception_time 原文，如 "2023年" / "5月"
    period_type: str = ""       # "year" | "month"（按 period 是否含"月"判定）
    energy_name: str = ""       # 能源名（如 "电能" / "天然气" / "热力" / "汽油"）
    rate_value: Optional[float] = None   # 同比增长率数值（如 36.74，表示 36.74%）
    direction: str = ""         # "up" / "down"（取自 tittle 的"同比上升/下降率"）
    title: str = ""             # tittle 原文
    desc: str = ""              # exception_desc 原文（照录）
    desc_no_year: str = ""      # 去掉句首"YYYY年"前缀的版本（供报告侧优先取用，边界①）
    anomaly_status: int = 0     # 主表 anomaly_status（参考用）


@dataclass
class EnergyYearly:
    """年度能耗数据（含月度明细，可选）

    合署办公场景下：
      - 标准字段（electricity_kwh/water_m3/...）= 本单位实际用量（unit_total_value）
      - building_* 字段 = 整栋建筑的合署办公总量（building_total_value），仅合署时有值
    """
    year: int
    electricity_kwh: float = 0
    water_m3: float = 0
    natural_gas_m3: float = 0
    heating_energy_kwh: float = 0  # 供暖电耗 kWh（供暖循环泵/风机，dt=4 挂电记录；须从总电量剔除）
    heating_energy_heat_gj: float = 0
    # 5.3 三个指标的剔除项（2026-10-19 接入）：
    #   transport_electricity_kwh —— 交通能耗中的电（dt=5 且能源=电；5.3.2 须扣）
    #   construction_electricity_kwh —— 本年新建施工项目用电（scene.has_construction=1 时取）
    #   special_electricity_kwh / special_area_m2 —— 特殊设备（独立计量且有当年电量）的用电与配套面积
    transport_electricity_kwh: float = 0
    construction_electricity_kwh: float = 0
    special_electricity_kwh: float = 0
    special_area_m2: float = 0
    petrol_kg: float = 0
    diesel_kg: float = 0
    electricity_cost_wan: float = 0
    water_cost_wan: float = 0
    natural_gas_cost_wan: float = 0
    heating_cost_wan: float = 0
    petrol_cost_wan: float = 0
    diesel_cost_wan: float = 0
    # 月度明细（可选，用于生成逐月折线图）
    monthly_electricity_kwh: Optional[List[float]] = None
    monthly_water_m3: Optional[List[float]] = None
    monthly_natural_gas_m3: Optional[List[float]] = None
    # 逐月费用（元，dt=2 费用类记录的 period 明细；2026-09-28 接入，供附录2「7 列表」）
    # 此前只取费用年度值（*_cost_wan），附录2 因此写不出"逐月水费/电费/单价"，
    # 三个项目退化出三种不同格式；单价由 费用÷用量 现算，不单独建字段。
    monthly_electricity_cost: Optional[List[float]] = None
    monthly_water_cost: Optional[List[float]] = None
    monthly_natural_gas_cost: Optional[List[float]] = None
    monthly_heating_cost: Optional[List[float]] = None
    # 整栋建筑合署办公总量（合署场景下追溯用，非合署时为 0）
    building_electricity_kwh: float = 0
    building_water_m3: float = 0
    building_natural_gas_m3: float = 0
    building_heating_energy_heat_gj: float = 0
    building_petrol_kg: float = 0
    building_diesel_kg: float = 0
    # 当年各类能源折标煤系数（kgce/kWh、kgce/t、kgce/m³ 等），key 为能源类型
    coefficients: Dict[str, float] = field(default_factory=dict)
    # 各能源类型折标煤系数来源，例如 'PG' / 'Config' / 'Excel' / 'default'
    coefficient_sources: Dict[str, str] = field(default_factory=dict)
    # 平台登记的当年异常（2026-10-13 接入；期间为年份或月份，见 EnergyAnomaly）
    anomalies: List[EnergyAnomaly] = field(default_factory=list)


@dataclass
class EnergyMonthly:
    """逐月能耗（用于第5章图表）"""
    year: int
    month: int
    electricity_kwh: float = 0
    water_m3: float = 0
    natural_gas_m3: float = 0


@dataclass
class Equipment:
    """设备信息"""
    name: str                          # 设备名称
    category: str = ""                 # 分类: 空调/照明/电梯/热水器/厨房/变压器
    spec: str = ""                     # 规格/功率
    quantity: int = 0                  # 数量
    # 旧链路兼容的扁平附件 ID；新链路须与 img_fields 同时保存。
    img_ids: List[str] = field(default_factory=list)
    # 图片上传字段语义：保留 system_img / motor_img / pump_img 等来源字段，
    # 供第6章按“设备名+字段名”生成不串义的图注。旧 data.json 无此键时，
    # 下游自动退回 img_ids 兼容路径。
    img_fields: List[Dict[str, Any]] = field(default_factory=list)
    energy_rating: str = ""            # 能效等级
    usage_years: str = ""              # 使用年限
    location: str = ""                 # 所在位置
    remark: str = ""                   # 设备备注信息
    # 第6章用水判定（2026-10-21 接入）：
    #   config —— 动力设备「配置情况」（生活水泵：生活水箱 / 无负压生活水系统）
    #   device_air_id / device_air_name —— 其他设备（空调系统补水装置）对应的冷热源
    config: str = ""
    device_air_id: str = ""
    device_air_name: str = ""
    independent_metering: str = ""     # 独立计量 — is_metering（有/无/空=该表无此字段或未填）
    independent_metering_desc: str = ""  # 独立计量情况 — metering_desc
    independent_metering_ratio: str = ""  # 独立计量比例 — metering_ratio
    independent_metering_time: str = ""   # 独立计量时间 — metering_time
    frequency_control: str = ""        # 变频情况 — change_frequency（变频/定频/空）
    #   来源：ts_institution_device_td（输配水泵）/ power（电梯、水泵、风机）/ terminal（空调末端）。
    #   2026-09-28 接入：**0=明确登记定频（机会成立）、空=未登记（不得断言）**，两者必须分开。
    control_mode: str = ""             # 调节方式 — adjust_type（如"人工调节"）或 is_adjust 折算
    #   来源同上；支撑第7章 7.1 C 类「控制方式落后」。
    # 燃气用途判据（2026-10-16 接入，5.2.3 用气节段1 设备描述的唯一依据）：
    #   has_gas_use     特殊设备表（厨房/食堂）是否使用燃气：1 有 / 0 无 / None 未登记
    #   year_gas_value  蒸汽表：该设备年耗气量 m³      gas_value / fuel_value  冷热源表：耗气/耗油
    #   第6章路由：“吸收式/溴化锂/直燃”且 gas_value/fuel_value > 0 → 6.4。
    # 口径：**设备存在即写**，耗气量只用于判断当年度是否运行（None=未登记 与 0=明确为 0 必须分开）
    has_gas_use: Optional[int] = None
    year_gas_value: Optional[float] = None
    gas_value: Optional[float] = None
    fuel_value: Optional[float] = None
    # 特殊用能设备（ts_institution_device_special）剔除判据（2026-10-19 接入，5.3.1/5.3.2/5.3.3）：
    #   is_metering 已映射为 independent_metering（有/无）；
    #   year_electric=1 表示登记了年用电量，year_electric_value 为 [{"time":"YYYY-..","value":kWh}, …]；
    #   match_area 为该类设备的配套面积（扣面积时用；只在扣得掉电量时才扣）。
    year_electric: Optional[int] = None
    year_electric_value: Any = None
    match_area: Optional[float] = None
    # 变配电系统（ts_institution_device_substation + *_attached）：
    # 主记录描述配电室运行条件，变压器等附属设备必须保留结构化明细，
    # 不能压扁进 spec 字符串，否则设备数量、容量和安装年份会在落盘后不可恢复。
    substation_id: Optional[int] = None
    supply_area: str = ""
    cross_electricity: str = ""
    out_supply: str = ""
    meter_config: str = ""
    municipal_supply: str = ""
    load_rate: str = ""
    remaining_capacity: Any = None
    substation_remark: str = ""
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    # 第6章统一路由与特殊设备功率明细（2026-10-23 接入）：
    #   total_power_kw 仅在平台明确给出 power_unit 时可计算；
    #   power_components 保留四类设备数量与单机功率，供正文和审计追溯。
    other_device_name: str = ""
    server_num: Optional[float] = None
    server_power: Optional[float] = None
    network_num: Optional[float] = None
    network_power: Optional[float] = None
    storage_num: Optional[float] = None
    storage_power: Optional[float] = None
    air_num: Optional[float] = None
    air_power: Optional[float] = None
    power_unit: str = ""
    power_components: List[Dict[str, Any]] = field(default_factory=list)
    total_power_kw: Optional[float] = None
    routing_power_error: str = ""
    equipment_section_key: str = ""
    equipment_section_title: str = ""
    photo_section_key: str = ""
    photo_section_title: str = ""
    routing_reason: str = ""


@dataclass
class MeteringInfo:
    """计量器具信息"""
    has_monitoring_system: bool = False # 是否有能耗监测系统
    has_household_metering: bool = False# 是否有分户计量
    has_separate_metering: bool = False # 是否有设备单独计量（场景表独立计量电表）
    electric_meters: int = 0           # 电表数量
    water_meters: int = 0              # 水表数量
    gas_meters: int = 0                # 气表数量
    heat_meters: int = 0               # 热量表数量
    # 第7章 7.1.1 用水分支（2026-10-21 接入）：
    #   water_measured_depth —— 水表计量深度（仅总表/楼栋/楼层/科室…）
    #   water_kitchen_metering —— 厨房用水是否单独计量（energy_meter.kitchen_water）
    water_measured_depth: str = ""
    water_kitchen_metering: Optional[bool] = None
    # 电表分项计量按年份留档：{year: {meter_count, sub_metering, scenario}}
    # 审计期最后一年与最新年份可能不同，写作端按审计期取，禁静默二选一。
    electric_metering_by_year: Dict[str, Any] = field(default_factory=dict)
    independent_light_socket: bool = False   # 照明和插座用电独立计量
    independent_power: bool = False          # 动力用电独立计量
    independent_aircon: bool = False         # 空调用电独立计量
    independent_special: bool = False        # 特殊用电独立计量
    independent_other_special: str = ""      # 其他特殊用电独立计量描述
    independent_construction_elec: bool = False  # 施工用电独立计量
    independent_construction_water: bool = False # 施工用水独立计量
    has_shared_office: bool = False          # 是否合署办公 — ts_institution_scene.mode (1是/2否)
    has_household_payment: bool = False      # 分户缴费 — split_payment (1是/2否)
    install_position: int = 0                # 计量器具安装位置 1按要求/2未按要求
    position_reasonable: int = 0             # 位置合理性 1合理/2不合理
    metering_standard: int = 0               # 计量规范性 1非常规范/2一般规范/3不规范
    partition_payment: bool = False          # 分区缴费 — partition_payment (1是/2否)
    electric_pay_type: str = ""              # 电费收费方式
    cold_control_type: str = ""              # 空调控制方式 — ts_institution_scene.cold_control_type
    #   （2026-09-28 接入：支撑第7章 7.1 的 C 类机会问题「空调与供暖控制方式落后」；
    #    此前该列**整条链没人读**，全仓 grep 零命中）
    service_staff: str = ""                  # 第三方服务人员
    scene_desc: str = ""                     # 现场描述
    ledger_files: str = ""                   # 计量器具台账附件文件 id（逗号分隔，电/水表记录拼接）
    ledger_text: str = ""                    # 台账文档下载后提取的文字（enrich_meter_ledger 回填）
    record_attach_id: int = 0                # 运行记录抽样文件 id（scene.record_attach_id）
    aircon_staff_num: int = 0                # 空调系统运维人数（4.2 专职人员判定）
    light_staff_num: int = 0                 # 照明系统运维人数
    power_room_staff_num: int = 0            # 配电室运维人数
    # 供暖口径（2026-09-21 新增）：现场情况表 ts_institution_scene 的供暖字段，
    # 此前只用于拼"供暖信息未记录"提示、没有落进 data.json，报告里的热价只能凭蓝本记忆写。
    # 现在它们是 2.2 表2.1「冬季供暖热源」、5.2.3 用热分析、6.1.1 供暖段的**唯一来源**。
    heat_pay_type: str = ""                  # 供暖缴费方式 — heat_pay_type（按计量表缴费/按面积缴费）
    heat_price: Optional[float] = None       # 热价（元/GJ；按热量计量时的结算单价） — heat_price
    heat_measurement_price: Optional[float] = None  # 计量热价（元/GJ） — measurement_price
    heat_area: Optional[float] = None        # 供热面积 m² — heat_area
    heat_day: Optional[int] = None           # 供热天数（天） — heat_day


@dataclass
class SharedOfficeUnit:
    """合署办公单位 — ts_institution_scene_mode"""
    dept_name: str = ""                    # 合署单位名称 — mode_dept_name
    reason: str = ""                       # 合署原因 — mode_reason
    pay_type: str = ""                     # 缴费方式 — pay_type
    start_time: str = ""                   # 开始日期
    end_time: str = ""                     # 结束日期
    building: str = ""                     # 使用建筑/楼层 — mode_build
    area: float = 0                        # 使用面积 m² — mode_area
    ratio: float = 0                       # 使用建筑比例 — mode_ratio
    independent_metering: str = ""         # 独立计量 — is_metering（有/无/空）


SHARED_OFFICE_METERED = "有合署办公且实现了合办公单位独立计量"
SHARED_OFFICE_UNMETERED = "有合署办公，但未实现各办公单位独立计量"
_SHARED_OFFICE_YES = {"有", "是", "1", 1, True}


def _shared_office_unit_metered(val) -> bool:
    if val in _SHARED_OFFICE_YES:
        return True
    return str(val).strip() in {"有", "是", "1"} if val is not None else False


def shared_office_metering_sentence(has_shared_office, shared_offices=None) -> str:
    """第4章合署办公独立计量固定句。合署办公为否时返回空串，不回显「合署办公：是/否」。

    - 列表中只要有一个独立计量为是/有 → 有合署办公且实现了合办公单位独立计量
    - 全部为否/无（或无明细）→ 有合署办公，但未实现各办公单位独立计量
    """
    if not has_shared_office:
        return ""
    units = shared_offices or []
    for unit in units:
        val = unit.get("independent_metering") if isinstance(unit, dict) else getattr(
            unit, "independent_metering", ""
        )
        if _shared_office_unit_metered(val):
            return SHARED_OFFICE_METERED
    return SHARED_OFFICE_UNMETERED


@dataclass
class ManagementInfo:
    """能源管理信息（第3章）"""
    management_org: str = ""           # 管理机构描述
    management_policy: str = ""        # 管理方针
    management_goals: str = ""         # 管理目标
    honors: str = ""                   # 已获节能荣誉


@dataclass
class EnergySaving:
    """公共机构节能管理信息 —— 对应 PG 表 ts_institution_energy_saving

    所有字段对齐 ts_institution_energy_saving 表结构，0/1 标记字段沿用 int 类型
    （1:有/是, 0:无/否），与 BuildingInfo 中 wallwarm_change 等字段风格一致。
    """
    statistical_year: int = 0           # 统计年
    energy_management: Optional[int] = None  # 能源管理制度 (1:有, 0:无, None:未填写)
    energy_pain_points: str = ""        # 目前能源利用痛点
    management_files: str = ""          # 能源管理制度文件ID，多个以逗号分隔
    management_file_images: List[str] = field(default_factory=list)  # 管理制度附件解析下载后的图片本地路径
    has_awards: int = 0                 # 节能相关奖项 (1:有, 0:无)
    award_name: str = ""                # 节能奖项名称
    award_certificate: str = ""         # 节能奖项证明文件ID
    award_certificate_images: List[str] = field(default_factory=list)  # 奖项证明附件解析下载后的图片本地路径
    other_measures: str = ""            # 其他节能改造措施
    third_party_system: str = ""        # 第三方托管能源系统
    charging_pile: int = 0              # 充电桩 (1:有, 0:无)
    charging_settlement: str = ""       # 充电桩结算方式
    charging_installation: str = ""     # 充电桩安装方式
    third_party_outsource: int = 0      # 第三方外包用能系统 (1:有, 0:无)
    outsource_content: str = ""         # 第三方外包用能系统内容
    outsource_settlement: str = ""      # 第三方外包用能系统结算方式
    lighting_replacement: int = 0       # 照明灯具更换 (1:有, 0:无)
    ac_replacement: int = 0             # 空调设备更换 (1:有, 0:无)
    water_saving_fixture_replacement: int = 0  # 节水型卫生器具更换 (1:有, 0:无)
    central_ac_control: int = 0         # 中央空调系统增加集中控制 (1:有, 0:无)


@dataclass
class IndoorEnv:
    """室内环境检测"""
    test_date: str = ""
    test_conditions: str = ""
    rooms: List[dict] = field(default_factory=list)  # [{room, temp, humidity, co2, illumination, voc, pm25, remark}]


@dataclass
class TeamMember:
    """审计组人员（能源审计组人员名单）

    对齐 ts_project_audit_user（position 在报告"组内职务"列展示，
    存储审计负责人/审计联络人/成员等职务）。
    """
    role: str = ""                      # 组内职务 — position（审计负责人/审计联络人/成员）
    name: str = ""                      # 姓名
    education: str = ""                 # 学历 — degree
    certification: str = ""             # 所获资质 — qualifications
    major: str = ""                     # 专业


@dataclass
class CoopMember:
    """被审计单位配合人员（能源审计配合人员名单）

    对齐 ts_project_audited_user（group_position=组内职务，position=职务）。
    """
    role: str = ""                      # 组内职务 — group_position（组长/联系人等）
    dept: str = ""                      # 部门 — department
    name: str = ""                      # 姓名
    gender: str = ""                    # 性别 — sex
    position: str = ""                  # 职务 — position（主任/科长等）


@dataclass
class ImageItem:
    """项目照片（带分类，供报告章节路由与照片完整性校验）

    category 取 PHOTO_CATEGORIES 之一；空字符串表示未分类（兼容旧数据，报告兜底进第2章）。
    building_name：采集**行归属**（2026-10-13 新增）。建筑外观照填所属建筑名
    （来源 ts_institution_build.build_name，实测一栋一行、无共用组），供 2.2 逐栋配图
    自动归属；其余分类留空。不要用 caption 存归属——仿写链路
    （report_generator._add_image_with_caption）会把 caption 逐字当图注写进 docx。
    """
    path: str                          # 图片文件路径（本地绝对路径）
    category: str = ""                 # 照片分类（PHOTO_CATEGORIES）
    caption: str = ""                  # 图注（可选，报告内展示用）
    building_name: str = ""            # 行归属：建筑外观照=所属建筑名，其余留空
    file_id: Optional[int] = None      # ts_attachment.group_id，设备 img_ids 的稳定关联键
    sha256: str = ""                   # 物理文件内容 SHA-256；缺失时由采集/目录边界补齐

    def __post_init__(self):
        self.category = normalize_photo_category(self.category)


def _image_field(image: Union[ImageItem, dict], name: str, default: Any = None) -> Any:
    if isinstance(image, dict):
        return image.get(name, default)
    return getattr(image, name, default)


def image_identity(image: Union[ImageItem, dict]) -> str:
    """返回照片的稳定物理身份：附件 ID 优先，其次规范化绝对路径。"""
    file_id = _image_field(image, 'file_id')
    if file_id not in (None, ''):
        return f"file_id:{file_id}"
    path = str(_image_field(image, 'path', '') or '').strip()
    return f"path:{Path(path).resolve()}"


def image_sha256(image: Union[ImageItem, dict]) -> str:
    """计算照片文件内容的 SHA-256；文件不可读时返回空字符串。"""
    digest = str(_image_field(image, 'sha256', '') or '').strip()
    if digest:
        return digest
    path = Path(str(_image_field(image, 'path', '') or ''))
    if not path.is_file():
        return ''
    hasher = hashlib.sha256()
    try:
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
    except OSError:
        return ''
    return hasher.hexdigest()


def dedupe_image_items(images: List[ImageItem]) -> List[ImageItem]:
    """按物理身份去重，保留首条语义并补齐内容哈希。

    实测岚山区人民医院 219 条附件登记只对应 41 个物理路径。重复登记
    必须合并，但设备侧 ``img_ids`` 等数据库绑定保持原样，由后续目录层
    聚合到唯一候选上。
    """
    deduped: List[ImageItem] = []
    seen = set()
    for image in images:
        identity = image_identity(image)
        if identity in seen:
            continue
        seen.add(identity)
        if not image.sha256:
            image.sha256 = image_sha256(image)
        deduped.append(image)
    return deduped


# ============================================================
# 顶层项目数据
# ============================================================
@dataclass
class AuditProject:
    """完整项目数据"""
    project_id: str = ""               # 自动生成
    created_at: str = ""               # 创建时间
    updated_at: str = ""               # 最后更新时间
    base: ProjectBase = field(default_factory=ProjectBase)
    buildings: List[BuildingInfo] = field(default_factory=list)
    energy_yearly: List[EnergyYearly] = field(default_factory=list)
    energy_monthly: List[EnergyMonthly] = field(default_factory=list)
    equipment: List[Equipment] = field(default_factory=list)
    metering: MeteringInfo = field(default_factory=MeteringInfo)
    energy_meter: List[dict] = field(default_factory=list)  # 表具计量信息（ts_institution_energy_meter 原始记录，按 data_type/statistical_year 版本归一后）
    # 能源流向树（图5.1）：ts_energy_flow + ts_energy_flow_level 按客户拼成的嵌套树
    # [{'name':'电能','energy_code':'45','children':[{'name':'空调用电','children':[...]}]}, ...]
    # 2026-09-24 接入：图5.1 由"能源类型+设备类别推断"改为"库登记树优先"，缺失才降级。
    energy_flow_trees: List[dict] = field(default_factory=list)
    # 光伏/太阳能利用（第7章 7.1 C 类「可再生能源利用率低」的唯一依据）：
    # ts_institution_solar 按客户版本归一后的一行；字段含 has_solar_utilization /
    # pv_capacity / annual_generation / accept_pv_install / can_install_pv_carport /
    # roof_utilization_form。**表内有测试数据**，落盘前过 pg_collector 的测试数据闸，
    # 测试行不落（改记 missing），避免把"测试"写进报告结论。
    solar: Dict[str, Any] = field(default_factory=dict)
    # 附属用水登记（第5章 5.2.2 段1「用水构成句」的唯一依据）：
    #   {'greening': [{'irrigation_type','irrigation_source','year_water','desc'}],
    #    'other':    [{'water_system', ...}],
    #    'road':     [{'water_type', 'flush_cycle', ...}]}
    # 2026-10-15 接入：源头 ts_institution_water_greening / _other / _road，
    # 落盘前过"占位行/测试行"闸（见 pg_collector._water_field_ok）；三表无有效记录时为空 dict。
    water_aux: Dict[str, Any] = field(default_factory=dict)
    shared_offices: List[SharedOfficeUnit] = field(default_factory=list)  # 合署办公明细
    management: ManagementInfo = field(default_factory=ManagementInfo)
    energy_saving: List[EnergySaving] = field(default_factory=list)  # 节能管理信息（ts_institution_energy_saving）
    audit_team: List[TeamMember] = field(default_factory=list)      # 审计组人员（ts_project_audit_user）
    cooperation: List[CoopMember] = field(default_factory=list)     # 配合人员（ts_project_audited_user）
    indoor_env: IndoorEnv = field(default_factory=IndoorEnv)
    images: List[ImageItem] = field(default_factory=list)  # 照片列表（带分类）
    data_sources: Dict[str, str] = field(default_factory=dict)  # 字段→来源追溯
    indicators: Dict[str, Any] = field(default_factory=dict)   # 预计算能源审计指标
    _version: str = "1.3.0"            # 数据格式版本（images 升级为带分类的 ImageItem）


# ============================================================
# 数据来源解析辅助函数
# ============================================================

def resolve_with_source(field_name: str, *candidates) -> Tuple[Any, str]:
    """按优先级解析字段值并记录数据来源。

    candidates: [(source_name, value_or_dict), ...]
      - value 为 dict 时，从中取 field_name；
      - value 为其它类型时，直接使用。
    返回: (resolved_value, source_name)

    优先级规则：第一个非 None / 非空字符串 / 非 0 / 非 False 的值获胜；
    全部未命中时返回最后一个候选值，来源标记为 'default'。
    """
    for source_name, value in candidates:
        if isinstance(value, dict):
            v = value.get(field_name)
        else:
            v = value
        if v not in (None, '', 0, False):
            return v, source_name
    last_value = candidates[-1][1] if candidates else None
    if isinstance(last_value, dict):
        last_value = last_value.get(field_name)
    return last_value, 'default'


class SourceResolver:
    """辅助按优先级解析字段并统一记录数据来源。"""

    def __init__(self):
        self.values: Dict[str, Any] = {}
        self.sources: Dict[str, str] = {}

    def resolve(self, field_name: str, *candidates) -> Any:
        value, source = resolve_with_source(field_name, *candidates)
        self.values[field_name] = value
        self.sources[field_name] = source
        return value


def first_non_empty_source(*candidates) -> str:
    """返回第一个非空（非 None / 空字符串 / 0 / False / 空列表 / 空 dict）候选的来源名，
    全部未命中时返回 'default'。
    """
    for source_name, value in candidates:
        if value not in (None, '', 0, False) and value != [] and value != {}:
            return source_name
    return 'default'


def is_valid_coefficient(value) -> bool:
    """判断一个折标煤系数是否有效：非 None、非空字符串、可转为 float 且大于 0。"""
    if value is None or value == '':
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def total_building_area(buildings: List[dict]) -> float:
    """各建筑面积合计（m²），None / 缺字段按 0 计。

    采集（pg_collector）与质检（data_collection_cli）多处需要"建筑合计面积"，
    统一收敛到此，避免 sum(b.get('area', 0)) 散落多个文件。
    """
    return sum(b.get('area', 0) or 0 for b in buildings)


# ============================================================
# 持久化层
# ============================================================

_PROJECTS_ROOT = Path.home() / "projects" / "energy-audit"


def save_project(project: AuditProject) -> str:
    """保存项目数据到 ~/projects/energy-audit/<name>/data.json"""
    if not project.project_id:
        project.project_id = datetime.now().strftime("P%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:8]
    project.created_at = project.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    safe_name = project.base.unit_name or "unnamed"
    data_dir = _PROJECTS_ROOT / safe_name
    data_dir.mkdir(parents=True, exist_ok=True)

    data_path = data_dir / "data.json"
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(project), f, ensure_ascii=False, indent=2, default=str)

    print(f"[datacollection] 数据已保存: {data_path}")
    return str(data_path)


def _dict_to_dataclass(data: dict, cls: type) -> Any:
    """递归把 dict/list 转成对应 dataclass。"""
    if data is None:
        return cls() if not getattr(cls, '__origin__', None) else None

    # 裸 dict（原始记录，如 energy_meter / rooms 字段类型为 List[dict]）：原样透传
    if cls is dict:
        return data

    # 处理 List[SomeDataclass] / List[dict]
    origin = getattr(cls, '__origin__', None)
    if origin is list or origin is List:
        item_cls = cls.__args__[0]
        # List[dict]：原 dict 元素直接透传（勿按 dataclass 递归）
        if item_cls is dict:
            return list(data)
        result = []
        for item in data:
            # 兼容旧数据：images 为纯字符串路径 → 转为 ImageItem(path=...)
            if isinstance(item, str) and hasattr(item_cls, '__dataclass_fields__') \
                    and 'path' in item_cls.__dataclass_fields__:
                result.append(item_cls(path=item))
            else:
                result.append(_dict_to_dataclass(item, item_cls))
        return result

    # 普通 dataclass
    if isinstance(data, dict):
        field_types = {}
        for f in cls.__dataclass_fields__.values():
            field_types[f.name] = f.type

        kwargs = {}
        for k, v in data.items():
            if k not in field_types:
                continue
            ft = field_types[k]
            # 可选类型解包
            if getattr(ft, '__origin__', None) is Union:
                args = ft.__args__
                # Optional[X] = Union[X, None]
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    ft = non_none[0]
            # 是 dataclass 或容器则递归
            if hasattr(ft, '__dataclass_fields__'):
                kwargs[k] = _dict_to_dataclass(v, ft)
            elif getattr(ft, '__origin__', None) in (list, List):
                kwargs[k] = _dict_to_dataclass(v, ft)
            else:
                kwargs[k] = v
        return cls(**kwargs)

    return data


def load_project(unit_name: str) -> Optional[AuditProject]:
    """按单位名加载项目（递归还原 dataclass）"""
    data_path = _PROJECTS_ROOT / unit_name / "data.json"
    if not data_path.exists():
        return None

    with open(data_path, encoding='utf-8') as f:
        raw = json.load(f)

    return _dict_to_dataclass(raw, AuditProject)


def list_projects() -> List[dict]:
    """列出所有已保存的项目"""
    if not _PROJECTS_ROOT.exists():
        return []
    projects = []
    for p in _PROJECTS_ROOT.iterdir():
        data_file = p / "data.json"
        if data_file.exists():
            with open(data_file, encoding='utf-8') as f:
                raw = json.load(f)
            base = raw.get('base', {})
            projects.append({
                'name': base.get('unit_name', p.name),
                'short': base.get('unit_short', ''),
                'type': base.get('unit_type', ''),
                'updated': raw.get('updated_at', ''),
                'path': str(data_file),
            })
    return projects
