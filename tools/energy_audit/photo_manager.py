"""
照片管理

检查各章节需要的照片是否齐全，生成缺失清单。
支持两种输入：
- 项目数据模型（带分类照片，如 AuditProject.images 为 ImageItem 列表）→ 按 category 校验；
- report_data dict → 按章节路径（chapter2.images 等）校验。
"""

from typing import List, Dict, Tuple

# 各章节期望的照片（名称与 project_data.PHOTO_CATEGORIES 一一对应）
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
        ('缴费发票', '能源缴费发票照片（电/水/燃气/供暖，采集自 ts_institution_energy_invoice + invoice_image）', 'chapter5.images'),
    ],
    '第6章': [
        ('制冷设备', '冷水机组/多联机/冷却塔/水泵/换热器等（采集自设备分表 _img 列）', 'chapter6.images.cooling'),
        ('照明设备', '典型照明灯具照片', 'chapter6.images.lighting'),
        ('办公设备', '电脑/打印机等办公设备照片', 'chapter6.images.office'),
        ('其他用电设备', '电热水器/电梯等', 'chapter6.images.other_electric'),
        ('信息机房', '服务器/机柜/精密空调等', 'chapter6.images.computer_room'),
        ('厨房设备', '燃气灶具、消毒柜等', 'chapter6.images.kitchen'),
    ],
    '第7章': [
        ('节能改造示意', '改造前现状照片（可选对比）', 'chapter7.images'),
    ],
}


def check_photos(data) -> Tuple[bool, List[str]]:
    """检查各章节照片是否齐全。返回 (齐全?, 缺失清单)

    - data 为项目数据模型（有 .images 且元素带 .category）→ 按分类校验；
    - data 为 report_data dict → 按章节路径校验。
    """
    if hasattr(data, 'images'):
        return _check_by_category(data)
    return _check_by_path(data)


def _check_by_category(project) -> Tuple[bool, List[str]]:
    """按照片分类校验（项目数据模型带分类照片时使用）"""
    have = {getattr(img, 'category', '') or '' for img in project.images}
    # 第3章 管理文件/荣誉：energy_saving 附件图片（file_resolver 已下载）也算
    for es in getattr(project, 'energy_saving', None) or []:
        if (getattr(es, 'management_file_images', None) or getattr(es, 'award_certificate_images', None)):
            have.add('管理文件/荣誉')

    missing = []
    for chapter, requirements in PHOTO_REQUIREMENTS.items():
        for name, desc, _path_hint in requirements:
            if name not in have:
                missing.append(f"{chapter} → {name}（{desc}）")

    return (len(missing) == 0, missing)


def _check_by_path(report_data: dict) -> Tuple[bool, List[str]]:
    """按章节路径校验（report_data dict 时使用）"""
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


def get_photo_checklist(data) -> str:
    """生成照片需求清单"""
    ok, missing = check_photos(data)
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
