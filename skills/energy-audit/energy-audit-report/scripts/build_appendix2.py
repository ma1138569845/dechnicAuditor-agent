#!/usr/bin/env python3
"""按"合计＝年度登记值、尾差并入 12 月"重建/校验附录2（2026-09-29 用户定，选项 C）。

背景（为什么需要这个脚本）
--------------------------
附录2 的「合计」行 = 12 个月相加（元/用量，2 位小数）；
而正文第5章、第8章引用的年度能源费用取平台**年度登记值**（万元，存 4 位小数）。
两条路径精度不同 → 合计与年度值对不上。实测三份报告：

    中医医院   2023 电费  逐月合计 1,350,299.53 元  vs 年度 135.0300 万元=1,350,300.00 元  差 −0.47
    烟台法院   2024 电费  逐月合计   752,854.00 元  vs 年度  75.2861 万元=  752,861.00 元  差 −7.00
    （其余多为 ±0.5 元以内）

而 `script-assembly-chain.md` 本来就写着铁律「**合计必须与正文第5章费用表及年度用量一致**」——
即现状是**违反包内规则**。用户 2026-09-29 选定处置口径 **C：尾差调进 12 月**（会计惯例"尾差入末月"），
使 `12 个月相加 ≡ 合计行 ≡ 年度登记值`，做到账表相符。

用法
----
    python build_appendix2.py <项目名或项目目录>          # 重建附录2
    python build_appendix2.py <项目名或项目目录> --check   # 只校验，不改文件

退出码：0 = 通过 / 已重建；2 = 校验发现合计与年度值不一致。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HEAD = ["月份", "水量(m³)", "水费(元)", "水单价(元/m³)",
        "电量(kWh)", "电费(元)", "电单价(元/kWh)"]

# (表内列序, 逐月用量键, 逐月费用键, 年度用量键, 年度费用键（万元）)
SERIES = [
    ("water", "monthly_water_m3", "monthly_water_cost", "water_m3", "water_cost_wan"),
    ("elec", "monthly_electricity_kwh", "monthly_electricity_cost",
     "electricity_kwh", "electricity_cost_wan"),
]
GAS = ("monthly_natural_gas_m3", "natural_gas_m3")

Q = Decimal("0.01")


def d(v) -> Decimal:
    """转 Decimal（容忍 None/空串/字符串数字）。"""
    if v in (None, ""):
        return Decimal(0)
    return Decimal(str(v))


def money(v: Decimal) -> str:
    return f"{v.quantize(Q, rounding=ROUND_HALF_UP):,.2f}"


def price(cost: Decimal, vol: Decimal) -> str:
    if not vol:
        return "—"
    return f"{(cost / vol).quantize(Q, rounding=ROUND_HALF_UP):,.2f}"


def balance(months: list[Decimal], annual: Decimal) -> tuple[list[Decimal], Decimal]:
    """把"年度值 − 逐月合计"的尾差调进最后一个月（12 月）。"""
    months = [m.quantize(Q, rounding=ROUND_HALF_UP) for m in months]
    residual = (annual - sum(months)).quantize(Q, rounding=ROUND_HALF_UP)
    out = list(months)
    if months and residual != 0:
        out[-1] = (out[-1] + residual).quantize(Q, rounding=ROUND_HALF_UP)
    # 调完之后再核一次（避免 quantize 反噬）
    gap = (annual - sum(out)).quantize(Q, rounding=ROUND_HALF_UP)
    if out and gap != 0:
        out[-1] = (out[-1] + gap).quantize(Q, rounding=ROUND_HALF_UP)
    return out, residual


def _pad12(seq: list) -> list:
    return list(seq or []) + [None] * max(0, 12 - len(seq or []))


def build_year_table(year: dict, idx: int, report: list) -> tuple[str, list]:
    """生成一张逐月表的 md 文本；返回 (文本, 尾差明细)。"""
    yr = year.get("year")
    gas_seq = _pad12(year.get(GAS[0]))
    has_gas = any(d(v) > 0 for v in gas_seq)

    cols: dict[str, list[Decimal]] = {}
    ann: dict[str, Decimal] = {}
    for key, mk, ck, yk, yc in SERIES:
        cols[key] = [d(v) for v in _pad12(year.get(mk))]
        cols[f"{key}_cost"] = [d(v) for v in _pad12(year.get(ck))]
        ann[key] = d(year.get(yk))
        ann[f"{key}_cost"] = (d(year.get(yc)) * 10000)
    if has_gas:
        cols["gas"] = [d(v) for v in gas_seq]
        ann["gas"] = d(year.get(GAS[1]))

    residuals = []
    for key in ("water", "elec", "gas"):
        if key not in cols:
            continue
        cols[key], r1 = balance(cols[key], ann[key])
        # 燃气只有用量列（表内无「气费」列）→ 无费用列可调
        if f"{key}_cost" in cols:
            cols[f"{key}_cost"], r2 = balance(cols[f"{key}_cost"], ann[f"{key}_cost"])
        else:
            r2 = Decimal(0)
        for label, r in (("用量", r1), ("费用", r2)):
            if r:
                residuals.append((yr, key, label, r))
                report.append(f"  {yr} {key} {label} 尾差 {r} 元/单位 → 调进 12 月")

    lines = [f"附表2-{idx} {yr}年逐月能源资源消耗及费用统计表", ""]
    head = HEAD + (["天然气(m³)"] if has_gas else [])
    lines.append("| " + " | ".join(head) + " |")
    lines.append("|" + "---|" * len(head))
    for i in range(12):
        row = [f"{i + 1}月",
               money(cols["water"][i]), money(cols["water_cost"][i]),
               price(cols["water_cost"][i], cols["water"][i]),
               money(cols["elec"][i]), money(cols["elec_cost"][i]),
               price(cols["elec_cost"][i], cols["elec"][i])]
        if has_gas:
            row.append(money(cols["gas"][i]))
        lines.append("| " + " | ".join(row) + " |")
    total = ["合计", money(ann["water"]), money(ann["water_cost"]), "—",
             money(ann["elec"]), money(ann["elec_cost"]), "—"]
    if has_gas:
        total.append(money(ann["gas"]))
    lines.append("| " + " | ".join(total) + " |")
    return "\n".join(lines) + "\n", residuals


def split_apx2(md: str) -> tuple[int, int] | None:
    m0 = re.search(r"^## 附录2：.*$", md, re.M)
    if not m0:
        return None
    m1 = re.search(r"^## 附录(?!2：).*$", md[m0.end():], re.M)
    end = m0.end() + (m1.start() if m1 else len(md) - m0.end())
    return m0.start(), end


def keep_summary(old_span: str) -> str:
    """保留原有的"三年…汇总表"，表号顺延为附表2-4。"""
    om = re.search(
        r"(附表2-\d+\s*[^\n]*汇总[^\n]*\n\n?\|[^\n]+\|\n\|[-| ]+\|\n(?:\|[^\n]+\|\n)+)",
        old_span)
    if not om:
        return ""
    return re.sub(r"^附表2-\d+", "附表2-4", om.group(1).strip()) + "\n"


def verify(appendix_md: str, data: dict) -> list[str]:
    """校验附录2 每张表的合计行 = 年度登记值。返回违规清单（空=通过）。"""
    span = split_apx2(appendix_md)
    if not span:
        return ["附录2 段落未找到"]
    seg = appendix_md[span[0]:span[1]]
    bad = []
    for year in (data.get("energy_yearly") or []):
        yr = year.get("year")
        m = re.search(rf"^附表2-\d+\s*{yr}年逐月.*?$", seg, re.M)
        if not m:
            bad.append(f"{yr}: 未找到该年逐月表")
            continue
        rows = [ln for ln in seg[m.end():].splitlines() if ln.strip().startswith("|")]
        total = next((r for r in rows if r.split("|")[1].strip() == "合计"), None)
        if not total:
            bad.append(f"{yr}: 无合计行")
            continue
        cells = [c.strip().replace(",", "") for c in total.split("|")[1:-1]]
        want = [d(year.get("water_m3")), d(year.get("water_cost_wan")) * 10000,
                "—", d(year.get("electricity_kwh")),
                d(year.get("electricity_cost_wan")) * 10000, "—"]
        for i, (got, exp) in enumerate(zip(cells[1:], want), start=0):
            if exp == "—":
                continue
            try:
                gv = Decimal(got)
            except Exception:  # noqa: BLE001
                bad.append(f"{yr}: 合计第{i + 1}列不是数字（{got}）")
                continue
            if abs(gv - exp) > Decimal("0.005"):
                bad.append(f"{yr}: 合计第{i + 1}列 {gv} ≠ 年度 {exp}")
    return bad


def resolve(project: str) -> Path:
    p = Path(project)
    if p.is_dir():
        return p
    return Path.home() / "projects" / "energy-audit" / project


def main() -> int:
    ap = argparse.ArgumentParser(description="按『合计＝年度登记值、尾差并入 12 月』重建/校验附录2")
    ap.add_argument("project", help="项目名（~/projects/energy-audit/<名>）或项目目录")
    ap.add_argument("--check", action="store_true", help="只校验，不改文件")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    pdir = resolve(args.project)
    data = json.loads((pdir / "data.json").read_text(encoding="utf-8"))
    ap_md = pdir / "chapter_md" / "appendix.md"
    md = ap_md.read_text(encoding="utf-8")

    if args.check:
        bad = verify(md, data)
        for b in bad:
            print(f"  ✗ {b}")
        print(f"[{'PASS' if not bad else 'FAIL'}] 附录2 合计与年度登记值一致"
              f"（违规 {len(bad)} 项）")
        return 0 if not bad else 2

    span = split_apx2(md)
    if not span:
        print("未找到『## 附录2：』段落，已中止")
        return 1
    summary = keep_summary(md[span[0]:span[1]])
    report: list[str] = []
    parts = ["## 附录2：建筑能耗数据信息表", ""]
    years = sorted((data.get("energy_yearly") or []), key=lambda r: r.get("year") or 0)
    for idx, year in enumerate(years, start=1):
        text, _ = build_year_table(year, idx, report)
        parts.append(text)
    if summary:
        parts.append(summary.rstrip())
        parts.append("")
    new_md = md[:span[0]] + "\n".join(parts) + md[span[1]:]

    bad = verify(new_md, data)
    if bad:
        print("重建后自检未通过，**未写文件**：")
        for b in bad:
            print(f"  ✗ {b}")
        return 2

    (ap_md.parent / "appendix.md.bak-20260929-tieout").write_text(md, encoding="utf-8")
    ap_md.write_text(new_md, encoding="utf-8")
    print(f"附录2 已重建（{len(years)} 张逐月表）→ {ap_md}")
    for line in report:
        print(line)
    if not report:
        print("  （无尾差：逐月合计本就等于年度登记值）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
