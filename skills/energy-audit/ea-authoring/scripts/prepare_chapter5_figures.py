#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_chapter5_figures.py — 第5章图表三方强绑定归置器。

真值链：
    chapter5_figures.json（本次生成批次）
        ↔ chapter_md/ch5_import.md 的图5.x 图注行
        ↔ report_images.json 的图5.x 条目
        ↔ charts/ 下的实际文件及 SHA-256

本脚本只重建 `report_images.json` 中的图5.x 条目，图2/3/4/6 与其他条目原样保留。
默认策略把单图缺失/哈希/图注异常写进 `chapter5_figure_issues.json`，只把可信图
写入清单；`--policy strict` 才以退出码 2 阻断最终严格审核。

用法:
    python prepare_chapter5_figures.py <项目名|项目目录>
        [--check] [--dry-run] [--policy placeholder|strict] [--quiet]

退出码:
    0 默认策略完成（可能有已登记的缺图/异常）
    1 输入/JSON/路径结构不合法
    2 strict 策略发现图注、图号、文件或哈希不一致
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
ISSUES_NAME = "chapter5_figure_issues.json"
MISSING_ITEMS_NAME = "missing_items.json"
CAPTION_RE = re.compile(r"^图5\.(\d+)\s+\S.+$")
PLACEHOLDER_RE = re.compile(r"（暂缺[：:].*）$")


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
            captions.append(PLACEHOLDER_RE.sub("", text).strip())
    if markdown_images:
        raise BindingError(
            "第5章装配稿仍含 Markdown 图片语法；装配器不会按图片渲染，"
            "请改成裸图注行：" + "；".join(markdown_images[:3])
        )
    return captions


def _issue(code: str, reason: str, figure_no: str = "",
           caption: str = "") -> dict:
    return {
        "figure_no": figure_no,
        "caption": caption,
        "code": code,
        "reason": reason,
    }


