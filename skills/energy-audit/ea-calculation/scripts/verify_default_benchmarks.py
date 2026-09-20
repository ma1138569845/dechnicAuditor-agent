#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_default_benchmarks.py — 「内置默认定额」与权威单点的一致性机检（2026-09-20 新增）

背景：2026-09-20 起定额**取值链 = 用户显式值 > 内置默认**，DB ts_limit_config 退出取值链，
      只做交叉校验。于是 `tools/energy_audit/indicators.py::_DEFAULT_BENCHMARKS`
      成了 `energy-audit-core/references/standards-values.md` 的**代码镜像**——
      两边一旦漂移（改了一边忘了另一边），报告就会取到与权威文件不符的值。

本脚本把这条要求变成可机检：
  A. 把 standards-values.md 按「标准」切块，抽出每块里所有「3 个数一组」的三档值；
  B. 遍历 _DEFAULT_BENCHMARKS 的每一项，按机构类型找对应标准块，要求该三档值在块内出现；
     用水指标（两档：通用值/先进值）只在 DB37/T 4452 块内比对前两位。

用法:
    python verify_default_benchmarks.py [--standards <path>] [--quiet]

退出码: 0 = 全部可溯源；1 = 存在代码有、文档无（或反之）的漂移
"""
from __future__ import annotations

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_repo_root(start: str) -> str:
    """向上查找含 tools/energy_audit/indicators.py 的仓库根。"""
    cur = os.path.abspath(start)
    for _ in range(8):
        if os.path.isfile(os.path.join(cur, "tools", "energy_audit", "indicators.py")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


ROOT = find_repo_root(SCRIPT_DIR) or find_repo_root(os.getcwd())
DEFAULT_STD = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "energy-audit-core", "references", "standards-values.md"))

# 机构类型 → 应比对的标准号（去空格/连字符后归一）
INST_STD = {
    "government": "DB37/T2672-2019",
    "medical": "DB37/T2673-2019",
    "education": "DB37/T2671-2019",
    "venue": "DB37/T3780-2019",
}
WATER_STD = "DB37/T4452-2021"

# 数值之间允许：空白 / 分隔符 / markdown 强调符 / 中文标签词
# （文档里既有 "| 16.5 | 10.0 | 7.5 |" 也有 "19.6/15.4/12.4" 和 "约束 2.2 / 基准 1.8 / 引导 1.4"）
LABELS = r"约束值|基准值|引导值|先进值|通用值|约束|基准|引导|先进|通用|值"
SEP = (r"(?:[^\S\r\n]|[/|｜]|—|–|-|\*|_|`|：|:|" + LABELS + r")*")
NUM = r"-?\d+(?:\.\d+)?"
TRIPLE_RE = re.compile(rf"(?<![\d.]){NUM}{SEP}{NUM}{SEP}{NUM}(?![\d.])")
PAIR_RE = re.compile(rf"(?<![\d.]){NUM}{SEP}{NUM}(?![\d.])")


def norm_num(x) -> str:
    try:
        return f"{float(x):g}"
    except (TypeError, ValueError):
        return str(x)


def triple(x) -> str:
    return "/".join(norm_num(v) for v in x[:3])


def norm_std(text: str) -> str:
    t = str(text or "").replace(" ", "").replace("—", "-").replace("–", "-")
    t = t.replace("／", "/").replace("T　", "T")
    return t.upper()


def split_by_standard(text: str):
    """按含 DB37 的标题行把文档切块 → {'DB37/T2673-2019': 该块正文, ...}"""
    blocks, cur_key, buf = {}, None, []
    for line in text.splitlines():
        if line.lstrip().startswith("#") and "DB37" in line:
            if cur_key:
                blocks.setdefault(cur_key, "")
                blocks[cur_key] += "\n".join(buf)
            m = re.search(r"(DB37\s*/?\s*T?\s*\d+\s*[-—]\s*\d{4})", line)
            cur_key = norm_std(m.group(1)) if m else None
            buf = []
        else:
            buf.append(line)
    if cur_key:
        blocks.setdefault(cur_key, "")
        blocks[cur_key] += "\n".join(buf)
    return {k: v for k, v in blocks.items() if k}


def tokens(block: str):
    trips = {"/".join(norm_num(n) for n in re.findall(NUM, m.group(0)))
             for m in TRIPLE_RE.finditer(block)}
    # 两档值用**无序集合**比对：文档写"先进值 | 通用值"，代码存 (通用值, 先进值)，顺序相反
    pairs = {frozenset(norm_num(n) for n in re.findall(NUM, m.group(0))[:2])
             for m in PAIR_RE.finditer(block)}
    return trips, pairs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="内置默认定额 vs standards-values.md 一致性机检")
    ap.add_argument("--standards", default=os.environ.get("EA_STANDARDS_VALUES", DEFAULT_STD))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if not ROOT:
        print("[错误] 未找到仓库根（需含 tools/energy_audit/indicators.py）")
        return 1
    sys.path.insert(0, ROOT)
    from tools.energy_audit.indicators import _DEFAULT_BENCHMARKS as BM  # noqa: E402

    if not os.path.isfile(args.standards):
        print(f"[错误] 找不到权威文件：{args.standards}")
        return 1
    with open(args.standards, encoding="utf-8") as fh:
        doc = fh.read()
    blocks = split_by_standard(doc)
    if not args.quiet:
        print(f"=== 权威文件切块：{len(blocks)} 个标准 ===")
        for k in sorted(blocks):
            t, p = tokens(blocks[k])
            print(f"  {k:<18} 三档值 {len(t):>3} 组；两档值 {len(p):>3} 组")
    if not blocks:
        print("[错误] 未从权威文件切出任何标准块（标题格式变了？）")
        return 1

    water_pairs = tokens(blocks.get(WATER_STD, ""))[1] if blocks.get(WATER_STD) else set()
    problems, checked, skipped = [], 0, []
    for inst, spec in BM.items():
        std = INST_STD.get(inst)
        if not std:
            skipped.append(inst)
            continue
        blk = blocks.get(std, "")
        if not blk:
            problems.append(f"{inst}：权威文件中找不到标准块 {std}")
            continue
        trips, pairs = tokens(blk)
        for metric, val in spec.items():
            if metric in ("standard_name", "water_standard"):
                continue
            items = val.items() if isinstance(val, dict) else [("", val)]
            for key, item in items:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                checked += 1
                label = f"{inst}/{metric}" + (f"/{key}" if key else "")
                if metric.startswith("water"):
                    want = frozenset(norm_num(v) for v in item[:2])
                    if want not in water_pairs:
                        problems.append(
                            f"{label}：代码 {'/'.join(sorted(want))} 未在 {WATER_STD} 块内找到（用水两档应在 4452）")
                else:
                    want = triple(item)
                    if want not in trips:
                        problems.append(f"{label}：代码 {want} 未在 {std} 块内找到")

    if not args.quiet:
        print(f"\n=== 结论：比对 {checked} 组，{'全部一致' if not problems else str(len(problems)) + ' 处漂移'} ===")
        if skipped:
            print(f"  （跳过未收录标准的机构：{'、'.join(skipped)}——其内置值暂无权威文件可比对）")
    for p in problems:
        print(f"  ⚠️ {p}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
