#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_report_photos.py — 报告照片归置器（第2/3/4/6章）

背景（2026-10-13）：照片从"采集产物"到"报告图表"这一段此前**没有任何工序**——
谁复制、放哪个目录、叫什么名、清单怎么写全靠人临场决定，于是出现三种后果：
  ① 副本目录两派（data/images/ 与 images/）；
  ② 文件名三派（平台 ID / 中文 / 英文）；
  ③ 岚山区人民医院 7 张建筑照一张没用进 2.2（归属信息在采集层被丢掉，只能人肉看图）。

本脚本把这一步工序化：**md 图注行仍是唯一编号源**；第2章按图注里的建筑名取图，
第4章按 `energy_meter[].device_img → images[].file_id` 识别电表/水表等计量器具，
第6章先用 `equipment[].img_fields[] → images[].file_id` 精确匹配上传字段，
再按文件名兜底；单字段图注为设备名，多字段图注为“设备名+字段名”。

覆盖范围（2026-10-21 扩到设备配图覆盖率硬校验）：
  - **第2章**：图 2.1（单位整体外观）+ 图 2.2…（逐栋建筑外观照，来源
    `proj.images[]` 的 `建筑外观` + `building_name`）；
  - **第3章**：图 3.1…（管理文件截图 / 荣誉证书，来源
    `es.management_file_images` / `es.award_certificate_images`）；选图规则 =
    数据库证书名称 + 年份 + 附件 ID 结构化绑定，名称/年份唯一匹配才配图；
    多候选时停止并告警，不再按池顺序猜测。荣誉候选再由 DeepSeek
    `deepseek-flash` 复核证书标题和受奖单位；默认视觉冲突仅告警并保留
    数据库确定性候选，`--certificate-policy strict` 才排除冲突图片。
  - **第4章**：图 4.1…（计量器具照片，来源 `proj.images[]` 的 `计量器具`）；
    按 `energy_meter[].device_img` + `data_type` 识别电表/水表/燃气表/热表，
    无台账映射时按文件名兜底；附件 ID 与文件路径双重去重。通用图注
    “计量器具照片”可承载同一图注下的多张照片，具体图注则按表种筛选。
  - **第6章**：`equipment[].img_fields[]` 中的每个附件 ID 都必须各有一条
    独立图注（单字段 `图6.N 设备名`；多字段 `图6.N 设备名+字段名`）；
    缺任何一条即返回告警码。信息机房与医疗设备按统一路由决定是否单列；
    生活水泵照片目标为 6.1 其他用电设备，燃气设备照片目标为 6.4。

分工：
  - 本脚本：装配**前**的三方一致（md 图注 ↔ 清单 ↔ 磁盘文件）+ 未引用照片提示；
    第3/4章照片**规则要求必给**，所以"有照片但 ch3.md/ch4.md 没写图注行"
    会按告警报出（rc=2）；
  - ea_docx_asserts.py 的 ch2_22_photos / ch3_photos / ch4_photos：
    装配**后**的成品一致（图注 ↔ 图）。

用法:
    python prepare_report_photos.py <项目名|项目目录> [--force] [--dry-run] [--quiet]
    python prepare_report_photos.py <项目名|项目目录> --catalog-only [--vision]
    python prepare_report_photos.py <项目名|项目目录> --prune {report,apply}

行为与退出码:
    0  正常（含"有照片未被引用"这类提示）
    1  输入缺失（项目目录 / data.json / chapter_md/ch2.md 任一不在）
    2  有告警（图注匹配不到照片，或有照片却没写图注，或有图片字段缺图注）
       ——已能写的条目仍会写

产物:
    <项目>/photo_catalog.json                写作前照片事实目录（--catalog-only）
    <项目>/data/images/<规范化文件名>         照片副本（清单引用的就是它）
    <项目>/report_images.json                 第2/3/4/6章照片条目重建（写前留 .bak；含来源元数据）
    <项目>/photo_vision_checks.json            第3章荣誉证书视觉核验缓存与核验记录
    <项目>/photo_finalization_status.json     本次归置是否仍有告警
    <项目>/photo_prune_report.json            孤立照片扫描/移动记录
    <项目>/_work/photo_trash/<时间>/           --prune apply 的可恢复回收区

