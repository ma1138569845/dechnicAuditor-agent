#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""防抄查重 CLI（editor 终审手动用）：生成稿 vs 一份或多份参考报告。

用法:
    python similarity_check.py <生成稿.md|txt> <参考1.md|txt> [参考2.txt ...]

输出：每份参考的 lcs_ratio / ngram_overlap / 最长连续相同 / 匹配片段，以及
总体是否通过。阈值与 rules 见 energy-audit-style/references/anti-copy-gate.md。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[3]  # skills/energy-audit/energy-audit-style/scripts → repo 根
_TOOLS = _REPO / "tools"

sys.path.insert(0, str(_TOOLS.parent))

from tools.energy_audit.similarity_gate import (  # noqa: E402
    check_similarity,
    format_flags,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成稿 vs 参考报告 防抄查重")
    parser.add_argument("generated", help="生成稿路径（.md/.txt）")
    parser.add_argument("references", nargs="+", help="参考报告路径（可多个）")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)

    gen_path = Path(args.generated)
    if not gen_path.exists():
        print(f"[similarity_check] 生成稿不存在: {gen_path}", file=sys.stderr)
        return 1

    refs = []
    for r in args.references:
        p = Path(r)
        if not p.exists():
            print(f"[similarity_check] 参考文件不存在: {p}", file=sys.stderr)
            return 1
        refs.append(p.read_text(encoding="utf-8", errors="replace"))

    generated = gen_path.read_text(encoding="utf-8", errors="replace")
    report = check_similarity(generated, refs)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_flags(report))
        if report and report["violations"]:
            print("\n疑似复述片段：")
            for v in report["violations"][:10]:
                print(f"  [{v['length']}字] {v['matched']}")
    return 0 if not report or report.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
