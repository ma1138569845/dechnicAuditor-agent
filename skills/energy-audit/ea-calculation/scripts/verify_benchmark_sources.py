#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_benchmark_sources.py — 定额取值「原文锚点」溯源自检（2026-09-18 新增）

背景：报告里的定额三档值必须有**标准号 + 表号/条款**可溯源；历史上出现过
"取错气候区却标注来源：DB"的事故。本脚本把这条要求变成可机检：
  A. 权威单点 `energy-audit-core/references/standards-values.md` 的每张定额表是否都带 `★来源锚点`
  B. 项目 `indicators.json` 每个指标的 benchmark 是否带「标准 + 来源 + 可定位的锚点」
  C. 输出可直接粘进报告的「取值溯源清单」

用法:
    python verify_benchmark_sources.py <项目名|项目目录> [--quiet] [--json]

退出码: 0 = 全部可溯源；1 = 存在缺锚点/缺标准（沿用时请在第5章写【待核验】）
"""
import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STD = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "energy-audit-core", "references", "standards-values.md"
))
LABELS = {
    "unit_area_non_heating_energy": "单位建筑面积非供暖能耗",
    "unit_area_heating": "单位采暖建筑面积供暖能耗",
    "unit_area_electricity": "常规用能系统单位建筑面积电耗",
    "per_capita_energy": "人均综合能耗",
    "water_indicator": "取水指标",
}

# 指标 → 标准表号（DB37 各机构标准表结构一致：表1 非供暖 / 表2 供暖 / 表3 人均 / 表4 常规电耗 / 表5 EUE）
# 用水指标来自 DB37/T 4452-2021 表2（先进值/通用值）
EXPECTED_TABLE = {
    "unit_area_non_heating_energy": "1",
    "unit_area_heating": "2",
    "unit_area_electricity": "4",
    "per_capita_energy": "3",
    "water_indicator": "2",
}


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit"
    )


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def norm_std(text: str) -> str:
    """把标准名归一成可比较的号，如 DB37/T2673-2019。"""
    t = str(text or "").replace(" ", "").replace("—", "-").replace("–", "-")
    m = re.search(r"(DB\d+/T\d+-\d{4}|GB/?T?\d+[-.]?\d*)", t)
    return m.group(1).replace("GBT", "GB/T") if m else ""


def parse_anchors(path: str):
    """从 standards-values.md 解析 ★来源锚点 → {(标准号, 表号): 原文行}"""
    anchors = {}
    if not os.path.isfile(path):
        return anchors
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if "★来源锚点" not in line:
                continue
            std = norm_std(line)
            table = re.search(r"表\s*(\d+)", line)
            key = (std, table.group(1) if table else "")
            anchors[key] = i
    return anchors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="定额取值原文锚点溯源自检")
    ap.add_argument("project", nargs="?", help="项目名或项目目录（省略则只检查权威单点）")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--standards", default=os.environ.get("EA_STANDARDS_VALUES", DEFAULT_STD))
    args = ap.parse_args(argv)

    anchors = parse_anchors(args.standards)
    tables = sorted({k[1] for k in anchors if k[1]})
    stds = sorted({k[0] for k in anchors if k[0]})
    report = {"authority_file": args.standards, "anchor_count": len(anchors),
              "standards": stds, "tables": tables, "project": None, "items": [], "problems": []}

    if not args.quiet:
        print(f"=== A. 权威单点锚点：{os.path.basename(args.standards)} ===")
        print(f"  识别到 {len(anchors)} 条锚点，覆盖标准 {len(stds)} 个、表 {len(tables)} 张：{'/'.join(tables)}")
    if not anchors:
        report["problems"].append(f"权威单点未找到 ★来源锚点：{args.standards}")

    if args.project:
        pdir = resolve_project_dir(args.project)
        if not pdir:
            print(f"[错误] 项目目录不存在：{args.project}")
            return 1
        ind_path = os.path.join(pdir, "indicators.json")
        try:
            with open(ind_path, encoding="utf-8") as fh:
                ind = json.load(fh)
        except (OSError, json.JSONDecodeError):
            print(f"[错误] 缺或无法解析 indicators.json：{ind_path}（先跑 caliber_agent.py）")
            return 1
        report["project"] = ind.get("project")

        if not args.quiet:
            print(f"\n=== B. 项目取值溯源：{ind.get('project')}（{ind.get('year')}）===")
            print(f"  {'指标':<22}{'值':>10}  {'标准':<34}{'锚点':<12}{'来源'}")
        for key, label in LABELS.items():
            node = ind.get(key)
            if not isinstance(node, dict):
                continue
            bench = node.get("benchmark") or {}
            std_raw = bench.get("标准") or ""
            std = norm_std(std_raw)
            anchor_field = bench.get("锚点") or bench.get("原文锚点") or ""
            exp_table = EXPECTED_TABLE.get(key, "")
            expected_anchor = (std, exp_table) in anchors
            hit = [f"表{t}" for (s, t) in sorted(anchors) if s == std and t]
            if anchor_field:
                anchor_show, status = anchor_field, "ok"
            elif expected_anchor:
                anchor_show, status = f"可定位(表{exp_table})", "derivable"
            else:
                anchor_show, status = "缺", "missing"
            value = next((node[k] for k in ("kgce_per_m2", "kgce_per_person", "kwh_per_m2", "value")
                          if isinstance(node.get(k), (int, float))), None)
            item = {"key": key, "label": label, "value": value,
                    "standard": std_raw, "standard_norm": std,
                    "expected_table": exp_table,
                    "anchor": anchor_field or (f"表{exp_table}" if expected_anchor else ""),
                    "available_tables": hit,
                    "source": bench.get("来源") or "", "comment": bench.get("评价结果") or "",
                    "status": status}
            report["items"].append(item)
            if status == "missing":
                report["problems"].append(
                    f"{label}：未定位到原文锚点（标准='{std_raw or '空'}'，期望 表{exp_table or '?'}）；"
                    "若因数据缺失未生成指标属已知缺失，否则请补 `standards-values.md` 锚点或在第5章标【待核验】"
                )
            if not args.quiet:
                print(f"  {label:<22}{str(value):>10}  {std_raw[:32]:<34}{anchor_show:<12}{bench.get('来源') or '—'}")

        if not args.quiet and report["items"]:
            print("\n=== C. 取值溯源清单（可直接粘进第5章/1.6 的溯源说明）===")
            for it in report["items"]:
                anchor = it["anchor"] or "【缺锚点，需补】"
                print(f"  - {it['label']}：{it['standard'] or '【缺标准】'} {anchor}（来源：{it['source'] or '—'}）")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    ok = not report["problems"]
    if not args.quiet:
        print(f"\n=== 结论：{'通过（全部可溯源）' if ok else '存在 ' + str(len(report['problems'])) + ' 处待补'} ===")
        for p in report["problems"]:
            print(f"  ⚠️ {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
