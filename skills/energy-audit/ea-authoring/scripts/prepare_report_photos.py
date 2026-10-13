#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_report_photos.py — 报告照片归置器（2.1/2.2 建筑外观照）

背景（2026-10-13）：照片从"采集产物"到"报告图表"这一段此前**没有任何工序**——
谁复制、放哪个目录、叫什么名、清单怎么写全靠人临场决定，于是出现三种后果：
  ① 副本目录两派（data/images/ 与 images/）；
  ② 文件名三派（平台 ID / 中文 / 英文）；
  ③ 岚山区人民医院 7 张建筑照一张没用进 2.2（归属信息在采集层被丢掉，只能人肉看图）。

本脚本把这一步工序化：**md 图注行是唯一编号源**，脚本按图注里的建筑名去
`data.json` 的照片里取对应照片，复制到 `<项目>/data/images/` 并写出
`report_images.json` 的第2章照片条目。

分工：
  - 本脚本：装配**前**的三方一致（md 图注 ↔ 清单 ↔ 磁盘文件）+ 未引用照片提示；
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
    - 非第2章条目（图表、附录照片等）原样保留，本脚本不碰。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys

CAP_RE = re.compile(r"^图2\.(\d+)\s*(.+?)\s*$")
BUILDING_CAT = "建筑外观"
OVERALL_CAT = "单位整体外观"
IMG_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
MANAGED_PREFIX = "图2."


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


def parse_captions(md_path: str):
    """返回 [(图号 int, 图注全文, 说明文字)]，按 md 出现顺序。"""
    out = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            m = CAP_RE.match(line.strip())
            if m:
                out.append((int(m.group(1)), line.strip(), m.group(2).strip()))
    return out


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
    """
    ext = os.path.splitext(src)[1].lower() or ".png"
    if ext not in IMG_EXT:
        say(f"  ⚠️ 跳过非常规图片扩展名：{src}")
        return ""
    digest = sha1(src)
    cache_key = (safe_name(stem), digest)
    if cache_key in copy_cache:
        return copy_cache[cache_key]
    img_dir = os.path.join(project_dir, "data", "images")
    os.makedirs(img_dir, exist_ok=True)
    dst = os.path.join(img_dir, f"{cache_key[0]}{ext}")
    n = 2
    while os.path.isfile(dst) and sha1(dst) != digest:
        if force:
            break
        dst = os.path.join(img_dir, f"{cache_key[0]}_{n}{ext}")
        n += 1
    if not os.path.isfile(dst) or sha1(dst) != digest:
        shutil.copy2(src, dst)
        say(f"  + 复制照片: {os.path.basename(dst)}")
    rel = os.path.relpath(dst, project_dir).replace(os.sep, "/")
    copy_cache[cache_key] = rel
    return rel


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="报告照片归置器（2.1/2.2 建筑外观照）")
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
    md_path = os.path.join(pdir, "chapter_md", "ch2.md")
    for need in (data_path, md_path):
        if not os.path.isfile(need):
            print(f"[错误] 缺少输入: {need}")
            return 1

    data = read_json(data_path, {})
    images = data.get("images") or []
    buildings = [(b.get("name") or "").strip() for b in (data.get("buildings") or [])]
    base = data.get("base") or {}
    unit_short = base.get("unit_short") or base.get("unit_name") or "单位"

    captions = parse_captions(md_path)
    if not captions:
        print(f"[错误] {md_path} 里没有 '图2.x' 图注行——"
              f"图注行是编号唯一来源，请先把它写进 md")
        return 1

    say(f"[项目] {pdir}")
    say(f"[输入] 建筑 {len(buildings)} 栋；照片 {len(images)} 条；md 图注 {len(captions)} 条")

    photo_entries = []
    copy_cache = {}
    warnings = []
    used_sources = set()

    for num, caption, desc in captions:
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

    man_path = os.path.join(pdir, "report_images.json")
    if args.dry_run:
        say(f"[dry-run] 将写入 {len(photo_entries)} 条第2章照片条目，未落盘")
    else:
        man = read_json(man_path, {"images": []})
        if not isinstance(man, dict):
            man = {"images": []}
        old = man.get("images") or []
        kept = [e for e in old
                if not str(e.get("caption") or "").strip().startswith(MANAGED_PREFIX)]
        dropped = len(old) - len(kept)
        man["images"] = kept + photo_entries
        if os.path.isfile(man_path):
            shutil.copy2(man_path, man_path + ".bak")
        with open(man_path, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, indent=2)
        say(f"[清单] {os.path.basename(man_path)}：重建第2章条目 {len(photo_entries)} 条"
            f"（替换旧条目 {dropped} 条，保留其他条目 {len(kept)} 条）")

    if warnings:
        print(f"\n[告警] {len(warnings)} 条：")
        for w in warnings:
            print(f"  · {w}")
        return 2
    say("\n[完成] 第2章照片已归置（无告警）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
