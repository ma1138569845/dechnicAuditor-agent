#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_chapter5_figures.py — 第5章图表三方强绑定归置器。

真值链：
    chapter5_figures.json（本次生成批次）
        ↔ chapter_md/ch5_import.md 的图5.x 图注行
        ↔ report_images.json 的图5.x 条目
        ↔ charts/ 下的实际文件及 SHA-256

本脚本只重建 `report_images.json` 中的图5.x 条目，图2/3/4/6 与其他条目原样保留。
任一处不一致均退出 2，且不覆盖原清单；装配器还有第二道硬闸门，不能靠漏跑本脚本绕过。

用法:
    python prepare_chapter5_figures.py <项目名|项目目录> [--check] [--dry-run] [--quiet]

退出码:
    0 三方可信且（非 check/dry-run 时）已原子更新清单
    1 输入/JSON/路径结构不合法
    2 图注、图号、文件或哈希不一致
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path


MANIFEST_NAME = "chapter5_figures.json"
CAPTION_RE = re.compile(r"^图5\.(\d+)\s+\S.+$")


class InputError(ValueError):
    pass


class BindingError(ValueError):
    pass


def projects_root() -> Path:
    raw = os.environ.get("HERMES_PROJECTS_ROOT")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "projects" / "energy-audit"


def resolve_project_dir(arg: str) -> Path:
    candidate = Path(arg).expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    candidate = projects_root() / arg
    if candidate.is_dir():
        return candidate.resolve()
    raise InputError(f"项目目录不存在: {arg}（查找根: {projects_root()}）")


def read_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise InputError(f"缺少输入: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"JSON 无法解析: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise InputError(f"JSON 顶层必须是对象: {path}")
    return data


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_project_src(project: Path, src: str) -> Path:
    if not src:
        raise InputError("manifest 图条目的 src 为空")
    raw = Path(src)
    if raw.is_absolute():
        raise InputError(f"manifest src 必须是项目内相对路径: {src}")
    target = (project / raw).resolve()
    try:
        target.relative_to(project)
    except ValueError as exc:
        raise InputError(f"manifest src 越出项目目录: {src}") from exc
    return target


def chapter5_captions(md_path: Path) -> list[str]:
    if not md_path.is_file():
        raise InputError(f"缺少第5章装配稿: {md_path}")
    captions = []
    markdown_images = []
    for line_no, line in enumerate(
            md_path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if text.startswith("![图5."):
            markdown_images.append(f"第{line_no}行 {text[:80]}")
            continue
        match = CAPTION_RE.match(text)
        if match:
            captions.append(text)
    if markdown_images:
        raise BindingError(
            "第5章装配稿仍含 Markdown 图片语法；装配器不会按图片渲染，"
            "请改成裸图注行：" + "；".join(markdown_images[:3])
        )
    return captions


def validate(project: Path) -> tuple[dict, list[dict], list[str]]:
    manifest = read_json(project / MANIFEST_NAME)
    figures = manifest.get("figures")
    if not isinstance(figures, list):
        raise InputError(f"{MANIFEST_NAME} 缺 figures 数组")

    captions = []
    seen_captions = set()
    for index, figure in enumerate(figures, 1):
        if not isinstance(figure, dict):
            raise InputError(f"figures[{index - 1}] 不是对象")
        figure_no = str(figure.get("figure_no") or "")
        if figure_no != f"5.{index}":
            raise BindingError(
                f"manifest 图号不连续：第 {index} 条应为 5.{index}，实际 {figure_no!r}"
            )
        caption = str(figure.get("caption") or "").strip()
        if not CAPTION_RE.match(caption):
            raise BindingError(f"manifest 图注形态不合法: {caption!r}")
        if not caption.startswith(f"图5.{index} "):
            raise BindingError(
                f"manifest 图号与图注不一致：figure_no=5.{index}，caption={caption}"
            )
        if caption in seen_captions:
            raise BindingError(f"manifest 存在重复图注: {caption}")
        seen_captions.add(caption)
        captions.append(caption)

        src = str(figure.get("src") or "")
        target = resolve_project_src(project, src)
        if not target.is_file():
            raise BindingError(f"{caption} 的图文件不存在: {src}")
        expected_hash = str(figure.get("sha256") or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise BindingError(f"{caption} 缺有效 sha256")
        actual_hash = sha256(target)
        if actual_hash != expected_hash:
            raise BindingError(
                f"{caption} 的图文件已变化：manifest={expected_hash[:12]}…，"
                f"实际={actual_hash[:12]}…"
            )

    md_captions = chapter5_captions(project / "chapter_md" / "ch5_import.md")
    if md_captions != captions:
        raise BindingError(
            "第5章装配稿图注与本次生成清单不一致："
            f"md={md_captions}；manifest={captions}"
        )
    return manifest, figures, captions


def atomic_write_json(path: Path, payload: dict):
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="第5章图表三方强绑定归置器")
    parser.add_argument("project", help="项目名或项目目录")
    parser.add_argument("--check", action="store_true", help="只校验，不写清单")
    parser.add_argument("--dry-run", action="store_true", help="校验并显示变更，不落盘")
    parser.add_argument("--quiet", action="store_true", help="只在异常时输出")
    args = parser.parse_args(argv)

    def say(*values):
        if not args.quiet:
            print(*values)

    try:
        project = resolve_project_dir(args.project)
        manifest, figures, captions = validate(project)
    except InputError as exc:
        print(f"[错误] {exc}")
        return 1
    except BindingError as exc:
        print(f"[错误] {exc}")
        return 2

    entries = []
    for figure in figures:
        entries.append({
            "caption": figure["caption"],
            "src": str(figure["src"]).replace("\\", "/"),
            "sha256": figure["sha256"],
        })

    say(
        f"[校验] 图5共 {len(entries)} 条；manifest、ch5_import.md、"
        "文件与哈希一致"
    )
    if args.check or args.dry_run:
        for entry in entries:
            say(f"  · {entry['caption']}  <=  {entry['src']}")
        say("[dry-run] 未写入 report_images.json" if args.dry_run else "[check] 通过")
        return 0

    path = project / "report_images.json"
    if path.is_file():
        images_doc = read_json(path)
        old = images_doc.get("images") or []
        if not isinstance(old, list):
            print(f"[错误] {path} 的 images 必须是数组")
            return 1
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    else:
        images_doc = {"images": []}
        old = []
    kept = [
        entry for entry in old
        if isinstance(entry, dict)
        and not str(entry.get("caption") or "").strip().startswith("图5.")
    ]
    images_doc["images"] = kept + entries
    atomic_write_json(path, images_doc)
    say(
        f"[清单] 图5条目 {len(entries)} 条已写入 {path}；"
        f"替换旧图5条目 {len(old) - len(kept)} 条，保留其他条目 {len(kept)} 条"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
