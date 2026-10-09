#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机构类型映射「唯一权威 ↔ 代码副本」一致性校验（2026-10-08 收口）。

权威：skills/energy-audit/ea-calculation/references/chapter5-templates.md
      §5.3.1「机构类型映射」表（列：类型 | org_type | action_desc | special_note）
副本：tools/energy_audit/institution_org_map.py 的 ORG_MAP

用法：
    python verify_org_map.py                 # 用默认路径
    python verify_org_map.py --repo <仓库根>
退出码：0 = 一致；2 = 不一致（差异逐行打印）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LABEL_TO_KEY = {
    "医疗": "medical",
    "政务": "service",
    "场馆": "venue",
    "教育": "education",
    "党政": "government",
    "其他": "other",
}


def parse_templates_map(path: Path) -> dict:
    """从 markdown 表里取 {key: (org_type, action_desc, special_note)}。"""
    txt = path.read_text(encoding="utf-8")
    m = re.search(r"^#+\s*机构类型映射", txt, re.M)   # 认标题，别被正文里的同名提及带偏
    if not m:
        raise SystemExit("chapter5-templates.md 里找不到「#### 机构类型映射」小节")
    seg = txt[m.start():m.start() + 1500]
    out = {}
    for line in seg.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        label = cells[0]
        if label not in LABEL_TO_KEY:
            continue
        out[LABEL_TO_KEY[label]] = (cells[1], cells[2], cells[3])
    return out


def load_org_map(path: Path) -> dict:
    ns: dict = {}
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)  # noqa: S102
    return dict(ns["ORG_MAP"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"D:\data\pyProject\dc_agent\dechnicAuditor-agent")
    args = ap.parse_args()
    repo = Path(args.repo)
    tpl = repo / "skills/energy-audit/ea-calculation/references/chapter5-templates.md"
    mod = repo / "tools/energy_audit/institution_org_map.py"
    for p in (tpl, mod):
        if not p.is_file():
            print("[FAIL] 缺少文件：%s" % p)
            return 2

    doc = parse_templates_map(tpl)
    code = load_org_map(mod)
    bad = []
    for key in sorted(set(doc) | set(code)):
        a, b = doc.get(key), code.get(key)
        if a != b:
            bad.append("  %-11s 模板=%s  代码=%s" % (key, a, b))
    if bad:
        print("[FAIL] 机构类型映射不一致（%d 处）：" % len(bad))
        print("\n".join(bad))
        print("  权威文件：%s" % tpl)
        print("  代码副本：%s" % mod)
        return 2
    print("[OK] 机构类型映射一致：%d 行（%s）" % (len(doc), "、".join(sorted(doc))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
