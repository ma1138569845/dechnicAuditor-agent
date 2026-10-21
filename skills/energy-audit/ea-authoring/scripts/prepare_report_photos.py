#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_report_photos.py — 报告照片归置器（第2章建筑外观照 + 第3章管理文件/荣誉证书）

背景（2026-10-13）：照片从"采集产物"到"报告图表"这一段此前**没有任何工序**——
谁复制、放哪个目录、叫什么名、清单怎么写全靠人临场决定，于是出现三种后果：
  ① 副本目录两派（data/images/ 与 images/）；
  ② 文件名三派（平台 ID / 中文 / 英文）；
  ③ 岚山区人民医院 7 张建筑照一张没用进 2.2（归属信息在采集层被丢掉，只能人肉看图）。

本脚本把这一步工序化：**md 图注行是唯一编号源**，脚本按图注里的建筑名去
`data.json` 的照片里取对应照片，复制到 `<项目>/data/images/` 并写出
`report_images.json` 的第2章照片条目。

覆盖范围（2026-10-13 扩到第3章）：
  - **第2章**：图 2.1（单位整体外观）+ 图 2.2…（逐栋建筑外观照，来源
    `proj.images[]` 的 `建筑外观` + `building_name`）；
  - **第3章**：图 3.1…（管理文件截图 / 荣誉证书，来源
    `es.management_file_images` / `es.award_certificate_images`）；选图规则 =
    文件名主干命中图注 → 关键词判池（荣誉/奖/证书 → 荣誉证书；制度/文件/标识/
    管理/规定/措施/截图 → 管理文件）→ 按池顺序兜底。

分工：
  - 本脚本：装配**前**的三方一致（md 图注 ↔ 清单 ↔ 磁盘文件）+ 未引用照片提示；
    第3章照片**规则要求必给**，所以"有照片但 ch3.md 没写图注行"会按告警报出（rc=2）；
  - ea_docx_asserts.py 的 ch2_22_photos：装配**后**的成品一致（图注 ↔ 图）。

用法:
    python prepare_report_photos.py <项目名|项目目录> [--force] [--dry-run] [--quiet]

行为与退出码:
    0  正常（含"有照片未被引用"这类提示）
    1  输入缺失（项目目录 / data.json / chapter_md/ch2.md 任一不在）
    2  有告警（某条图注匹配不到照片）——已能写的条目仍会写

产物:
    <项目>/data/images/<规范化文件名>         照片副本（清单引用的就是它）
    <项目>/report_images.json                 第2章照片条目重建（写前留 .bak）

约定（对应 2026-10-13 五项决策）:
    - 副本目录统一 `data/images/`，清单 src 写相对路径 `data/images/xxx.png`；
    - 图 2.1 → 分类 `单位整体外观`（无则第一张建筑照），图注沿用
      "图2.1 {单位简称}单位整体外观"；
    - 图 2.N（N≥2）→ 图注里的建筑名 → 该建筑的 `building_name` 照片，图注措辞
      "图2.N {楼名}总体外观"；**图数不要求等于栋数**（挑几张即可）；
    - 本章之外条目（图表、附录照片等）原样保留，本脚本不碰。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

CAP_RE = re.compile(r"^图([236])\.(\d+)\s*(.+?)\s*$")
BUILDING_CAT = "建筑外观"
OVERALL_CAT = "单位整体外观"
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
# 本脚本负责重建的图注前缀（其余条目原样保留）
MANAGED_PREFIXES = ("图2.", "图3.", "图6.")
# 第6章：设备照片池（建筑外观/计量器具不参与设备配图）
CH6_DEVICE_CATS = {"制冷设备", "照明设备", "办公设备", "其他用电设备", "信息机房"}
# 图注关键词 → 设备照片分类（文件名对不上时的兜底）
CH6_CAT_HINTS = (
    (("照明", "灯"), "照明设备"),
    (("办公", "电脑", "打印机"), "办公设备"),
    (("信息机房", "机房", "服务器"), "信息机房"),
    (("空调", "冷水", "冷却塔", "热泵"), "制冷设备"),
    (("电梯", "水泵", "开水器", "热水"), "其他用电设备"),
)
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


def parse_captions(md_path: str, chapter: str):
    """返回指定章的 [(图号 int, 图注全文, 说明文字)]，按 md 出现顺序。"""
    out = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            m = CAP_RE.match(line.strip())
            if m and m.group(1) == chapter:
                out.append((int(m.group(2)), line.strip(), m.group(3).strip()))
    return out


def pick_ch3_photo(desc: str, pools: dict, used: set):
    """第3章选图：①文件名主干命中图注 → ②关键词判池 → ③按池顺序兜底。

    pools = {"management": [管理文件截图路径…], "award": [荣誉证书路径…]}
    """
    all_files = [(kind, p) for kind in ("management", "award") for p in pools[kind]]
    for kind, p in all_files:
        stem = os.path.splitext(os.path.basename(p))[0]
        if stem and stem in desc and p not in used:
            return p, kind
    for kind, label, keys in CH3_RULES:
        if any(k in desc for k in keys):
            for p in pools[kind]:
                if p not in used:
                    return p, kind
    for kind in ("management", "award"):          # 兜底：按池顺序取未用过的
        for p in pools[kind]:
            if p not in used:
                return p, kind
    return "", ""


