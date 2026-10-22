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
第6章先用 `equipment[].img_ids → images[].file_id` 精确匹配，再按文件名兜底。

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
  - **第6章**：凡 `equipment[].img_ids` 非空的设备，都必须各有一条
    `图6.N 设备名`；缺任何一条即 rc=2。特殊用能中的医疗设备与
    数据中心/信息中心分别校验，不能用系统级一张图代替。

分工：
  - 本脚本：装配**前**的三方一致（md 图注 ↔ 清单 ↔ 磁盘文件）+ 未引用照片提示；
    第3/4章照片**规则要求必给**，所以"有照片但 ch3.md/ch4.md 没写图注行"
    会按告警报出（rc=2）；
  - ea_docx_asserts.py 的 ch2_22_photos / ch3_photos / ch4_photos：
    装配**后**的成品一致（图注 ↔ 图）。

用法:
    python prepare_report_photos.py <项目名|项目目录> [--force] [--dry-run] [--quiet]

行为与退出码:
    0  正常（含"有照片未被引用"这类提示）
    1  输入缺失（项目目录 / data.json / chapter_md/ch2.md 任一不在）
    2  有告警（图注匹配不到照片，或有照片却没写图注，或有 img_ids 的设备缺图注）
       ——已能写的条目仍会写

产物:
    <项目>/data/images/<规范化文件名>         照片副本（清单引用的就是它）
    <项目>/report_images.json                 第2/3/4/6章照片条目重建（写前留 .bak）
    <项目>/photo_vision_checks.json            第3章荣誉证书视觉核验缓存与核验记录

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
import json
import os
import re
import shutil
import sys
from pathlib import Path


def _load_photo_contract():
    """加载 repo 中的唯一分类契约；技能从 profile 或 repo 内运行都可用。"""
    try:
        from tools.energy_audit.project_data import (  # type: ignore
            PHOTO_CATEGORIES,
            normalize_photo_category,
        )
        return PHOTO_CATEGORIES, normalize_photo_category
    except ModuleNotFoundError:
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "tools" / "energy_audit" / "project_data.py").is_file():
                sys.path.insert(0, str(parent))
                break
        from tools.energy_audit.project_data import (  # type: ignore
            PHOTO_CATEGORIES,
            normalize_photo_category,
        )
        return PHOTO_CATEGORIES, normalize_photo_category


PHOTO_CATEGORIES, normalize_photo_category = _load_photo_contract()


def _load_photo_vision():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    from photo_vision import (  # type: ignore
        DEFAULT_MODEL,
        normalize_claim_text,
        verify_certificate,
        vision_cache_key,
    )
    return DEFAULT_MODEL, normalize_claim_text, verify_certificate, vision_cache_key


VISION_MODEL, _normalize_claim_text, verify_certificate, vision_cache_key = \
    _load_photo_vision()
