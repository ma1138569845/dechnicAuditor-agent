#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_chapter_md.py — 第5章装配稿就位器（消灭"手工搬运"断点）

背景：caliber 把第5章写在 `<项目>/chapter5.md`；装配脚本 `build_energy_audit_docx.py`
读的是 `<项目>/chapter_md/ch5_import.md`（优先匹配 `chN_import.md`）。中间这次搬运
过去没有任何脚本负责——忘放就会导致报告第5章为空。本脚本负责"检查 + 就位"，并且
**不覆盖**作者已并入叙述段的装配稿。

用法:
    python prepare_chapter_md.py <项目名|项目目录> [--force] [--quiet]

行为与退出码:
    0  已就位（本次新复制）/ 已有不早于计算产物的装配稿（保留）
    1  输入缺失（项目目录或 chapter5.md 找不到）
    2  装配稿早于计算产物（疑似用了旧数据）→ 人工确认后加 --force 覆盖

产物:
    <项目>/chapter_md/ch5_import.md
    <项目>/chapter_md/ch5_import.md.bak   （仅 --force 覆盖时保留上一版）
"""
import argparse
import os
import shutil
import sys


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit"
    )


def resolve_project_dir(arg: str) -> str:
    """参数可以是项目目录，也可以是项目名（在 HERMES_PROJECTS_ROOT 下查找）。"""
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="第5章装配稿就位器")
    ap.add_argument("project", help="项目名（对应 ~/projects/energy-audit/<项目名>/）或项目目录")
    ap.add_argument("--force", action="store_true", help="装配稿早于计算产物时强制覆盖")
    ap.add_argument("--quiet", action="store_true", help="只在异常时输出")
    args = ap.parse_args(argv)

    def say(*a):
        if not args.quiet:
            print(*a)

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在: {args.project}（查找根: {projects_root()}）")
        return 1

    src = os.path.join(pdir, "chapter5.md")
    if not os.path.isfile(src):
        print(f"[错误] 缺少计算产物: {src}（先跑 caliber_agent.py）")
        return 1

    md_dir = os.path.join(pdir, "chapter_md")
    os.makedirs(md_dir, exist_ok=True)
    dst = os.path.join(md_dir, "ch5_import.md")

    if not os.path.isfile(dst):
        shutil.copy2(src, dst)
        say(f"[就位] 已由计算产物生成装配稿: {dst}")
        return 0

    src_m, dst_m = os.path.getmtime(src), os.path.getmtime(dst)
    if dst_m >= src_m:
        say(f"[保留] 已有装配稿（不早于计算产物，视为已并入叙述段）: {dst}")
        return 0

    if not args.force:
        print(f"[警告] 装配稿早于计算产物，可能用了旧数据: {dst}")
        print(f"       计算产物: {src}（更新）")
        print("       确认无误后重跑并加 --force 覆盖，或手工并入叙述段后重跑本脚本确认。")
        return 2

    bak = dst + ".bak"
    shutil.copy2(dst, bak)
    shutil.copy2(src, dst)
    say(f"[覆盖] 已用计算产物覆盖装配稿（上一版备份: {bak}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
