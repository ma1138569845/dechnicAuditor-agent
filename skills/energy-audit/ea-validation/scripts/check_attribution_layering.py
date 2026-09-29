#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_attribution_layering.py — 5.2「归因下沉」机械检查（律 1）

检查对象：第5章装配稿（`<项目>/chapter_md/ch5_import.md`，缺则 `chapter5.md`）。

判据（`energy-audit-style/references/rules.md`《归因下沉三律》律 1）：
    各能源品种的**总量图**（图注含"总…量"且不含"逐月"）之后那一段，
    只允许出现增量 / 增减率 / 波动区间 / 极值；
    出现"由于／因为／受…影响／与…有关／原因／导致"等归因词即判不合格。

定位方式用**结构**而非语义猜测：图注 → 紧随其后的第一个正文段 = 段2（年际解析段）。
标题含"费用"的子节跳过（费用段的原因句通常指数据可得性，属合法）。

用法：
    python check_attribution_layering.py <项目名>            # 查 ~/projects/energy-audit/<项目名>/
    python check_attribution_layering.py --file <chapter5.md> # 直接给文件
    python check_attribution_layering.py <项目名> --quiet     # 只打印结论行

退出码：0 = 未发现越级归因（或未找到可检查段落）；1 = 有命中；2 = 入参/文件问题。

⚠️ 定位（2026-09-29 更新）：**已接入 datava REPORT_REVIEW 自动闸门**——
    `datava/mode_report_review.py::check_attribution_layering()` 直接复用本脚本的
    `resolve_source` / `scan`，命中记 **P1（待修，不阻塞交付）**；本脚本仍可独立跑做单点排查。
    语义判断留给 editor 终审，本脚本只抓"图注后第一段带归因词"这一种最明确的越级形态。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 归因词（律 1 的判据）。两族：
#  ① 因果连词："由于/因为/原因/导致…"——显式把结果挂到某个因上；
#  ② 成效语："成效/见效/归功…"——把变化挂到某项管理或措施上（隐含归因，
#     实测样例：「用水水平逐年改善，节水管理成效逐步显现」，无①族词但同样越级）。
ATTRIB_WORDS = ("由于", "因为", "原因", "导致", "造成", "有关", "影响",
                "得益于", "归因", "源于", "致使", "系因", "受制于",
                "成效", "见效", "归功", "发挥作用", "效果显现")

# 豁免语境：不是"断言归因"，而是"提请核实"——判据词附近出现这些词时不算命中。
# 实测样例：「建议进一步核实用气增长原因及燃气计量准确性」含"原因"但语义相反。
EXEMPT_NEAR = ("核实", "待核", "不明", "待查", "未知", "未见", "无需")
EXEMPT_WINDOW = 10

_H3_RE = re.compile(r"^###\s+(5\.2\.\d+)\s*(.*)$")
_H2_RE = re.compile(r"^##\s+(5\.\d+)\s*(.*)$")
_CAPTION_RE = re.compile(r"^\s*(?:!\[)?\s*图\s*5\.\d+\s*(.*?)\s*\]?(?:\(.*\))?\s*$")
_TABLE_RE = re.compile(r"^\s*\|")


def projects_root() -> Path:
    env = os.environ.get("HERMES_PROJECTS_ROOT")
    return Path(env) if env else Path.home() / "projects" / "energy-audit"


def resolve_source(project: str = "", file: str = "") -> Path:
    if file:
        return Path(file)
    pdir = projects_root() / project / "chapter_md"
    for name in ("ch5_import.md", "chapter5.md"):
        cand = pdir / name
        if cand.is_file():
            return cand
    return pdir / "ch5_import.md"          # 不存在时由调用方报错


def is_total_caption(text: str) -> bool:
    """总量图注：含"总"且不含"逐月"（逐月图注形如"逐月用电量"）。"""
    return "总" in text and "逐月" not in text


def find_attrib(text: str) -> list[str]:
    """返回真正的归因词（剔除"提请核实"语境）。"""
    bad = []
    for w in ATTRIB_WORDS:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            win = text[max(0, i - EXEMPT_WINDOW): i + len(w) + EXEMPT_WINDOW]
            if not any(e in win for e in EXEMPT_NEAR):
                bad.append(w)
                break
            start = i + len(w)
    return bad


def scan(lines: list[str]) -> tuple[list[dict], list[str]]:
    """返回（命中列表, 已检查段落描述）。"""
    hits: list[dict] = []
    checked: list[str] = []
    section = ""
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m3 = _H3_RE.match(line)
        if m3:
            section = f"{m3.group(1)} {m3.group(2).strip()}"
        else:
            m2 = _H2_RE.match(line)
            if m2:
                section = f"{m2.group(1)} {m2.group(2).strip()}"
                # 进入 5.3/5.4 后不再有 5.2 的图注，保持 section 仅用于报告定位
        cap = _CAPTION_RE.match(line)
        if cap and is_total_caption(cap.group(1)) and section.startswith("5.2"):
            # 图注后第一个正文段（跳过空行/表格/图注/标题）
            j = i + 1
            while j < n:
                nxt = lines[j]
                if not nxt.strip() or _TABLE_RE.match(nxt) or _CAPTION_RE.match(nxt) \
                        or nxt.lstrip().startswith("#"):
                    j += 1
                    continue
                break
            if j < n:
                para = lines[j].strip()
                if "费用" in section:
                    checked.append(f"{section} → 跳过（费用节）")
                else:
                    bad = find_attrib(para)
                    checked.append(f"{section} → 图注后段 {len(para)} 字"
                                   + (f"，命中归因词 {'、'.join(bad)}" if bad else "，干净"))
                    if bad:
                        hits.append({"section": section, "line": j + 1,
                                     "words": bad, "text": para})
        i += 1
    return hits, checked


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description="5.2 归因下沉机械检查（律 1）")
    ap.add_argument("project", nargs="?", default="", help="项目名（读 <项目>/chapter_md/ch5_import.md）")
    ap.add_argument("--file", default="", help="直接指定第5章 md 文件")
    ap.add_argument("--quiet", action="store_true", help="只打印结论行")
    args = ap.parse_args(argv)

    if not args.project and not args.file:
        print("[用法] python check_attribution_layering.py <项目名> 或 --file <ch5.md>")
        return 2

    src = resolve_source(args.project, args.file)
    if not src.is_file():
        print(f"[错误] 找不到第5章文件：{src}")
        return 2

    lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
    hits, checked = scan(lines)

    if not args.quiet:
        print(f"[文件] {src}")
        print("[已检查] （判据：总量图注后第一段不得含归因词）")
        for c in checked or ["（未找到 5.2 的总量图注，跳过）"]:
            print(f"  · {c}")
    if hits:
        print(f"\n[不合格] {len(hits)} 处越级归因（律 1）：")
        for h in hits:
            print(f"  ✗ {h['section']}（第 {h['line']} 行）命中：{'、'.join(h['words'])}")
            print(f"      {h['text'][:120]}{'…' if len(h['text']) > 120 else ''}")
        print("\n  处置：把归因移到该品种的逐月段（图5.N+1 之后），只挂设备形式或现场事件；"
              "挂不上改写「成因待核实」。")
        print("  依据：energy-audit-style/references/rules.md《归因下沉三律》律 1。")
        return 1

    print("\n[PASS] 未发现段2 越级归因。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