def pick_ch6_photo(desc: str, images, used: set):
    """第6章设备照：图注（设备名）→ 设备照片池按文件名匹配。

    规则（2026-10-21）：每个合并后的设备表行 1 张图，图注=设备名；
    优先文件名主干与图注完全相同，其次互相包含；只用设备类照片，
    建筑外观/计量器具不参与。
    """
    key = re.sub(r"\s+", "", desc or "")
    if not key:
        return ""
    pool = [(im, str(im.get("path") or "")) for im in images
            if (im.get("category") or "") in CH6_DEVICE_CATS]
    for im, p in pool:                                  # ① 主干完全相同
        stem = re.sub(r"\s+", "", os.path.splitext(os.path.basename(p))[0])
        if stem == key and p not in used and os.path.isfile(p):
            return p
    for im, p in pool:                                  # ② 互相包含
        stem = re.sub(r"\s+", "", os.path.splitext(os.path.basename(p))[0])
        if stem and (key in stem or stem in key) and p not in used and os.path.isfile(p):
            return p
    for keys, cat in CH6_CAT_HINTS:                     # ③ 图注关键词 → 分类兜底
        if any(k in key for k in keys):
            for im, p in pool:
                if (im.get("category") or "") == cat and p not in used and os.path.isfile(p):
                    return p
    return ""


def match_building(desc: str, buildings):
    """从图注说明里找建筑名（最长优先，避免"门诊楼"命中"门诊病房综合楼"的部分串）。"""
    for name in sorted([b for b in buildings if b], key=len, reverse=True):
        if name in desc:
            return name
    return ""


def pick_photo(images, category: str, building: str = ""):
    """按分类（+建筑名）选一张照片；命中多个取第一个。"""
    for im in images:
        if (im.get("category") or "") != category:
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
    ap = argparse.ArgumentParser(description="报告照片归置器（第2章建筑外观照 / 第3章管理文件·荣誉证书 / 第6章设备照）")
    ap.add_argument("project", help="项目名（~/projects/energy-audit/<项目名>）或项目目录")
    ap.add_argument("--force", action="store_true", help="同名不同内容时覆盖既有副本/清单")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不复制、不写清单")
    ap.add_argument("--quiet", action="store_true", help="只在告警时输出")
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
    md6_path = os.path.join(pdir, "chapter_md", "ch6.md")
    for need in (data_path, md2_path):
        if not os.path.isfile(need):
            print(f"[错误] 缺少输入: {need}")
            return 1

    data = read_json(data_path, {})
    images = data.get("images") or []
    buildings = [(b.get("name") or "").strip() for b in (data.get("buildings") or [])]
    base = data.get("base") or {}
    unit_short = base.get("unit_short") or base.get("unit_name") or "单位"
    saving = data.get("energy_saving") or []

    caps2 = parse_captions(md2_path, "2")
    caps3 = parse_captions(md3_path, "3") if os.path.isfile(md3_path) else []
    caps6 = parse_captions(md6_path, "6") if os.path.isfile(md6_path) else []
    if not caps2 and not caps3 and not caps6:
        print(f"[错误] {md2_path} / {md3_path} / {md6_path} 里都没有 '图2.x' / '图3.x' / '图6.x' 图注行——"
              f"图注行是编号唯一来源，请先把它写进 md")
        return 1

    say(f"[项目] {pdir}")
    say(f"[输入] 建筑 {len(buildings)} 栋；照片 {len(images)} 条；"
        f"图注 第2章 {len(caps2)} 条 / 第3章 {len(caps3)} 条 / 第6章 {len(caps6)} 条")

    photo_entries = []
    copy_cache = {}
    warnings = []
    used_sources = set()
    used3 = set()
    used6 = set()

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
              if (im.get("category") or "") == BUILDING_CAT
              and str(im.get("path") or "") not in used_sources]
    if unused:
        names = sorted({(im.get("building_name") or "（无名）") for im in unused})
        say(f"[提示] 有 {len(unused)} 条建筑照未被第2章引用（{'、'.join(names)}）"
            f"——按现口径允许只挑代表性照片，无需处理")

    # ---- 第3章：管理文件截图 / 荣誉证书（来源 es.management_file_images / award_certificate_images）----
    pools = {"management": [], "award": []}
    for es in saving:
        for p in (es.get("management_file_images") or []):
            if p and os.path.isfile(p) and p not in pools["management"]:
                pools["management"].append(p)
        for p in (es.get("award_certificate_images") or []):
            if p and os.path.isfile(p) and p not in pools["award"]:
                pools["award"].append(p)
    pool_total = len(pools["management"]) + len(pools["award"])
    if caps3:
        say(f"[第3章] 可用照片：管理文件 {len(pools['management'])} 张 / "
            f"荣誉证书 {len(pools['award'])} 张")
    for num, caption, desc in caps3:
        src, kind = pick_ch3_photo(desc, pools, used3)
        if not src:
            warnings.append(f"{caption}：第3章没有可用照片（es.management_file_images / "
                            f"award_certificate_images 均为空或已用完）")
            continue
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

    # ---- 第6章：设备照片（图注=设备名；每个合并后的设备表行 1 张）----
    if caps6:
        say(f"[第6章] 图注 {len(caps6)} 条，设备照片池按文件名匹配")
    for num, caption, desc in caps6:
        src = pick_ch6_photo(desc, images, used6)
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

    man_path = os.path.join(pdir, "report_images.json")
    if args.dry_run:
        say(f"[dry-run] 将写入 {len(photo_entries)} 条第2/3/6章照片条目，未落盘")
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
        say(f"[清单] {os.path.basename(man_path)}：重建第2/3/6章条目 {len(photo_entries)} 条"
            f"（替换旧条目 {dropped} 条，保留其他条目 {len(kept)} 条）")

    if warnings:
        print(f"\n[告警] {len(warnings)} 条：")
        for w in warnings:
            print(f"  · {w}")
        return 2
    say("\n[完成] 第2/3/6章照片已归置（无告警）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