约定（对应 2026-10-13 五项决策）:
    - 副本目录统一 `data/images/`，清单 src 写相对路径 `data/images/xxx.png`；
    - 图 2.1 → 分类 `单位整体外观`（无则第一张建筑照），图注沿用
      "图2.1 {单位简称}单位整体外观"；
    - 图 2.N（N≥2）→ 图注里的建筑名 → 该建筑的 `building_name` 照片，图注措辞
      "图2.N {楼名}总体外观"；**图数不要求等于栋数**（挑几张即可）；
    - 第4章 `图4.N 计量器具照片` → 按 `data.json.energy_meter[].device_img`
      精确关联；通用图注按附件池顺序连续插入，同一附件 ID 只插入一次；
    - 本章之外条目（图表、附录照片等）原样保留，本脚本不碰。
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def _load_photo_contract():
    """加载 repo 中的唯一分类契约；技能从 profile 或 repo 内运行都可用。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        target = parent / "tools" / "energy_audit" / "project_data.py"
        if not target.is_file():
            continue
        spec = importlib.util.spec_from_file_location(
            "prepare_report_photos_project_data",
            target,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return (
            module.PHOTO_CATEGORIES,
            module.normalize_photo_category,
            module.CHAPTER6_SECTIONS,
            module.chapter6_route_for_equipment,
            module.chapter6_water_aux_photo_items,
            module.equipment_photo_slots,
        )
    try:
        from tools.energy_audit.project_data import (  # type: ignore
            PHOTO_CATEGORIES,
            normalize_photo_category,
            CHAPTER6_SECTIONS,
            chapter6_route_for_equipment,
            chapter6_water_aux_photo_items,
            equipment_photo_slots,
        )
        return (
            PHOTO_CATEGORIES,
            normalize_photo_category,
            CHAPTER6_SECTIONS,
            chapter6_route_for_equipment,
            chapter6_water_aux_photo_items,
            equipment_photo_slots,
        )
    except ImportError as exc:
        raise ImportError("无法加载照片分类与第6章设备小节路由") from exc


(
    PHOTO_CATEGORIES,
    normalize_photo_category,
    CHAPTER6_SECTIONS,
    chapter6_route_for_equipment,
    chapter6_water_aux_photo_items,
    equipment_photo_slots,
) = _load_photo_contract()


def _load_photo_vision():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from photo_vision import (  # type: ignore
        DEFAULT_MODEL,
        inspect_photo,
        normalize_claim_text,
        verify_certificate,
        vision_cache_key,
    )
    return (
        DEFAULT_MODEL,
        inspect_photo,
        normalize_claim_text,
        verify_certificate,
        vision_cache_key,
    )


VISION_MODEL, inspect_photo, _normalize_claim_text, verify_certificate, vision_cache_key = \
    _load_photo_vision()
VISION_CHECKS_FILENAME = "photo_vision_checks.json"
FINALIZATION_STATUS_FILENAME = "photo_finalization_status.json"
PRUNE_REPORT_FILENAME = "photo_prune_report.json"


def _load_photo_catalog():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from photo_catalog import (  # type: ignore
        build_photo_catalog,
        write_photo_catalog,
    )
    return build_photo_catalog, write_photo_catalog


build_photo_catalog, write_photo_catalog = _load_photo_catalog()

CAP_RE = re.compile(r"^图([2346])\.(\d+)\s*(.+?)\s*$")
BUILDING_CAT = "建筑外观"
OVERALL_CAT = "单位整体外观"
METERING_CAT = "计量器具"
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
# 本脚本负责重建的图注前缀（其余条目原样保留）
MANAGED_PREFIXES = ("图2.", "图3.", "图4.", "图6.")
# 第4章：meter 表 data_type 与照片命名的既有口径
CH4_METER_TYPES = {
    1: ("electric", "电表"),
    2: ("water", "水表"),
    3: ("gas", "燃气表"),
    4: ("heat", "热表"),
}
CH4_TYPE_WORDS = {
    "electric": ("电表", "电能表"),
    "water": ("水表",),
    "gas": ("燃气表", "天然气表"),
    "heat": ("热表", "热量表"),
}
# 第6章：设备照片池（建筑外观/计量器具不参与设备配图）
CH6_DEVICE_CATS = {
    "制冷设备", "照明设备", "办公设备", "其他用电设备",
    "信息机房", "医疗设备", "特殊设备", "变压器/配电", "水泵/水箱", "厨房设备",
    "用水设施", "燃气设备",
}
assert CH6_DEVICE_CATS <= set(PHOTO_CATEGORIES)
STRICT_REVERSE_PHOTO_CATEGORIES = {"动力", "特殊设备"}
# 图注关键词 → 设备照片分类（文件名对不上时的兜底）
CH6_CAT_HINTS = (
    (("照明", "灯"), "照明设备"),
    (("办公", "电脑", "打印"), "办公设备"),
    ((
        "信息机房",
        "数据机房",
        "服务器",
        "网络设备",
        "存储设备",
        "数据中心",
        "信息中心",
    ), "信息机房"),
    (("医疗", "X射线", "CT", "摄影"), "医疗设备"),
    (("空调", "冷水", "冷却塔", "热泵"), "制冷设备"),
    (("变压器", "配电柜", "配电室", "开关柜"), "变压器/配电"),
    (("水泵", "水箱"), "水泵/水箱"),
    (("厨房", "燃气灶", "蒸柜", "消毒柜"), "厨房设备"),
    (("灌溉", "绿化", "用水设施"), "用水设施"),
    (("燃气锅炉", "燃气热水", "燃气蒸汽", "燃气设备"), "燃气设备"),
    (("电梯", "开水器", "热水器"), "其他用电设备"),
)
# 图注关键词 → 文件名关键词（用于同义词匹配，禁止按分类乱抓）
CH6_KEYWORDS = (
    ("冷水机组", ("冷水机组",)),
    ("空调", ("空调",)),
    ("水泵", ("水泵",)),
    ("冷却塔", ("冷却塔",)),
    ("平板灯", ("平板灯",)),
    ("吸顶灯", ("吸顶灯",)),
    ("灯管", ("灯管",)),
    ("荧光灯", ("荧光灯",)),
    ("筒灯", ("筒灯",)),
    ("电脑", ("电脑",)),
    ("打印", ("打印",)),
    ("热泵", ("热泵",)),
    ("热水器", ("热水器",)),
    ("医疗", ("X光", "CT", "医疗")),
    ("数据中心", ("数据中心", "信息中心", "信息机房", "数据机房", "服务器")),
    ("信息中心", ("数据中心", "信息中心", "信息机房", "数据机房", "服务器")),
)
CH6_GARBAGE_STEMS = {"image", "店铺"}
# 第3章：来源 → 图注关键词（照 chapter-guides-1-4.md「图片路由」节）
CH3_RULES = (
    ("award", "荣誉证书", ("荣誉", "奖", "证书", "称号", "授牌")),
    ("management", "管理文件", ("制度", "文件", "标识", "管理", "规定", "措施", "截图", "提示")),
)
# python-docx 可直接嵌入的格式（真实格式，不看扩展名）
EMBEDDABLE = {"png": ".png", "jpeg": ".jpg", "gif": ".gif", "bmp": ".bmp", "tiff": ".tif"}
"""实测（2026-10-13 岚山区人民医院）：平台附件里存在**扩展名骗人**的图片——
`建筑外观_急诊楼.png`/`建筑外观_行政后勤楼.png` 真实格式是 WebP，python-docx 抛
`UnrecognizedImageError` 直接让整个装配失败。故本脚本按**真实格式**落盘，非可嵌入
格式一律转成 PNG（有 Pillow 时），保证清单里的文件装配链一定吃得下。"""


def probe_format(path: str):
    """返回 (真实格式名, 可直接嵌入?)；无 Pillow 时按扩展名乐观处理。"""
    try:
        from PIL import Image
    except ImportError:
        return os.path.splitext(path)[1].lstrip(".").lower(), True
    try:
        with Image.open(path) as im:
            fmt = (im.format or "").lower()
    except Exception:  # noqa: BLE001
        return os.path.splitext(path)[1].lstrip(".").lower(), True
    return (fmt, fmt in EMBEDDABLE)


def save_as_png(src: str, dst: str):
    from PIL import Image
    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im.convert("RGBA").save(dst, "PNG")
        else:
            im.convert("RGB").save(dst, "PNG")


def _is_png(path: str) -> bool:
    """文件是否能按 PNG 打开（判断转换产物是否已就绪）。"""
    try:
        fmt, _ = probe_format(path)
        return fmt == "png"
    except Exception:  # noqa: BLE001
        return False


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit")


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (text or "").strip()) or "未命名"


def read_json(path: str, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, payload, *, backup: bool = True):
    """原子写入 JSON；覆盖前留备份，供人工核查或回滚。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if backup and target.is_file():
        shutil.copy2(target, target.with_name(target.name + ".bak"))
    temp = target.with_name(target.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(temp, target)


def parse_captions(md_path: str, chapter: str):
    """返回指定章的 [(图号 int, 图注全文, 说明文字)]，按 md 出现顺序。"""
    out = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            m = CAP_RE.match(line.strip())
            if m and m.group(1) == chapter:
                out.append((int(m.group(2)), line.strip(), m.group(3).strip()))
    return out


CHAPTER6_PREFIX = {
    "air_heating": "6.1",
    "lighting": "6.1",
    "office": "6.1",
    "information_room": "6.1",
    "medical_equipment": "6.1",
    "substation": "6.1",
    "other_energy": "6.1",
    "water_system": "6.2",
    "gas_system": "6.4",
}


def _chapter6_heading_key(title: str) -> str:
    text = re.sub(r"\s+", "", str(title or ""))
    rules = (
        ("information_room", ("信息机房", "数据中心")),
        ("medical_equipment", ("医疗设备",)),
        ("water_system", ("用水系统", "用水运行")),
        ("gas_system", ("燃气系统", "用燃气")),
        ("substation", ("变配电系统",)),
        ("lighting", ("照明系统",)),
        ("office", ("办公设备",)),
        ("air_heating", ("空调与供暖", "空调供暖")),
        ("other_energy", ("其他用电设备",)),
    )
    for key, words in rules:
        if any(word in text for word in words):
            return key
    return ""


def chapter6_section_label(key: str) -> str:
    section = CHAPTER6_SECTIONS.get(str(key or ""))
    if not section:
        return ""
    prefix = CHAPTER6_PREFIX.get(str(key or ""), "")
    return f"{prefix} {section['photo_title']}".strip()


def parse_caption_sections(md_path: str, chapter: str):
    """返回第6章图注及其所在系统小节：``(图号, 说明, 小节 key)``。"""
    if not md_path or not os.path.isfile(md_path):
        return []
    out = []
    section_key = ""
    with open(md_path, encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            line = raw.strip()
            heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if heading:
                section_key = _chapter6_heading_key(heading.group(1))
                continue
            match = CAP_RE.match(line)
            if match and match.group(1) == chapter:
                out.append((
                    int(match.group(2)),
                    match.group(3).strip(),
                    section_key,
                ))
    return out


def parse_md_device_names(md_path: str) -> set:
    """从第6章 Markdown 设备表抽取“设备名称”列。

    该集合只用于 Markdown 表内名称过滤；不能作为数据库动力设备、特殊设备的
    配图覆盖免检边界。
    """
    names, col = set(), None
    if not md_path or not os.path.isfile(md_path):
        return names
    with open(md_path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line.startswith("|"):
                col = None
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if "设备名称" in cells:
                col = cells.index("设备名称")
                continue
            if col is None or not cells or all(set(c) <= {"-", ":"} for c in cells):
                continue
            if col < len(cells) and cells[col] and cells[col] not in ("—", "-"):
                names.add(cells[col])
    return names


def _attachment_ids(value) -> list:
    if isinstance(value, (list, tuple, set)):
        raw = " ".join(str(v or "") for v in value)
    else:
        raw = str(value or "")
    return re.findall(r"\d+", raw)


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(str(path or "")))


def _sha256_file(path: str) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _image_row_for_source(images, source_path: str, file_id=None) -> dict:
    source_key = _path_key(source_path)
    for image in images or []:
        if _path_key(image.get("path")) == source_key:
            return image
    file_id = str(file_id or "").strip()
    if file_id:
        for image in images or []:
            if str(image.get("file_id") or "").strip() == file_id:
                return image
    return {}


def make_photo_entry(
    *,
    caption: str,
    destination: str,
    project_dir: str,
    source_path: str,
    images,
    kind: str,
    binding_ref: str,
    binding_label: str,
    file_id=None,
    category: str = "",
    verification: str = "unverified",
    section_route=None,
) -> dict:
    """Build a manifest entry while preserving the legacy caption/src contract."""
    image = _image_row_for_source(images, source_path, file_id=file_id)
    resolved_file_id = str(
        file_id if file_id not in (None, "") else image.get("file_id") or ""
    ).strip()
    source_abs = os.path.abspath(source_path)
    source_sha = str(image.get("sha256") or "").strip() or _sha256_file(source_abs)
    candidate_id = (
        f"file_id:{resolved_file_id}"
        if resolved_file_id
        else f"path:{Path(source_abs).resolve()}"
    )
    destination_abs = os.path.join(project_dir, destination.replace("/", os.sep))
    binding = {
        "ref": binding_ref,
        "label": binding_label,
    }
    for key in (
        "equipment_section_key",
        "equipment_section_title",
        "photo_section_key",
        "photo_section_title",
        "routing_reason",
    ):
        if section_route and str((section_route or {}).get(key) or "").strip():
            binding[key] = str(section_route[key]).strip()
    return {
        "caption": caption,
        "src": destination,
        "sha256": _sha256_file(destination_abs),
        "source": {
            "kind": kind,
            "candidate_id": candidate_id,
            "file_id": resolved_file_id,
            "source_path": source_abs,
            "source_sha256": source_sha,
            "category": category or str(image.get("category") or ""),
            "binding": binding,
            "selection_method": "file_id" if resolved_file_id else "path",
            "verification": verification,
        },
    }


def semantic_reuse_warnings(entries) -> list:
    """Warn when one physical source is reused under different captions."""
    by_source = {}
    for entry in entries or []:
        source = entry.get("source") or {}
        digest = str(source.get("source_sha256") or "").strip()
        caption = str(entry.get("caption") or "").strip()
        if not digest or not caption:
            continue
        by_source.setdefault(digest, [])
        if caption not in by_source[digest]:
            by_source[digest].append(caption)

    warnings = []
    for captions in by_source.values():
        if len(captions) > 1:
            warnings.append(
                "同一张源照片被分配给不同图注，存在语义错配风险："
                + " / ".join(captions)
            )
    return warnings


def prune_photo_orphans(project_dir: str | Path, *, apply: bool = False) -> dict:
    """Report or move unreferenced photos without touching referenced files."""
    root = Path(project_dir).resolve()
    images_dir = root / "data" / "images"
    manifest_path = root / "report_images.json"
    reasons = []
    if images_dir.is_symlink():
        reasons.append("data/images 是符号链接，拒绝扫描或移动其目标目录")
    manifest = read_json(manifest_path, None) if manifest_path.is_file() else None
    manifest_valid = (
        isinstance(manifest, dict)
        and isinstance(manifest.get("images"), list)
    )
    if not manifest_valid:
        manifest = {"images": []}

    referenced = set()
    for entry in manifest.get("images") or []:
        src = str((entry or {}).get("src") or "").strip()
        if not src:
            continue
        candidate = Path(src)
        if not candidate.is_absolute():
            candidate = root / candidate
        referenced.add(candidate.resolve())

    scanned = []
    if images_dir.is_dir() and not images_dir.is_symlink():
        for current, dirnames, filenames in os.walk(images_dir):
            current_path = Path(current)
            dirnames[:] = [
                name for name in dirnames
                if not (current_path / name).is_symlink()
            ]
            for name in filenames:
                path = current_path / name
                if path.is_symlink() or not path.is_file():
                    continue
                scanned.append(path.resolve())

    orphans = sorted(path for path in scanned if path not in referenced)
    finalization = read_json(root / FINALIZATION_STATUS_FILENAME, {})
    if not manifest_valid:
        reasons.append("report_images.json 缺失或无效，无法判断哪些照片已被引用")
    if (
        isinstance(finalization, dict)
        and finalization.get("clean") is False
    ):
        reasons.append("上次照片归置仍有告警，需先清理告警并重跑归置")
    blocked = bool(apply and reasons)
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "apply" if apply else "report",
        "blocked": blocked,
        "reason": "；".join(reasons),
        "referenced": [
            os.path.relpath(path, root).replace(os.sep, "/")
            for path in sorted(referenced)
        ],
        "orphans": [
            os.path.relpath(path, root).replace(os.sep, "/")
            for path in orphans
        ],
        "moved": [],
        "trash_dir": "",
    }

    if apply and orphans and not blocked:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        trash_dir = root / "_work" / "photo_trash" / stamp
        for source in orphans:
            relative = source.relative_to(images_dir)
            destination = trash_dir / "data" / "images" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            result["moved"].append(
                os.path.relpath(destination, root).replace(os.sep, "/")
            )
        result["trash_dir"] = str(trash_dir)

    (root / PRUNE_REPORT_FILENAME).write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def build_ch3_pools(saving, images=None):
    """构建第3章结构化照片池，保留证书标题、年份和附件 ID。"""
    image_by_path = {
        _path_key(im.get("path")): im
        for im in (images or [])
        if im.get("path")
    }
    image_by_id = {
        str(im.get("file_id") or ""): im
        for im in (images or [])
        if im.get("file_id")
    }
    pools = {"management": [], "award": []}
    seen = set()

    def add(kind, path, *, title="", year=0, file_id=""):
        path = str(path or "").strip()
        if not path:
            return
        key = (kind, _path_key(path))
        if key in seen:
            return
        seen.add(key)
        pools[kind].append({
            "kind": kind,
            "path": path,
            "file_id": str(file_id or ""),
            "title": str(title or os.path.splitext(os.path.basename(path))[0]),
            "year": int(year or 0),
        })

    for es in saving or []:
        year = es.get("statistical_year") or 0
        award_title = str(es.get("award_name") or "").strip()
        award_ids = _attachment_ids(es.get("award_certificate"))
        award_paths = [str(p) for p in (es.get("award_certificate_images") or []) if p]
        if not award_paths:
            award_paths = [
                image_by_id[fid].get("path")
                for fid in award_ids
                if fid in image_by_id and image_by_id[fid].get("path")
            ]
        for idx, path in enumerate(award_paths):
            image = image_by_path.get(_path_key(path)) or {}
            fid = (
                image.get("file_id")
                or (award_ids[idx] if idx < len(award_ids) else "")
            )
            add("award", path, title=award_title, year=year, file_id=fid)

        management_ids = _attachment_ids(es.get("management_files"))
        management_paths = [
            str(p) for p in (es.get("management_file_images") or []) if p
        ]
        if not management_paths:
            management_paths = [
                image_by_id[fid].get("path")
                for fid in management_ids
                if fid in image_by_id and image_by_id[fid].get("path")
            ]
        for idx, path in enumerate(management_paths):
            image = image_by_path.get(_path_key(path)) or {}
            fid = (
                image.get("file_id")
                or (management_ids[idx] if idx < len(management_ids) else "")
            )
            add("management", path, file_id=fid)
    return pools


def _ch3_caption_kind(desc: str) -> str:
    for kind, _label, keys in CH3_RULES:
        if any(key in desc for key in keys):
            return kind
    return ""


def _ch3_candidates(desc: str, pools: dict):
    requested_kind = _ch3_caption_kind(desc)
    candidates = []
    for kind in (("management", "award") if not requested_kind else (requested_kind,)):
        for item in pools.get(kind) or []:
            record = (
                dict(item)
                if isinstance(item, dict)
                else {
                    "kind": kind,
                    "path": str(item),
                    "file_id": "",
                    "title": os.path.splitext(os.path.basename(str(item)))[0],
                    "year": 0,
                }
            )
            record.setdefault("kind", kind)
            candidates.append(record)
    return candidates


def select_ch3_candidate(desc: str, pools: dict, used: set):
    """选图时优先精确标题/文件名；多候选且无法唯一匹配时返回 None。"""
    candidates = _ch3_candidates(desc, pools)

    desc_key = _normalize_claim_text(desc)
    exact = []
    for record in candidates:
        title_key = _normalize_claim_text(record.get("title"))
        stem_key = _normalize_claim_text(
            os.path.splitext(os.path.basename(str(record.get("path") or "")))[0]
        )
        if (title_key and (title_key in desc_key or desc_key in title_key)) or \
                (stem_key and (stem_key in desc_key or desc_key in stem_key)):
            exact.append(record)

    if exact:
        desc_years = {int(y) for y in re.findall(r"(?:19|20)\d{2}", desc)}
        if desc_years:
            year_matched = [
                record for record in exact
                if int(record.get("year") or 0) in desc_years
            ]
            if year_matched:
                exact = year_matched

        unused_exact = [
            record for record in exact
            if str(record.get("path") or "") not in used
        ]
        if len(unused_exact) > 1:
            return None
        if unused_exact:
            return unused_exact[0]
        # 已有精确候选但均已使用，不回退到其他证书，避免图注与内容错位。
        return None

    unused = [
        record for record in candidates
        if str(record.get("path") or "") not in used
    ]
    if len(unused) == 1:
        return unused[0]
    return None


def pick_ch3_photo(desc: str, pools: dict, used: set):
    """返回选中记录；不会在多个证书之间按顺序猜测。"""
    selected = select_ch3_candidate(desc, pools, used)
    if not selected:
        return "", "", None
    return selected["path"], selected["kind"], selected


def _meter_type_from_text(text: str) -> tuple:
    """按文件名/图注识别计量器具表种；识别不到时返回通用标签。"""
    raw = str(text or "")
    for kind, words in CH4_TYPE_WORDS.items():
        if any(word in raw for word in words):
            label = next(label for k, label in CH4_METER_TYPES.values() if k == kind)
            return kind, label
    return "", METERING_CAT


def metering_photos(images, energy_meter=None) -> list:
    """返回第4章可用照片池；按附件 ID 优先、路径兜底去重。

    附件 ID 是平台侧的稳定关联键。实测同一电表照片会在 `images[]` 中出现两次，
    若只按路径去重，路径写法稍有差异仍会重复插图；因此两把键都保留。
    """
    kind_by_id = {}
    for row in energy_meter or []:
        fid = str((row or {}).get("device_img") or "").strip()
        if not fid:
            continue
        try:
            data_type = int((row or {}).get("data_type"))
        except (TypeError, ValueError):
            data_type = None
        if data_type in CH4_METER_TYPES:
            kind, label = CH4_METER_TYPES[data_type]
            kind_by_id.setdefault(fid, (kind, label))

    out, seen = [], set()
    for im in images or []:
        if str((im or {}).get("category") or "").strip() != METERING_CAT:
            continue
        src = str((im or {}).get("path") or "").strip()
        if not src or not os.path.isfile(src):
            continue
        fid = str((im or {}).get("file_id") or "").strip()
        key = f"id:{fid}" if fid else "path:" + os.path.normcase(os.path.abspath(src))
        if key in seen:
            continue
        seen.add(key)
        kind, label = kind_by_id.get(
            fid, _meter_type_from_text(os.path.splitext(os.path.basename(src))[0])
        )
        out.append({"key": key, "src": src, "kind": kind, "label": label})
    return out


def pick_ch4_photos(desc: str, photos, used: set) -> list:
    """按图注选第4章照片；未写表种时取全部未用照片（支持一注多图）。"""
    hits = []
    for kind, words in CH4_TYPE_WORDS.items():
        positions = [desc.find(word) for word in words if word in desc]
        if positions:
            hits.append((min(positions), kind))
    requested = [kind for _, kind in sorted(hits)]

    if requested:
        matched = [p for p in photos if p.get("kind") in requested]
        out = [p for p in matched if p["key"] not in used]
        return out or matched
    return [p for p in photos if p["key"] not in used] or list(photos)


def _photo_name_key(text) -> str:
    """设备名/图注归一：忽略空白、斜杠和常用分隔符。"""
    return re.sub(
        r"[\s/／\\、，,。.；;：:（）()\-—_]+",
        "",
        str(text or ""),
    ).lower()


def _ch6_photo_contracts(equipment) -> list:
    """设备图片附件 → 每个附件 ID 一条独立图注契约。"""
    contracts = []
    for eq in equipment or []:
        for slot in equipment_photo_slots(eq):
            contracts.append({
                "equipment": eq,
                "name": slot["name"],
                "category": slot["category"],
                "field": slot["field"],
                "field_label": slot["field_label"],
                "caption_label": slot["caption_label"],
                "file_id": slot["file_id"],
                "attachment_index": slot["attachment_index"],
                "ids": [slot["file_id"]],
                "image_source_ref": slot["image_source_ref"],
            })
    return contracts


def _route_chapter6_equipment(equipment, base: dict) -> list:
    """照片工序按同一路由契约重算小节，兼容未带路由的旧 data.json。"""
    routed = []
    for item in equipment or []:
        record = dict(item)
        record.update(chapter6_route_for_equipment(
            record,
            unit_func=str((base or {}).get("unit_func") or ""),
            children_func=str((base or {}).get("children_func") or ""),
            institution_category=str(
                (base or {}).get("institution_category") or ""
            ),
            unit_name=str((base or {}).get("unit_name") or ""),
        ))
        routed.append(record)
    return routed


def _images_by_file_id(images) -> dict:
    out = {}
    for im in images or []:
        fid = str(im.get("file_id") or "").strip()
        if fid:
            out[fid] = im
    return out


def equipment_caption_coverage(
    equipment,
    captions,
    images=None,
    table_names=None,
) -> dict:
    """反向检查登记附件所需的图注及本地文件，两个结果独立返回。"""
    remaining_caption_keys = [
        _photo_name_key(desc)
        for _, _, desc in captions or []
    ]
    available_ids = set(_images_by_file_id(images or []))
    table_keys = [
        _photo_name_key(name)
        for name in (table_names or [])
    ]
    missing_captions = []
    missing_local_files = []

    for contract in _ch6_photo_contracts(equipment):
        name_key = _photo_name_key(contract["name"])
        file_id = str(contract.get("file_id") or "").strip()
        if not name_key or not file_id:
            continue

        strict_reverse = (
            contract["category"] in STRICT_REVERSE_PHOTO_CATEGORIES
            or contract["image_source_ref"].startswith("water_aux.")
        )
        if (
            not strict_reverse
            and table_keys
            and not any(
                name_key == table_key
                or name_key in table_key
                or table_key in name_key
                for table_key in table_keys
            )
        ):
            continue

        caption_label = contract["caption_label"]
        caption_key = _photo_name_key(caption_label)
        legacy_caption = contract["field"] == "img_ids"
        caption_index = next((
            index
            for index, current_key in enumerate(remaining_caption_keys)
            if caption_key == current_key
            or (
                legacy_caption
                and caption_key
                and current_key
                and (
                    caption_key in current_key
                    or current_key in caption_key
                )
            )
        ), None)
        if caption_index is None:
            missing_captions.append(caption_label)
        else:
            remaining_caption_keys.pop(caption_index)

        if file_id not in available_ids:
            missing_local_files.append(caption_label)

    return {
        "missing_captions": missing_captions,
        "missing_local_files": missing_local_files,
    }


def equipment_caption_gaps(equipment, captions, images=None, table_names=None) -> list:
    """兼容旧调用：只返回缺少图注的槽位。"""
    return equipment_caption_coverage(
        equipment,
        captions,
        images,
        table_names=table_names,
    )["missing_captions"]


def equipment_caption_section_warnings(
    equipment,
    captions,
    sections,
    *,
    unit_func: str = "",
    children_func: str = "",
    institution_category: str = "",
    unit_name: str = "",
) -> list:
    """告警第6章照片是否放在路由指定的系统小节。"""
    actual_by_num = {
        int(num): str(section or "")
        for num, _desc, section in sections or []
    }
    caption_text_by_num = {
        int(num): str(caption or "")
        for num, caption, _desc in captions or []
    }
    warnings = []
    consumed_caption_indexes = set()
    for eq in equipment or []:
        name_key = re.sub(r"\s+", "", str(eq.get("name") or ""))
        if not name_key:
            continue
        caption_index = next((
            index
            for index, (_num, _caption, desc) in enumerate(captions or [])
            if index not in consumed_caption_indexes
            and name_key in re.sub(r"\s+", "", str(desc or ""))
        ), None)
        if caption_index is None:
            continue
        consumed_caption_indexes.add(caption_index)
        caption_num = int(captions[caption_index][0])
        route = {
            key: str(eq.get(key) or "").strip()
            for key in (
                "equipment_section_key",
                "equipment_section_title",
                "photo_section_key",
                "photo_section_title",
                "routing_reason",
            )
        }
        if not route["photo_section_key"]:
            route = chapter6_route_for_equipment(
                eq,
                unit_func=unit_func,
                children_func=children_func,
                institution_category=institution_category,
                unit_name=unit_name,
            )
        expected_key = str(route.get("photo_section_key") or "")
        actual_key = actual_by_num.get(caption_num, "")
        if not actual_key or not expected_key or actual_key == expected_key:
            continue
        actual_label = (
            chapter6_section_label(actual_key)
            or "未识别系统小节"
        )
        expected_label = (
            chapter6_section_label(expected_key)
            or str(route.get("photo_section_title") or expected_key)
        )
        warnings.append(
            f"{caption_text_by_num.get(caption_num, f'图6.{caption_num}')}："
            f"照片当前放在 {actual_label}，应在 {expected_label}"
            f"（路由依据：{route.get('routing_reason') or 'equipment_route'}）"
        )
    return warnings


def pick_ch6_photo_details(desc: str, images, used: set, equipment=None):
    """第6章设备照：字段图注 → 对应上传字段的 file_id。

    优先精确命中“设备名+字段名”，再兼容旧图注“设备名”。同名图注
    按附件顺序逐条消费第一张尚未使用的可用照片；文件名匹配只作旧数据兜底。
    """
    key = re.sub(r"\s+", "", desc or "")
    if not key:
        return {}
    pool = [(im, str(im.get("path") or "")) for im in images
            if normalize_photo_category(im.get("category")) in CH6_DEVICE_CATS]
    by_file_id = _images_by_file_id(images)

    key_desc = _photo_name_key(desc)
    contracts = _ch6_photo_contracts(equipment)
    exact = [
        item for item in contracts
        if _photo_name_key(item["caption_label"]) == key_desc
    ]
    legacy = [
        item for item in contracts
        if item["field"] == "img_ids"
        and _photo_name_key(item["name"]) == key_desc
    ]
    matched = sorted(
        exact or legacy,
        key=lambda item: int(item.get("attachment_index") or 0),
    )
    for contract in matched:
        for fid in contract["ids"]:
            im = by_file_id.get(fid)
            p = str((im or {}).get("path") or "")
            if not p or not os.path.isfile(p):
                continue
            if p not in used:
                route = {
                    key: str(contract["equipment"].get(key) or "").strip()
                    for key in (
                        "equipment_section_key",
                        "equipment_section_title",
                        "photo_section_key",
                        "photo_section_title",
                        "routing_reason",
                    )
                }
                return {
                    "src": p,
                    "file_id": fid,
                    "field": contract["field"],
                    "field_label": contract["field_label"],
                    "caption_label": contract["caption_label"],
                    "binding_ref": (
                        f"{contract['image_source_ref']}.img_fields[{contract['field']}]"
                        if contract["field"] != "img_ids"
                        else f"{contract['image_source_ref']}.img_ids"
                    ),
                    "section_route": route,
                }

    def _first(match):
        for im, p in pool:
            stem = _stem(p)
            if stem in CH6_GARBAGE_STEMS or stem.startswith("微信图片"):
                continue
            if not match(im, p):
                continue
            if not os.path.isfile(p):
                continue
            if p not in used:
                return p
        return ""

    def _stem(p):
        return re.sub(r"\s+", "", os.path.splitext(os.path.basename(p))[0])

    hit = _first(lambda im, p: _stem(p) == key)          # ① 主干完全相同
    if hit:
        return {"src": hit}
    hit = _first(lambda im, p: _stem(p) and (key in _stem(p) or _stem(p) in key))
    if hit:                                              # ② 互相包含
        return {"src": hit}
    for cap_kw, img_kws in CH6_KEYWORDS:                # ③ 同义词关键词（不做分类兜底）
        if cap_kw in key:
            hit = _first(lambda im, p, ks=img_kws: any(k in _stem(p) for k in ks))
            if hit:
                return {"src": hit}
    return {}


def pick_ch6_photo(desc: str, images, used: set, equipment=None):
    """兼容旧调用：仅返回选中的源文件路径。"""
    return str((pick_ch6_photo_details(desc, images, used, equipment) or {}).get("src") or "")


def match_building(desc: str, buildings):
    """从图注说明里找建筑名（最长优先，避免"门诊楼"命中"门诊病房综合楼"的部分串）。"""
    for name in sorted([b for b in buildings if b], key=len, reverse=True):
        if name in desc:
            return name
    return ""


def pick_photo(images, category: str, building: str = ""):
    """按分类（+建筑名）选一张照片；命中多个取第一个。"""
    category = normalize_photo_category(category)
    for im in images:
        if normalize_photo_category(im.get("category")) != category:
            continue
        if building and (im.get("building_name") or "").strip() != building:
            continue
        p = str(im.get("path") or "")
        if p and os.path.isfile(p):
            return p
    return ""


def place(project_dir: str, src: str, stem: str, force: bool, copy_cache: dict, say):
    """把 src 复制为 <项目>/data/images/<stem>.<ext>，返回相对路径。

    同一运行内**同一用途+同一内容**只落一份（缓存键 = 用途+内容指纹）；同名不同
    内容时默认加 _2 后缀，--force 则覆盖。

    注意：不同用途即使内容相同也各落一份——实测出现过"单位整体外观"与"门诊楼
    建筑外观"在平台里注册成同一张图，若跨用途复用文件名，图注与文件名会串义。
    扩展名按**真实格式**给（见 probe_format），非可嵌入格式转 PNG。
    """
    src_ext = os.path.splitext(src)[1].lower()
    real_fmt, embeddable = probe_format(src)
    ext = EMBEDDABLE.get(real_fmt) if embeddable else ".png"
    if src_ext not in IMG_EXT and real_fmt not in EMBEDDABLE:
        say(f"  ⚠️ 跳过非常规图片：{os.path.basename(src)}（真实格式 {real_fmt or '未知'}）")
        return ""
    if not embeddable:
        say(f"  ↻ 格式转换: {os.path.basename(src)} 真实格式 {real_fmt} → PNG（装配链不吃 WebP）")
    digest = sha1(src)
    cache_key = (safe_name(stem), digest, ext)
    if cache_key in copy_cache:
        return copy_cache[cache_key]
    img_dir = os.path.join(project_dir, "data", "images")
    os.makedirs(img_dir, exist_ok=True)
    dst = os.path.join(img_dir, f"{cache_key[0]}{ext}")
    n = 2
    if embeddable:
        while os.path.isfile(dst) and sha1(dst) != digest:
            if force:
                break
            dst = os.path.join(img_dir, f"{cache_key[0]}_{n}{ext}")
            n += 1
        need_write = (not os.path.isfile(dst)) or sha1(dst) != digest
    else:
        # 转换分支：目标必须是"真 PNG"，用能否按 PNG 打开判定，**不能**与源哈希比对
        # （转换后的字节必然与源不同，拿源指纹比对会误判成"已存在、无需写"）。
        dst_ok = os.path.isfile(dst) and _is_png(dst)
        need_write = force or not dst_ok
    if need_write:
        if embeddable:
            shutil.copy2(src, dst)
            say(f"  + 复制照片: {os.path.basename(dst)}")
        else:
            try:
                save_as_png(src, dst)
                if not _is_png(dst):
                    say(f"  ⚠️ 转换结果不是 PNG，已跳过: {os.path.basename(dst)}")
                    return ""
                say(f"  + 复制照片（已转 PNG）: {os.path.basename(dst)}")
            except Exception as exc:  # noqa: BLE001
                say(f"  ⚠️ 格式转换失败 {os.path.basename(src)}: {exc}")
                return ""
    rel = os.path.relpath(dst, project_dir).replace(os.sep, "/")
    copy_cache[cache_key] = rel
    return rel


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="报告照片归置器（第2章建筑外观照 / 第3章管理文件·荣誉证书 / 第4章计量器具照 / 第6章设备照）")
    ap.add_argument("project", help="项目名（~/projects/energy-audit/<项目名>）或项目目录")
    ap.add_argument("--force", action="store_true", help="同名不同内容时覆盖既有副本/清单")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不复制、不写清单")
    ap.add_argument("--quiet", action="store_true", help="只在告警时输出")
    ap.add_argument(
        "--catalog-only",
        action="store_true",
        help="写作前只生成 photo_catalog.json，不要求 chapter_md/ch2.md",
    )
    ap.add_argument(
        "--vision",
        action="store_true",
        help="配合 --catalog-only，用 DeepSeek 提取图片可见事实（失败不阻断）",
    )
    ap.add_argument(
        "--prune",
        choices=("report", "apply"),
        help=(
            "孤立照片处理：report=只报告；apply=移动到 "
            "<项目>/_work/photo_trash/<时间>/"
        ),
    )
    ap.add_argument(
        "--certificate-policy",
        choices=("review", "strict"),
        default="review",
        help=(
            "荣誉证书视觉冲突处理：review=保留数据库候选并告警（默认）；"
            "strict=排除视觉冲突图片"
        ),
    )
    args = ap.parse_args(argv)

    def say(*a):
        if not args.quiet:
            print(*a)

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在: {args.project}（查找根: {projects_root()}）")
        return 1
    if args.prune:
        if args.prune == "apply" and args.dry_run:
            say("[dry-run] 清理只生成报告，不移动文件")
        result = prune_photo_orphans(
            pdir,
            apply=args.prune == "apply" and not args.dry_run,
        )
        if result["blocked"]:
            print(f"[阻断] {result['reason']}")
            print(f"[报告] 仍可在 {PRUNE_REPORT_FILENAME} 查看孤立文件清单")
            return 2
        say(
            f"[照片清理] 引用 {len(result['referenced'])}，"
            f"孤立 {len(result['orphans'])}，移动 {len(result['moved'])}"
        )
        if result["trash_dir"]:
            say(f"  回收目录：{result['trash_dir']}")
        return 0

    data_path = os.path.join(pdir, "data.json")
    md2_path = os.path.join(pdir, "chapter_md", "ch2.md")
    md3_path = os.path.join(pdir, "chapter_md", "ch3.md")
    md4_path = os.path.join(pdir, "chapter_md", "ch4.md")
    md6_path = os.path.join(pdir, "chapter_md", "ch6.md")
    if not os.path.isfile(data_path):
        print(f"[错误] 缺少输入: {data_path}")
        return 1

    data = read_json(data_path, {})
    if args.catalog_only:
        visualizer = None
        if args.vision:
            def visualizer(path, context):
                return inspect_photo(
                    image_path=path,
                    expected_context=context,
                    model=VISION_MODEL,
                )
        catalog = build_photo_catalog(
            data,
            pdir,
            visualizer=visualizer,
        )
        out = write_photo_catalog(pdir, catalog)
        say(
            f"[照片目录] {len(catalog.get('candidates') or [])} 个物理照片："
            f"{out}"
        )
        for warning in catalog.get("warnings") or []:
            say(f"  ⚠️ {warning}")
        return 0

    if not os.path.isfile(md2_path):
        print(f"[错误] 缺少输入: {md2_path}")
        return 1
    images = data.get("images") or []
    base = data.get("base") or {}
    equipment = _route_chapter6_equipment(
        data.get("equipment") or [],
        base,
    )
    equipment.extend(
        chapter6_water_aux_photo_items(data.get("water_aux") or {})
    )
    meter_photos = metering_photos(images, data.get("energy_meter") or [])
    buildings = [(b.get("name") or "").strip() for b in (data.get("buildings") or [])]
    unit_short = base.get("unit_short") or base.get("unit_name") or "单位"
    saving = data.get("energy_saving") or []

    caps2 = parse_captions(md2_path, "2")
    caps3 = parse_captions(md3_path, "3") if os.path.isfile(md3_path) else []
    caps4 = parse_captions(md4_path, "4") if os.path.isfile(md4_path) else []
    caps6 = parse_captions(md6_path, "6") if os.path.isfile(md6_path) else []
    section_captions = (
        parse_caption_sections(md6_path, "6")
        if os.path.isfile(md6_path)
        else []
    )
    table_device_names = parse_md_device_names(md6_path)
    if not caps2 and not caps3 and not caps4 and not caps6 and not meter_photos:
        print(f"[错误] {md2_path} / {md3_path} / {md4_path} / {md6_path} 里都没有 "
              f"'图2.x' / '图3.x' / '图4.x' / '图6.x' 图注行——"
              f"图注行是编号唯一来源，请先把它写进 md")
        return 1

    say(f"[项目] {pdir}")
    say(f"[输入] 建筑 {len(buildings)} 栋；照片 {len(images)} 条；"
        f"图注 第2章 {len(caps2)} 条 / 第3章 {len(caps3)} 条 / "
        f"第4章 {len(caps4)} 条 / 第6章 {len(caps6)} 条")

    photo_entries = []
    copy_cache = {}
    warnings = []
    used_sources = set()
    used3 = set()
    used4 = set()
    used6 = set()
    coverage = equipment_caption_coverage(
        equipment, caps6, images, table_names=table_device_names
    )
    if coverage["missing_captions"]:
        warnings.append(
            "第6章设备配图覆盖不足：以下图片槽位没有对应图注："
            + "、".join(coverage["missing_captions"])
        )
    if coverage["missing_local_files"]:
        warnings.append(
            "第6章附件已登记但本地文件缺失，对应图注暂不能归置："
            + "、".join(coverage["missing_local_files"])
        )
    warnings.extend(equipment_caption_section_warnings(
        equipment,
        caps6,
        section_captions,
        unit_func=str(base.get("unit_func") or ""),
        children_func=str(base.get("children_func") or ""),
        institution_category=str(base.get("institution_category") or ""),
        unit_name=str(base.get("unit_name") or ""),
    ))

    for num, caption, desc in caps2:
        if num == 1:
            src = pick_photo(images, OVERALL_CAT) or pick_photo(images, BUILDING_CAT)
            stem = "单位整体外观"
            if not src:
                warnings.append(f"{caption}：没有 '{OVERALL_CAT}' 照片（也无建筑照可兜底）")
                continue
        else:
            name = match_building(desc, buildings)
            if not name:
                warnings.append(f"{caption}：图注里找不到建筑名"
                                f"（现有建筑：{'、'.join(buildings)}）")
                continue
            src = pick_photo(images, BUILDING_CAT, building=name)
            if not src:
                warnings.append(f"{caption}：建筑“{name}”没有可用建筑外观照"
                                f"（检查 data.json 里 images[].building_name）")
                continue
            stem = f"建筑外观_{name}"
        used_sources.add(src)
        if args.dry_run:
            say(f"  · {caption}  <=  {src}")
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=f"data/images/{safe_name(stem)}",
                project_dir=pdir,
                source_path=src,
                images=images,
                kind="building",
                binding_ref=(
                    "images[].category" if num == 1
                    else "images[].building_name"
                ),
                binding_label=(
                    unit_short if num == 1 else name
                ),
            ))
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=rel,
                project_dir=pdir,
                source_path=src,
                images=images,
                kind="building",
                binding_ref=(
                    "images[].category" if num == 1
                    else "images[].building_name"
                ),
                binding_label=(
                    unit_short if num == 1 else name
                ),
            ))

    unused = [im for im in images
              if normalize_photo_category(im.get("category")) == BUILDING_CAT
              and str(im.get("path") or "") not in used_sources]
    if unused:
        names = sorted({(im.get("building_name") or "（无名）") for im in unused})
        say(f"[提示] 有 {len(unused)} 条建筑照未被第2章引用（{'、'.join(names)}）"
            f"——按现口径允许只挑代表性照片，无需处理")

    # ---- 第3章：管理文件截图 / 荣誉证书（来源 es.management_file_images / award_certificate_images）----
    pools = build_ch3_pools(saving, images)
    for kind in ("management", "award"):
        pools[kind] = [
            record
            for record in pools.get(kind) or []
            if os.path.isfile(str(record.get("path") or ""))
        ]
    pool_total = len(pools["management"]) + len(pools["award"])
    if caps3:
        say(f"[第3章] 可用照片：管理文件 {len(pools['management'])} 张 / "
            f"荣誉证书 {len(pools['award'])} 张")

    vision_checks_path = os.path.join(pdir, VISION_CHECKS_FILENAME)
    vision_cache = read_json(
        vision_checks_path, {"version": 1, "checks": {}}
    )
    if not isinstance(vision_cache, dict):
        vision_cache = {"version": 1, "checks": {}}
    vision_checks = vision_cache.get("checks") or {}
    if not isinstance(vision_checks, dict):
        vision_checks = {}
    vision_cache_dirty = False
    expected_recipient = (
        base.get("unit_name") or base.get("unit_short") or unit_short
    )

    for num, caption, desc in caps3:
        src, kind, record = pick_ch3_photo(desc, pools, used3)
        if not src:
            unused_count = len([
                item
                for item in _ch3_candidates(desc, pools)
                if str(item.get("path") or "") not in used3
            ])
            if unused_count > 1:
                warnings.append(
                    f"{caption}：有 {unused_count} 个候选，但图注无法唯一对应具体证书，"
                    f"已停止配图；请在图注中写明证书名称及年份"
                )
            else:
                warnings.append(
                    f"{caption}：第3章没有可用照片，或没有与图注唯一匹配的证书"
                )
            continue

        verification_status = "unverified"
        if kind == "award":
            expected_title = str(record.get("title") or desc).strip()
            cache_key = vision_cache_key(
                image_path=src,
                expected_title=expected_title,
                expected_recipient=expected_recipient,
                model=VISION_MODEL,
            )
            verification = vision_checks.get(cache_key)
            if not (
                isinstance(verification, dict)
                and verification.get("status") in {"pass", "review", "mismatch"}
            ):
                verification = verify_certificate(
                    image_path=src,
                    expected_title=expected_title,
                    expected_recipient=expected_recipient,
                    model=VISION_MODEL,
                )
                if verification.get("status") in {"pass", "review", "mismatch"}:
                    vision_checks[cache_key] = {
                        **verification,
                        "caption": caption,
                        "kind": kind,
                        "file_id": str(record.get("file_id") or ""),
                        "source_path": src,
                        "expected_title": expected_title,
                        "expected_recipient": expected_recipient,
                    }
                    vision_cache_dirty = True

            status = str((verification or {}).get("status") or "unverified")
            verification_status = status
            reason = str((verification or {}).get("reason") or "未完成视觉核验")
            if status == "mismatch":
                if args.certificate_policy == "strict":
                    warnings.append(
                        f"{caption}：视觉核验判定不匹配，严格模式已排除该证书（{reason}）"
                    )
                    continue
                warnings.append(
                    f"{caption}：视觉核验与数据库描述不一致，"
                    f"默认保留数据库候选并建议人工复核（{reason}）"
                )
            if status == "review":
                warnings.append(
                    f"{caption}：保留数据库确定性候选，需人工复核（{reason}）"
                )
            elif status == "unverified":
                warnings.append(
                    f"{caption}：保留数据库确定性候选，视觉复核未完成（{reason}）"
                )

        used3.add(src)
        prefix = "管理文件" if kind == "management" else "荣誉证书"
        stem = f"{prefix}_{os.path.splitext(os.path.basename(src))[0]}"
        if args.dry_run:
            say(f"  · {caption}  <=  {src}")
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=f"data/images/{safe_name(stem)}",
                project_dir=pdir,
                source_path=src,
                images=images,
                kind=kind,
                binding_ref=(
                    "energy_saving[].award_certificate"
                    if kind == "award"
                    else "energy_saving[].management_files"
                ),
                binding_label=str(
                    record.get("title") or "能源管理制度文件"
                ),
                file_id=record.get("file_id"),
                verification=verification_status,
            ))
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=rel,
                project_dir=pdir,
                source_path=src,
                images=images,
                kind=kind,
                binding_ref=(
                    "energy_saving[].award_certificate"
                    if kind == "award"
                    else "energy_saving[].management_files"
                ),
                binding_label=str(
                    record.get("title") or "能源管理制度文件"
                ),
                file_id=record.get("file_id"),
                verification=verification_status,
            ))

    if vision_cache_dirty and not args.dry_run:
        write_json(
            vision_checks_path,
            {"version": 1, "checks": vision_checks},
            backup=True,
        )
        say(f"[第3章] 视觉核验结果：{os.path.basename(vision_checks_path)}")

    # ---- 第6章：设备照片（单字段=设备名；多字段=设备名+字段名）----
    if caps6:
        say(f"[第6章] 图注 {len(caps6)} 条，优先按设备图片字段匹配，文件名兜底")
    for num, caption, desc in caps6:
        picked = pick_ch6_photo_details(
            desc, images, used6, equipment=equipment
        )
        src = str(picked.get("src") or "")
        if not src:
            warnings.append(f"{caption}：第6章未找到与该图注或图片字段匹配的照片"
                            f"（可用分类：{'、'.join(sorted(CH6_DEVICE_CATS))}）")
            continue
        used6.add(src)
        binding_label = str(picked.get("caption_label") or desc)
        stem = f"设备_{binding_label}"
        binding_ref = str(picked.get("binding_ref") or "equipment[].img_ids")
        if args.dry_run:
            say(f"  · {caption}  <=  {src}")
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=f"data/images/{safe_name(stem)}",
                project_dir=pdir,
                source_path=src,
                images=images,
                kind="equipment",
                binding_ref=binding_ref,
                binding_label=binding_label,
                file_id=picked.get("file_id"),
                section_route=picked.get("section_route"),
            ))
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append(make_photo_entry(
                caption=caption,
                destination=rel,
                project_dir=pdir,
                source_path=src,
                images=images,
                kind="equipment",
                binding_ref=binding_ref,
                binding_label=binding_label,
                file_id=picked.get("file_id"),
                section_route=picked.get("section_route"),
            ))

    if pool_total and not caps3:
        warnings.append(f"第3章有 {pool_total} 张可用照片（管理文件 "
                        f"{len(pools['management'])} / 荣誉证书 {len(pools['award'])}），"
                        f"但 ch3.md 没有 '图3.x' 图注行——按规则第3章**必须提供照片**，"
                        f"请在 3.2（管理文件截图）/ 3.3（荣誉证书）末尾补图注行后重跑")

    # ---- 第4章：计量器具照片（台账 device_img + 文件名表种识别）----
    if meter_photos:
        by_type = {}
        for p in meter_photos:
            by_type[p["label"]] = by_type.get(p["label"], 0) + 1
        say(f"[第4章] 可用照片 {len(meter_photos)} 张（"
            + " / ".join(f"{k} {v}" for k, v in by_type.items()) + "）")
    nums4 = [num for num, _, _ in caps4]
    if nums4 and nums4 != list(range(1, len(nums4) + 1)):
        warnings.append(f"第4章图注编号不连续：{nums4}（应自 图4.1 起连号）")
    for num, caption, desc in caps4:
        selected = pick_ch4_photos(desc, meter_photos, used4)
        if not selected:
            warnings.append(f"{caption}：第4章没有可用的 '{METERING_CAT}' 照片"
                            f"（检查 data.json.images[] 与 energy_meter[].device_img）")
            continue
        for item in selected:
            used4.add(item["key"])
            stem = f"{METERING_CAT}_{item['label']}"
            if args.dry_run:
                say(f"  · {caption}  <=  {item['src']}")
                photo_entries.append(make_photo_entry(
                    caption=caption,
                    destination=f"data/images/{safe_name(stem)}",
                    project_dir=pdir,
                    source_path=item["src"],
                    images=images,
                    kind="metering",
                    binding_ref="energy_meter[].device_img",
                    binding_label=item["label"],
                    category=METERING_CAT,
                ))
                continue
            rel = place(pdir, item["src"], stem, args.force, copy_cache, say)
            if rel:
                photo_entries.append(make_photo_entry(
                    caption=caption,
                    destination=rel,
                    project_dir=pdir,
                    source_path=item["src"],
                    images=images,
                    kind="metering",
                    binding_ref="energy_meter[].device_img",
                    binding_label=item["label"],
                    category=METERING_CAT,
                ))

    if meter_photos and not caps4:
        warnings.append(f"第4章有 {len(meter_photos)} 张可用 '{METERING_CAT}' 照片，"
                        f"但 ch4.md 没有 '图4.x' 图注行——请在 4.2 末尾补"
                        f"`图4.1 计量器具照片` 后重跑")

    warnings.extend(semantic_reuse_warnings(photo_entries))

    man_path = os.path.join(pdir, "report_images.json")
    if args.dry_run:
        say(f"[dry-run] 将写入 {len(photo_entries)} 条第2/3/4/6章照片条目，未落盘")
    else:
        man = read_json(man_path, {"images": []})
        if not isinstance(man, dict):
            man = {"images": []}
        old = man.get("images") or []
        kept = [e for e in old
                if not str(e.get("caption") or "").strip().startswith(MANAGED_PREFIXES)]
        dropped = len(old) - len(kept)
        man["images"] = kept + photo_entries
        if os.path.isfile(man_path):
            shutil.copy2(man_path, man_path + ".bak")
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        say(f"[清单] {os.path.basename(man_path)}：重建第2/3/4/6章条目 {len(photo_entries)} 条"
            f"（替换旧条目 {dropped} 条，保留其他条目 {len(kept)} 条）")

    if not args.dry_run:
        write_json(
            os.path.join(pdir, FINALIZATION_STATUS_FILENAME),
            {
                "clean": not warnings,
                "warnings": warnings,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            backup=True,
        )

    if warnings:
        print(f"\n[告警] {len(warnings)} 条：")
        for w in warnings:
            print(f"  · {w}")
        return 2
    say("\n[完成] 第2/3/4/6章照片已归置（无告警）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
