#!/usr/bin/env python3
"""第7章「依据锚点」机械闸（2026-09-29 用户定，决策 3-A）。

检查三件事（前两项是硬闸，后两项只提示）：
  ① 标题零条文：7.1 标题句（`（N）` 后首句）与 7.2 的 `7.2.N` 小标题，
     不得出现标准号（GB / DB37 / 《 / 》）或括注 `（`。
  ② 引用形态：正文禁止括注式（`（出自` / `（详见` / `（来源` / `（引自`）与泛引
     （`依据相关标准`）；引了标准就必须给**条文号**（`第X.X.X条`）。
  ③（提示）每条最多引 1 部标准；某条引了标准却没给条文号 → 提示补全。
  ④（提示）逐条列出"有无锚点"（标准号/带单位数值/原理词），供人工判断**能引未引**。
     ⚠️ 锚点是"择优"不是"强制"：**没有锚点不判不合格**（用户 2026-09-29 定）。

用法：python check_chapter7_anchors.py <项目名或项目目录> [--quiet]
退出码：0 = 硬闸通过（含仅有提示）；2 = 硬闸不合格；1 = 输入缺失
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# —— 标题禁用：标准号与括注
TITLE_BAD = re.compile(r'(GB|DB37|《|》|（|\(|【)')
# —— 正文禁用：括注式出处 / 泛引
PAREN_BAD = re.compile(r'（\s*(出自|详见|来源|引自|见标准|参考标准)|依据相关标准|根据相关标准')
# —— 标准名 / 条文号 / 单位 / 原理词
STD_NAME = re.compile(r'《[^》]{2,60}》')
STD_NO = re.compile(r'(GB|DB37|DB|JGJ|GBT)\s?/?T?\s?\d{3,5}', re.I)
CLAUSE_NO = re.compile(r'第\s?\d+(?:\.\d+){1,3}\s?条')
UNIT_VAL = re.compile(r'\d[\d,]*(?:\.\d+)?\s*(?:℃|%|MPa|kW|kWh|kW·h|GJ|MJ|L|m³|m2|m²|元|kgce|人|盏|台|只|套)')
PRINCIPLE = re.compile(r'(相似定律|能效|效率|COP|EER|传热|换热|蒸发|冷凝|绝缘|降容|损耗|负荷|变频|工频|水力平衡|功率)')


def load(project: str) -> Path:
    p = Path(project)
    d = p if p.is_dir() else Path.home() / "projects" / "energy-audit" / project
    f = d / "chapter_md" / "ch7.md"
    if not f.is_file():
        print(f"未找到 {f}", file=sys.stderr)
        sys.exit(1)
    return f


def split_items(text: str) -> list[tuple[str, str, str]]:
    """返回 [(编号, 标题句, 正文)]；7.1 段内以 `（N）` 开头。"""
    if "## 7.1" not in text:
        return []
    seg = text.split("## 7.1", 1)[1]
    seg = seg.split("## 7.2", 1)[0] if "## 7.2" in seg else seg
    out = []
    for m in re.finditer(r'（(\d+)）([^\n]+)', seg):
        body = m.group(2)
        i = body.find("。")
        if i < 0:
            out.append((m.group(1), body.strip(), ""))
        else:
            out.append((m.group(1), body[:i].strip(), body[i + 1:].strip()))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="第7章依据锚点机械闸")
    ap.add_argument("project", help="项目名或项目目录")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    path = load(args.project)
    text = path.read_text(encoding="utf-8")

    fails: list[str] = []
    warns: list[str] = []
    rows: list[str] = []

    items = split_items(text)
    if not items:
        fails.append("7.1 未解析到任何问题条目（检查 `## 7.1` 段与 `（N）` 编号）")

    for no, title, body in items:
        if TITLE_BAD.search(title):
            fails.append(f"（{no}）标题句含标准号/括注：{title}")
        full = title + "。" + body
        m = PAREN_BAD.search(body)
        if m:
            fails.append(f"（{no}）正文出现括注式出处/泛引：{m.group(0)}")
        names = STD_NAME.findall(body)
        if names:
            # "定额标准"用于说明对标口径，不计入"最多 1 部"的堆砌限制（2026-09-29）
            codes = [n for n in names if "定额" not in n]
            if len(codes) > 1:
                warns.append(f"（{no}）引了 {len(codes)} 部规范（建议每条最多 1 部）：{codes}")
            # 引"定额标准"是为了说明对标口径，不要求给条文号（2026-09-29）
            if not CLAUSE_NO.search(body) and "定额" not in names[0]:
                warns.append(f"（{no}）引了标准但未给条文号（`第X.X.X条`）：{names[0]}")
        anchors = []
        if STD_NO.search(body) or names:
            anchors.append("标准")
        if UNIT_VAL.search(body):
            anchors.append("定量")
        if PRINCIPLE.search(body):
            anchors.append("原理")
        nchar = len(re.sub(r"\s", "", full))
        tag = "/".join(anchors) if anchors else "无（不判不合格）"
        rows.append(f"（{no}）字{nchar:4d} | 锚点={tag} | {title[:34]}")

    for m in re.finditer(r'^###\s*(7\.2\.\d+)\s*(.+)$', text, re.M):
        t = m.group(2).strip()
        if TITLE_BAD.search(t):
            fails.append(f"{m.group(1)} 小标题含标准号/括注：{t}")

    if not args.quiet:
        print(f"[文件] {path}")
        print("— 逐条锚点（提示，不判不合格）—")
        for r in rows:
            print("  " + r)
        if warns:
            print("— 提示 —")
            for w in warns:
                print("  · " + w)
    for f in fails:
        print("  ✗ " + f)
    print(f"[{'PASS' if not fails else 'FAIL'}] 第7章标题零条文 / 引用形态"
          f"（硬闸失败 {len(fails)} 项，提示 {len(warns)} 项）")
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
