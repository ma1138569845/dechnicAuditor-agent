"""
照片管理

检查各章节需要的照片是否齐全，生成缺失清单。
"""

from typing import List, Dict, Tuple

# 各章节期望的照片
PHOTO_REQUIREMENTS = {
    '第2章': [
        ('建筑外观', '被审计单位建筑全景或主立面照片', 'chapter2.images'),
        ('各建筑外观', '每栋建筑单独外观照', 'chapter2.images'),
    ],
    '第3章': [
        ('管理文件/荣誉', '能源管理制度文件、节能荣誉证书等', 'chapter3.images'),
    ],
    '第4章': [
        ('计量器具', '电表、水表、气表等计量仪表照片', 'chapter4.images'),
    ],
    '第5章': [
        ('能耗账单', '电费、水费、燃气费账单示例', 'chapter5.images'),
    ],
    '第6章': [
        ('制冷设备', '冷水机组/多联机外机/分体空调等', 'chapter6.cooling.images'),
        ('照明设备', '典型照明灯具照片', 'chapter6.lighting.images'),
        ('变压器/配电', '变压器室、配电柜等', 'chapter6.transformer.images'),
        ('水泵/水箱', '生活水泵、消防水箱等', 'chapter6.water.images'),
        ('厨房设备', '燃气灶具、消毒柜等', 'chapter6.other_energy.images'),
    ],
    '第7章': [
        ('节能改造示意', '改造前现状照片（可选对比）', 'chapter7.images'),
    ],
}


def check_photos(report_data: dict) -> Tuple[bool, List[str]]:
    """检查各章节照片是否齐全。返回 (齐全?, 缺失清单)"""
    missing = []

    for chapter, requirements in PHOTO_REQUIREMENTS.items():
        for name, desc, path_hint in requirements:
            found = _find_photo(report_data, path_hint)
            if not found:
                missing.append(f"{chapter} → {name}（{desc}）")

    return (len(missing) == 0, missing)


def _find_photo(data: dict, path_hint: str) -> bool:
    """在 report_data 中递归查找是否有图片"""
    parts = path_hint.split('.')
    current = data

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part, {})
        elif isinstance(current, list):
            break  # 列表里的项不递归
        else:
            return False

    # 最终如果是一个列表且有元素，认为有图
    if isinstance(current, list) and current:
        return any(
            (isinstance(item, dict) and item.get('path')) or
            (isinstance(item, str) and item)
            for item in current
        )
    return False


def get_photo_checklist(report_data: dict) -> str:
    """生成照片需求清单"""
    ok, missing = check_photos(report_data)
    if ok:
        return "✅ 照片全部齐全"

    lines = [
        "=" * 45,
        "📷 照片需求检查 — 建议补充以下照片（共{}处）：".format(len(missing)),
        "=" * 45,
    ]
    seen = {}
    for m in missing:
        if m not in seen:
            seen[m] = 1
            lines.append(f"  · {m}")
    lines.append("=" * 45)
    return '\n'.join(lines)