VISION_CHECKS_FILENAME = "photo_vision_checks.json"

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
}
assert CH6_DEVICE_CATS <= set(PHOTO_CATEGORIES)
# 图注关键词 → 设备照片分类（文件名对不上时的兜底）
CH6_CAT_HINTS = (
    (("照明", "灯"), "照明设备"),
    (("办公", "电脑", "打印"), "办公设备"),
    (("信息机房", "机房", "服务器", "数据中心"), "信息机房"),
    (("医疗", "X射线", "CT", "摄影"), "医疗设备"),
    (("空调", "冷水", "冷却塔", "热泵"), "制冷设备"),
    (("变压器", "配电柜", "配电室", "开关柜"), "变压器/配电"),
    (("水泵", "水箱"), "水泵/水箱"),
    (("厨房", "燃气灶", "蒸柜", "消毒柜"), "厨房设备"),
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
    ("数据中心", ("机房", "数据中心")),
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


def parse_md_device_names(md_path: str) -> set:
    """从第6章 Markdown 设备表抽取“设备名称”列。

    配图覆盖以报告实际列出的设备行为边界；数据库里存在但未进入设备表的条目，
    不在本脚本强制配图。
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


def _img_ids(equipment: dict) -> list:
    raw = equipment.get("img_ids")
    if isinstance(raw, (list, tuple, set)):
        return [str(v).strip() for v in raw if str(v).strip()]
    return re.findall(r"\d+", str(raw or ""))


def _images_by_file_id(images) -> dict:
    out = {}
    for im in images or []:
        fid = str(im.get("file_id") or "").strip()
        if fid:
            out[fid] = im
    return out


def equipment_caption_gaps(equipment, captions, images=None, table_names=None) -> list:
    """返回「有 img_ids 但第6章没有设备图注」的设备名。

    这是本链路的硬校验：只检查 md 中已有图注是否都能找到图，会把
    “设备行有附件、作者漏写图注”的整条记录静默跳过。必须从设备台账反向查。
    """
    caption_keys = [_photo_name_key(desc) for _, _, desc in captions]
    available_ids = set(_images_by_file_id(images or []))
    table_keys = [_photo_name_key(name) for name in (table_names or [])]
    missing, seen = [], set()
    for eq in equipment or []:
        name = str(eq.get("name") or "").strip()
        key = _photo_name_key(name)
        ids = _img_ids(eq)
        if not key or key in seen or not ids or not available_ids.intersection(ids):
            continue
        if table_keys and not any(key == tk or key in tk or tk in key for tk in table_keys):
            continue
        seen.add(key)
        if not any(key == ck or (key and ck and (key in ck or ck in key))
                   for ck in caption_keys):
            missing.append(name)
    return missing


def pick_ch6_photo(desc: str, images, used: set, equipment=None):
    """第6章设备照：图注（设备名）→ 设备照片池按文件名匹配。

    规则（2026-10-21）：每个合并后的设备表行 1 张图，图注=设备名；
    优先文件名主干与图注完全相同，其次互相包含；只用设备类照片，
    建筑外观/计量器具不参与。
    """
    key = re.sub(r"\s+", "", desc or "")
    if not key:
        return ""
    pool = [(im, str(im.get("path") or "")) for im in images
            if normalize_photo_category(im.get("category")) in CH6_DEVICE_CATS]
    by_file_id = _images_by_file_id(images)

    # ① 设备台账 img_ids → 采集照片 file_id。文件 ID 是稳定关联键，
    # 优先于文件名/分类猜测；平台多个附件同名时尤其必要。
    key_desc = _photo_name_key(desc)
    matched_eqs = []
    for eq in equipment or []:
        eq_key = _photo_name_key(eq.get("name"))
        if not eq_key:
            continue
        if eq_key == key_desc:
            matched_eqs.insert(0, eq)
        elif key_desc and (eq_key in key_desc or key_desc in eq_key):
            matched_eqs.append(eq)
    for allow_used in (False, True):
        for eq in matched_eqs:
            for fid in _img_ids(eq):
                im = by_file_id.get(fid)
                p = str((im or {}).get("path") or "")
                if not p or not os.path.isfile(p):
                    continue
                if allow_used or p not in used:
                    return p

    def _first(match, allow_used=False):
        for im, p in pool:
            stem = _stem(p)
            if stem in CH6_GARBAGE_STEMS or stem.startswith("微信图片"):
                continue
            if not match(im, p):
                continue
            if not os.path.isfile(p):
                continue
            if allow_used or p not in used:
                return p
        return ""

    def _stem(p):
        return re.sub(r"\s+", "", os.path.splitext(os.path.basename(p))[0])

    for allow_used in (False, True):                    # ① 主干完全相同（先未用，后允许复用）
        hit = _first(lambda im, p: _stem(p) == key, allow_used)
        if hit:
            return hit
    for allow_used in (False, True):                    # ② 互相包含
        hit = _first(lambda im, p: _stem(p) and (key in _stem(p) or _stem(p) in key), allow_used)
        if hit:
            return hit
    for cap_kw, img_kws in CH6_KEYWORDS:                # ③ 同义词关键词（不做分类兜底）
        if cap_kw in key:
            for allow_used in (False, True):
                hit = _first(lambda im, p, ks=img_kws: any(k in _stem(p) for k in ks), allow_used)
                if hit:
                    return hit
    return ""


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
    data_path = os.path.join(pdir, "data.json")
    md2_path = os.path.join(pdir, "chapter_md", "ch2.md")
    md3_path = os.path.join(pdir, "chapter_md", "ch3.md")
    md4_path = os.path.join(pdir, "chapter_md", "ch4.md")
    md6_path = os.path.join(pdir, "chapter_md", "ch6.md")
    for need in (data_path, md2_path):
        if not os.path.isfile(need):
            print(f"[错误] 缺少输入: {need}")
            return 1

    data = read_json(data_path, {})
    images = data.get("images") or []
    equipment = data.get("equipment") or []
    meter_photos = metering_photos(images, data.get("energy_meter") or [])
    buildings = [(b.get("name") or "").strip() for b in (data.get("buildings") or [])]
    base = data.get("base") or {}
    unit_short = base.get("unit_short") or base.get("unit_name") or "单位"
    saving = data.get("energy_saving") or []

    caps2 = parse_captions(md2_path, "2")
    caps3 = parse_captions(md3_path, "3") if os.path.isfile(md3_path) else []
    caps4 = parse_captions(md4_path, "4") if os.path.isfile(md4_path) else []
    caps6 = parse_captions(md6_path, "6") if os.path.isfile(md6_path) else []
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
    photo_gaps = equipment_caption_gaps(
        equipment, caps6, images, table_names=table_device_names
    )
    if photo_gaps:
        warnings.append(
            "第6章设备配图覆盖不足：以下有 img_ids 的设备没有对应图注："
            + "、".join(photo_gaps)
            + "。请按设备名补写 `图6.N 设备名` 后重跑"
        )

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
            photo_entries.append({"caption": caption, "src": f"data/images/{safe_name(stem)}"})
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append({"caption": caption, "src": rel})

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
            photo_entries.append({"caption": caption,
                                  "src": f"data/images/{safe_name(stem)}"})
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append({"caption": caption, "src": rel})

    if vision_cache_dirty and not args.dry_run:
        write_json(
            vision_checks_path,
            {"version": 1, "checks": vision_checks},
            backup=True,
        )
        say(f"[第3章] 视觉核验结果：{os.path.basename(vision_checks_path)}")

    # ---- 第6章：设备照片（图注=设备名；每个合并后的设备表行 1 张）----
    if caps6:
        say(f"[第6章] 图注 {len(caps6)} 条，优先按设备 img_ids 匹配，文件名兜底")
    for num, caption, desc in caps6:
        src = pick_ch6_photo(desc, images, used6, equipment=equipment)
        if not src:
            warnings.append(f"{caption}：第6章未找到与设备名匹配的照片"
                            f"（可用分类：{'、'.join(sorted(CH6_DEVICE_CATS))}）")
            continue
        used6.add(src)
        stem = f"设备_{desc}"
        if args.dry_run:
            say(f"  · {caption}  <=  {src}")
            photo_entries.append({"caption": caption,
                                  "src": f"data/images/{safe_name(stem)}"})
            continue
        rel = place(pdir, src, stem, args.force, copy_cache, say)
        if rel:
            photo_entries.append({"caption": caption, "src": rel})

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
                photo_entries.append({"caption": caption,
                                      "src": f"data/images/{safe_name(stem)}"})
                continue
            rel = place(pdir, item["src"], stem, args.force, copy_cache, say)
            if rel:
                photo_entries.append({"caption": caption, "src": rel})

    if meter_photos and not caps4:
        warnings.append(f"第4章有 {len(meter_photos)} 张可用 '{METERING_CAT}' 照片，"
                        f"但 ch4.md 没有 '图4.x' 图注行——请在 4.2 末尾补"
                        f"`图4.1 计量器具照片` 后重跑")

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

    if warnings:
        print(f"\n[告警] {len(warnings)} 条：")
        for w in warnings:
            print(f"  · {w}")
        return 2
    say("\n[完成] 第2/3/4/6章照片已归置（无告警）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