def validate(project: Path) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """返回 manifest、全部图定义、可信 entries、问题清单。

    图注整批不匹配时无法可靠判断剩余图片的语义归属，因此整批图5条目不写入
    report_images.json；单图文件/哈希异常只淘汰该图。
    """
    manifest = read_json(project / MANIFEST_NAME)
    figures = manifest.get("figures")
    if not isinstance(figures, list):
        raise InputError(f"{MANIFEST_NAME} 缺 figures 数组")

    captions = []
    seen_captions = set()
    safe_entries = []
    issues = []
    clear_all_entries = False
    for index, figure in enumerate(figures, 1):
        if not isinstance(figure, dict):
            raise InputError(f"figures[{index - 1}] 不是对象")
        figure_no = str(figure.get("figure_no") or "")
        if figure_no != f"5.{index}":
            issues.append(_issue(
                "figure_number_mismatch",
                f"manifest 图号不连续：第 {index} 条应为 5.{index}，实际 {figure_no!r}",
                figure_no,
            ))
            clear_all_entries = True
        caption = str(figure.get("caption") or "").strip()
        if not CAPTION_RE.match(caption):
            issues.append(_issue(
                "caption_invalid",
                f"manifest 图注形态不合法: {caption!r}",
                figure_no,
                caption,
            ))
            clear_all_entries = True
        if not caption.startswith(f"图5.{index} "):
            issues.append(_issue(
                "caption_invalid",
                f"manifest 图号与图注不一致：figure_no=5.{index}，caption={caption}",
                figure_no,
                caption,
            ))
            clear_all_entries = True
        if caption in seen_captions:
            issues.append(_issue(
                "caption_duplicate",
                f"manifest 存在重复图注: {caption}",
                figure_no,
                caption,
            ))
            clear_all_entries = True
        seen_captions.add(caption)
        captions.append(caption)

        status = str(figure.get("status") or "available").strip().lower()
        if status == "missing":
            issues.append(_issue(
                "manifest_missing_status",
                str(figure.get("reason") or "本次未生成该图"),
                figure_no,
                caption,
            ))
            continue

        figure_ok = True
        try:
            src = str(figure.get("src") or "")
            target = resolve_project_src(project, src)
        except InputError as exc:
            issues.append(_issue(
                "chart_path_invalid", str(exc), figure_no, caption
            ))
            figure_ok = False
            target = None
            src = str(figure.get("src") or "")
        if figure_ok and not target.is_file():
            issues.append(_issue(
                "chart_file_missing",
                f"{caption} 的图文件不存在: {src}",
                figure_no,
                caption,
            ))
            figure_ok = False
        if figure_ok:
            expected_hash = str(figure.get("sha256") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                issues.append(_issue(
                    "chart_hash_invalid",
                    f"{caption} 缺有效 sha256",
                    figure_no,
                    caption,
                ))
                figure_ok = False
            else:
                actual_hash = sha256(target)
                if actual_hash != expected_hash:
                    issues.append(_issue(
                        "chart_hash_mismatch",
                        f"{caption} 的图文件已变化：manifest={expected_hash[:12]}…，"
                        f"实际={actual_hash[:12]}…",
                        figure_no,
                        caption,
                    ))
                    figure_ok = False
        if figure_ok:
            safe_entries.append({
                "caption": caption,
                "src": src.replace("\\", "/"),
                "sha256": str(figure["sha256"]).strip().lower(),
            })

    try:
        md_captions = chapter5_captions(project / "chapter_md" / "ch5_import.md")
    except InputError as exc:
        issues.append(_issue("markdown_missing", str(exc)))
        md_captions = []
        clear_all_entries = True
    except BindingError as exc:
        issues.append(_issue("markdown_invalid", str(exc)))
        md_captions = []
        clear_all_entries = True
    if md_captions != captions:
        issues.append(_issue(
            "caption_mismatch",
            "第5章装配稿图注与本次生成清单不一致："
            f"md={md_captions}；manifest={captions}",
        ))
        clear_all_entries = True
    if clear_all_entries:
        safe_entries = []
    return manifest, figures, safe_entries, issues


def merge_missing_items(project: Path, issues: list[dict]):
    path = project / MISSING_ITEMS_NAME
    if path.is_file():
        payload = read_json(path)
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise InputError(f"{path} 的 items 必须是数组")
    else:
        payload = {"items": []}
        items = []

    known = {
        (
            str(item.get("field") or ""),
            str(item.get("label") or ""),
            str(item.get("reason") or ""),
        )
        for item in items
        if isinstance(item, dict)
    }
    for issue in issues:
        figure_no = str(issue.get("figure_no") or "").strip()
        caption = str(issue.get("caption") or "").strip()
        label = (
            f"图{figure_no}" if figure_no
            else caption.split(" ", 1)[0] if caption
            else "第5章图表"
        )
        field = (
            "chapter5_figure_" + figure_no.replace(".", "_")
            if figure_no else "chapter5_figure_pipeline"
        )
        reason = str(issue.get("reason") or "")
        key = (field, label, reason)
        if key in known:
            continue
        items.append({
            "field": field,
            "label": label,
            "location": "第5章",
            "reason": reason,
        })
        known.add(key)
    payload["items"] = items
    atomic_write_json(path, payload)


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
    parser.add_argument(
        "--policy",
        choices=("placeholder", "strict"),
        default="placeholder",
        help="placeholder=登记问题并继续，strict=发现问题即退出 2",
    )
    parser.add_argument("--quiet", action="store_true", help="只在异常时输出")
    args = parser.parse_args(argv)

    def say(*values):
        if not args.quiet:
            print(*values)

    try:
        project = resolve_project_dir(args.project)
        manifest, figures, entries, issues = validate(project)
    except InputError as exc:
        print(f"[错误] {exc}")
        return 1
    except BindingError as exc:
        print(f"[错误] {exc}")
        return 2

    say(
        f"[校验] 图5共 {len(figures)} 条，可信 {len(entries)} 条，"
        f"问题 {len(issues)} 条"
    )
    for issue in issues:
        say(
            f"  ! {issue.get('figure_no') or '批次'} "
            f"{issue.get('code')}: {issue.get('reason')}"
        )
    if args.policy == "strict" and issues:
        say("[strict] 第5章图表存在问题，按严格策略阻断")
        return 2
    if args.check or args.dry_run:
        for entry in entries:
            say(f"  · {entry['caption']}  <=  {entry['src']}")
        say(
            "[dry-run] 未写入 report_images.json"
            if args.dry_run else "[check] 完成"
        )
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
    atomic_write_json(project / ISSUES_NAME, {
        "policy": args.policy,
        "batch_id": (
            manifest.get("batch_id") if isinstance(manifest, dict) else ""
        ),
        "issues": issues,
    })
    try:
        merge_missing_items(project, issues)
    except InputError as exc:
        print(f"[错误] {exc}")
        return 1
    say(
        f"[清单] 可信图5条目 {len(entries)} 条已写入 {path}；"
        f"替换旧图5条目 {len(old) - len(kept)} 条，保留其他条目 {len(kept)} 条"
    )
    say(f"[问题] {len(issues)} 条已写入 {project / ISSUES_NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
