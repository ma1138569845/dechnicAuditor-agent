#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_retrieval_evidence.py — 参考证据闸门（2026-09-20 新增，「钩子 2」）

## 治什么问题

写章契约里只留了一句"可以调用 `reference_library.search_local_references` /
`energy_audit_rag_search`"——**没有任何一步是必须检索**，检索结果也不留痕。
于是"有没有真去参考同类成稿/标准条文"纯靠模型自觉，不可检查。

## 怎么做（台账 + 闸门）

1. 写章前，`prepare_writing_context.py` 会生成/续写
   `<项目>/chapter_md/_retrieval_log.md`（登记台账，含表头与"必需登记章节"声明）；
2. 作者每查一次填一行：章 / 检索入口 / 命中来源 / 采用了什么 / 落到哪节；
3. 本脚本在 **S14** 跑，检查台账覆盖必需章、单元格填实、来源能在磁盘上找到。

## 判据

| 级别 | 条件 |
|---|---|
| **P0（阻塞交付）** | 台账文件缺失；必需章没有任何一行；某行的「检索入口」或「命中来源」为空 |
| **P1（提示）** | 命中行没写「采用了什么」；来源在本地参考库/标准库中找不到（可能记错文件名） |

> **合法无命中**：来源写「未命中：<原因>」即可——"查过了没有"本身就是证据，
> 只是不允许**空白**（空白区分不出"没查"和"忘了填"）。

用法:
    python verify_retrieval_evidence.py <项目名|项目目录> [--log <md>] [--json] [--quiet]

退出码: 0 = 无 P0（P1 仅提示）；1 = 存在 P0
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_CHAPTERS = ("第3章", "第6章", "第7章")
LOG_NAME = "_retrieval_log.md"
NO_HIT_OK = ("未命中", "无", "n/a", "不适用", "-", "—")


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit")


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "hermes" if local else Path.home() / ".hermes"


def known_sources() -> set:
    """本地参考库 / 标准归档 / 知识库根目录里真实存在的文件名集合（做来源存在性核对）。"""
    roots = [hermes_home() / "rag" / "report",
             hermes_home() / "rag" / "standards",
             hermes_home() / "rag" / "data"]
    names = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and not p.name.startswith("."):
                names.add(p.name)
    return names


def parse_log(text: str):
    """返回 (必需章列表, 表头列索引, 数据行列表)。"""
    chapters = list(DEFAULT_CHAPTERS)
    m = re.search(r"必需登记章节[：:]\s*(.+)", text)
    if m:
        # 模板里这句常带 markdown 强调（**…**、`…`），先剥掉再切
        raw = m.group(1).replace("*", "").replace("`", "").strip()
        items = [c.strip() for c in re.split(r"[、,，;；\s]+", raw) if c.strip()]
        if items:
            chapters = items

    rows, header = [], None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if all(re.fullmatch(r":?-{2,}:?", c or "-") for c in cells):
            continue
        rows.append(cells)
    return chapters, (header or []), rows


def col_index(header, *keywords) -> int:
    for i, h in enumerate(header):
        if any(k in h for k in keywords):
            return i
    return -1


def cell(row, idx) -> str:
    return row[idx].strip() if 0 <= idx < len(row) else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="参考证据闸门（S14）")
    ap.add_argument("project", help="项目名（~/projects/energy-audit/<项目名>）或项目目录")
    ap.add_argument("--log", default="", help=f"台账路径（默认 <项目>/chapter_md/{LOG_NAME}）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在：{args.project}（查找根 {projects_root()}）")
        return 1
    log_path = Path(args.log) if args.log else Path(pdir) / "chapter_md" / LOG_NAME

    p0, p1 = [], []
    detail = {"project": pdir, "log": str(log_path)}

    if not log_path.is_file():
        p0.append(f"缺检索证据台账：{log_path}"
                  f"（写章前跑 prepare_writing_context.py 会自动生成模板）")
        return report(p0, p1, detail, args)

    text = log_path.read_text(encoding="utf-8", errors="replace")
    chapters, header, rows = parse_log(text)
    ci = {
        "chapter": col_index(header, "章"),
        "entry": col_index(header, "入口"),
        "source": col_index(header, "来源", "命中"),
        "used": col_index(header, "采用"),
        "section": col_index(header, "落到", "节"),
    }
    if ci["chapter"] < 0 or ci["source"] < 0:
        p0.append("台账表头不合规：至少要有「章」与「命中来源」两列"
                  "（模板见 prepare_writing_context.py 生成的 "
                  f"{LOG_NAME}）")
        return report(p0, p1, detail, args)

    names = known_sources()
    filled, present = {}, set()
    for row in rows:
        ch = cell(row, ci["chapter"])
        if not ch:
            continue
        present.add(ch)
        entry = cell(row, ci["entry"]) if ci["entry"] >= 0 else ""
        src = cell(row, ci["source"])
        used = cell(row, ci["used"]) if ci["used"] >= 0 else ""
        others = [c for c in row[1:]]
        if not any(others):                     # 模板行整行没填 → 只报一条
            p0.append(f"{ch}：模板行未填（检索入口 / 命中来源 / 采用了什么 都是空的）")
            continue
        if not entry:
            p0.append(f"{ch}：这一行缺「检索入口」（写清用了哪个入口："
                      "search_local_references / energy_audit_rag_search(kbs=standards) / 其他）")
        if not src:
            p0.append(f"{ch}：这一行「命中来源」为空——查不到也要写「未命中：<原因>」，"
                      "空白区分不出'没查'和'忘了填'")
            continue
        is_hit = not any(k in src.lower() for k in NO_HIT_OK)
        if is_hit and not used:
            p1.append(f"{ch}：命中了 {src}，但没写「采用了什么」")
        if is_hit and names and not any(n and n in src for n in names):
            p1.append(f"{ch}：来源 `{src}` 在本地参考库/标准库/知识库根目录里找不到"
                      "（可能记错文件名，或来源已归档）")
        filled.setdefault(ch, []).append(src)

    for c in chapters:
        if c not in present:
            p0.append(f"必需登记章节 {c} 没有任何证据行"
                      f"（台账 {log_path.name}）")

    detail["required"] = chapters
    detail["rows"] = {c: len(filled.get(c, [])) for c in chapters}
    return report(p0, p1, detail, args)


def report(p0, p1, detail, args) -> int:
    if args.json:
        print(json.dumps({"p0": p0, "p1": p1, **detail}, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print("=" * 62)
        print(f"参考证据闸门　项目={detail['project']}")
        print(f"台账={detail['log']}")
        if detail.get("required"):
            print(f"必需章节={('、'.join(detail['required']))}"
                  f"　登记行数={detail.get('rows')}")
        print("=" * 62)
        for m in p0:
            print(f"  ✗ P0 {m}")
        for m in p1:
            print(f"  ⚠️ P1 {m}")
        if not p0 and not p1:
            print("  ✓ 通过：必需章均有证据，且来源可核对")
        print("\n=== 结论 ===")
        print(f"  P0 {len(p0)} 项；P1 {len(p1)} 项")
    return 1 if p0 else 0


if __name__ == "__main__":
    sys.exit(main())
