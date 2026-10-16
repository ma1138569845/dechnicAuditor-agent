#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ch5_gas_attribution.py — 第5章 5.2.3 用气情况分析【段1 设备描述】判定器

背景（2026-10-16 用户定）：
  用水节的设备描述已有台账判定器（ch5_water_attribution.py），用气节却全靠写作层现场发挥——
  既可能漏设备（只写厨房、漏掉锅炉），也会写出无台账支撑的说法，还会踩括号禁令
  （岚山实测：`燃气蒸汽锅炉（2台，供手术室区域，运行时间7:00-18:00）`）。

判定表（两张判据并用，用户 2026-10-16 定）：

  A. 厨房/炊事用气 ← ① `equipment` 特殊设备表 `has_gas_use == 1`（平台表单字段，直给"是"）
                       ② 交叉印证：`energy_flow_trees` 的天然气分支含 厨房/炊事/食堂/餐厅/灶
                       （实测岚山：特殊设备表**没有厨房行**，has_gas_use 全 0，只能靠流向树命中
                        —— 这正是"两只判据都要"的原因）
  B. 燃气型锅炉/机组 ← `equipment` 名称命中：燃气蒸汽锅炉 / 燃气热水锅炉 / 燃油·燃气吸收式溴化锂
                       （跨类目：蒸汽 / 空调 / 生活热水）

  口径要点：
    · **设备存在即写**；`year_gas_value` / `gas_value` 只用于判断"当年度是否运行"，
      不作为"是否写"的并列必要条件——否则"有设备没耗气"（停用/闲置/未分项计量）这类
      审计发现点会被抹掉。
    · 空值语义：None = 未登记（出告警），0 = 明确为 0（出告警提示核实是否停用）。

成句（对齐 energy-audit-style/rules.md《3b 正文数值与括号规范》的正例形态，不用括号承载参数）：

  只有厨房      ：{单位}用气主要为厨房炊事设备。
  只有锅炉      ：{单位}用气主要为燃气蒸汽锅炉，共2台，供手术室区域使用，运行时间为7:00—18:00。
  两者都有      ：{单位}用气主要为燃气蒸汽锅炉和厨房炊事设备，其中燃气蒸汽锅炉共2台，
                  供手术室区域使用，运行时间为7:00—18:00。
  台账无燃气设备但天然气量 > 0（兜底，不编设备）：
                {单位}天然气主要用于{流向树登记的用途}。  ← 并向用户告警"设备台账缺登记"

顺带做一处口径统一（2026-10-16）：用气节段1 的引语句式与用水节对齐——
`根据统计数据，` → `根据所提供能耗账单及缴费发票统计分析，`（幂等，只在该节替换）。

用法:
    python ch5_gas_attribution.py <项目名|项目目录>            # 只打印（dry-run）
    python ch5_gas_attribution.py <项目名|项目目录> --apply    # 幂等写回 chapter_md/ch5_import.md
    python ch5_gas_attribution.py <项目名|项目目录> --json out.json

退出码: 0 正常；1 输入缺失/锚点缺失；2 有告警（台账缺登记、耗气量未登记、分支兜底等）
"""
import argparse
import json
import os
import re
import sys

ZW = "\u200c\u200b\u200d\ufeff"

# 燃气型设备（平台字典 heat_device / cold_device / hotwater_device 里的燃气项）
GAS_DEVICES = (
    ("燃气蒸汽锅炉", ("燃气蒸汽锅炉",)),
    ("燃气热水锅炉", ("燃气热水锅炉",)),
    ("燃油/燃气吸收式溴化锂", ("溴化锂", "吸收式")),
)
KITCHEN_TOKENS = ("厨房", "炊事", "食堂", "餐厅", "灶")
LEAD_OLD = "根据统计数据，"
LEAD_NEW = "根据所提供能耗账单及缴费发票统计分析，"


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit")


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def clean(v) -> str:
    return str(v or "").translate({ord(c): None for c in ZW}).strip()


def fmt_num(v) -> str:
    """数值口径：整数不带小数位、小数两位（rules.md《3b》）。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v or "")
    return f"{f:.0f}" if abs(f - round(f)) < 1e-6 else f"{f:.2f}"


def _spec_field(spec: str, key: str) -> str:
    """从 spec 串里取 `区域:手术室` / `运行:07:00:00~18:00:00` 这类片段。"""
    m = re.search(rf"{key}\s*[:：]\s*([^|]+)", spec or "")
    return clean(m.group(1)) if m else ""


def _fmt_time(raw: str) -> str:
    """07:00:00~18:00:00 → 7:00—18:00（去秒、破折号统一为全角）。"""
    if not raw:
        return ""
    def _one(t):
        parts = t.strip().split(":")
        hh = parts[0].lstrip("0") or "0"
        mm = parts[1] if len(parts) > 1 else "00"
        return f"{hh}:{mm}"
    seg = re.split(r"[~～\-—]", raw)
    if len(seg) == 2:
        return f"{_one(seg[0])}—{_one(seg[1])}"
    return raw


def detect_gas_use(data: dict):
    """判定用气设备与用途，返回 (info, warns, ev)。"""
    warns, ev = [], {}
    equip = data.get("equipment") or []

    # ---- A. 厨房/炊事用气 ----
    kitchen_by_field = [e for e in equip
                        if e.get("has_gas_use") == 1
                        and any(k in clean(e.get("name")) for k in KITCHEN_TOKENS)]
    kitchen_by_flow, flow_usages = [], []
    for tree in (data.get("energy_flow_trees") or []):
        if "天然气" not in clean(tree.get("name")) and "燃气" not in clean(tree.get("name")):
            continue
        def walk(nodes, path):
            for n in nodes or []:
                nm = clean(n.get("name"))
                if nm:
                    flow_usages.append(nm)
                    if any(k in nm for k in KITCHEN_TOKENS):
                        kitchen_by_flow.append(nm)
                walk(n.get("children"), path + [nm])
        walk(tree.get("children"), [])
    kitchen = bool(kitchen_by_field) or bool(kitchen_by_flow)
    if kitchen_by_field:
        ev["厨房"] = "特殊设备台账 has_gas_use=1：" + "、".join(
            clean(e.get("name")) for e in kitchen_by_field)
    if kitchen_by_flow:
        ev["厨房"] = (ev.get("厨房", "") + "；" if ev.get("厨房") else "") + \
                     "能源流向树登记：" + "、".join(sorted(set(kitchen_by_flow)))

    # ---- B. 燃气型锅炉/机组 ----
    burners = []
    for e in equip:
        nm = clean(e.get("name"))
        if not nm:
            continue
        for label, keys in GAS_DEVICES:
            if any(k in nm for k in keys):
                burners.append((label, e))
                break
    # 同一台设备多版本行 → 合并
    merged = {}
    for label, e in burners:
        key = (label, _spec_field(e.get("spec"), "区域"), e.get("quantity"))
        if key not in merged:
            merged[key] = e
    burner_list = [(label, e) for (label, _r, _q), e in merged.items()]
    ev["燃气设备"] = "；".join(
        f"{label}（{clean(e.get('category'))}台账，{e.get('quantity')}台）"
        for label, e in burner_list) or "无"
    for label, e in burner_list:
        yv, gv = e.get("year_gas_value"), e.get("gas_value")
        if yv in (None, "") and gv in (None, ""):
            warns.append(f"{label} 台账未登记年耗气量（year_gas_value/gas_value 为空）"
                         f"→ 建议在平台补填，用于核对当年度是否运行")
        elif yv == 0 or gv == 0:
            warns.append(f"{label} 台账登记耗气量为 0 → 请核实设备是否停用/闲置，"
                         f"或未单独计量（该项本身是审计发现点）")

    # ---- 天然气年度实物量 ----
    gas_years = [(ey.get("year"), float(ey.get("natural_gas_m3") or 0))
                 for ey in (data.get("energy_yearly") or [])
                 if float(ey.get("natural_gas_m3") or 0) > 0]
    if not gas_years:
        warns.append("无天然气年度用量 → 5.2.3 用气节不应生成")
    if gas_years and not kitchen and not burner_list:
        warns.append("天然气用量 > 0 但台账里既无厨房燃气使用、也无燃气型锅炉/机组 "
                     "→ 段1 按流向树用途兜底，请人工核实设备台账是否漏登")
    if not kitchen:
        warns.append("厨房炊事用气未命中：特殊设备表无厨房行（has_gas_use=1）且流向树无厨房分支")

    return {"kitchen": kitchen, "burners": burner_list,
            "flow_usages": sorted(set(flow_usages)), "gas_years": gas_years}, warns, ev


def build_lead_sentence(unit: str, info: dict) -> str:
    """段1 的设备描述句（新口径：不用括号承载参数）。"""
    items = []
    detail = []
    labels = sorted({label for label, _ in info["burners"]})
    if labels:
        items.append("、".join(labels))
    if info["kitchen"]:
        items.append("厨房炊事设备")
    if not items:                                    # 兜底：不编设备
        usages = [u for u in info["flow_usages"] if "用气" in u]
        tail = "、".join(usages) if usages else "未登记用途"
        return f"{unit}天然气主要用于{tail}。"

    for label, e in info["burners"]:
        qty = e.get("quantity") or 0
        area = _spec_field(e.get("spec"), "区域")
        run = _fmt_time(_spec_field(e.get("spec"), "运行"))
        seg = f"{label}共{int(qty)}台" if qty else label
        if area:
            seg += f"，供{area}区域使用"
        if run:
            seg += f"，运行时间为{run}"
        detail.append(seg)
    if len(items) == 1:
        head = f"{unit}用气主要为{items[0]}"
    else:
        head = f"{unit}用气主要为{'和'.join(items)}"
    if info["burners"]:
        head += "，其中" + "；".join(detail)
    return head + "。"


def locate_lead(md_path: str, heading_pat: str = r"^### 5\.2\.3"):
    """定位用气节段1：返回 (行号, 主语前缀, 首句之后的其余文本)。找不到即退出。"""
    lines = open(md_path, encoding="utf-8").read().splitlines()
    s = next((i for i, l in enumerate(lines) if re.match(heading_pat, l.strip())), None)
    if s is None:
        raise SystemExit("[错误] md 里找不到用气节标题（默认 '### 5.2.3'；如节号不同用 --heading 指定）")
    e = next((i for i in range(s + 1, len(lines))
              if re.match(r"^#{2,3} ", lines[i].strip())), len(lines))
    lead = next((i for i in range(s + 1, e) if "用气主要为" in lines[i]), None)
    if lead is None:
        raise SystemExit("[错误] 用气节段1 里找不到 '用气主要为' 句子（锚点缺失）")
    orig = lines[lead]
    k = orig.index("用气主要为")
    prefix, dot = orig[:k], orig.find("。", orig.index("用气主要为"))
    rest = orig[dot + 1:] if dot >= 0 else ""
    return lines, lead, prefix, rest


def apply_to_md(md_path: str, new_lead: str, warns: list, heading_pat=r"^### 5\.2\.3"):
    """幂等写回：替换段1 的**设备描述首句**（含引语口径统一），数值句与引图句原样保留。"""
    lines, lead, _prefix, rest = locate_lead(md_path, heading_pat)
    if LEAD_OLD in rest:                      # 引语统一（幂等：第二次跑不再命中）
        rest = rest.replace(LEAD_OLD, LEAD_NEW, 1)
    # 数值与单位之间空一格（2026-10-16 口径：`57207 m³`，不写 `57207m³`；幂等）
    rest = re.sub(r"(\d)\s*(kWh|m³|GJ|kg|t|L)\b", r"\1 \2", rest)
    lines[lead] = new_lead + rest
    open(md_path, "w", encoding="utf-8").write("\n".join(lines).rstrip("\n") + "\n")
    return md_path


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--heading", default=r"^### 5\.2\.3",
                    help="用气节标题正则（机构不同节号可能变化）")
    args = ap.parse_args()

    proj_dir = resolve_project_dir(args.project)
    if not proj_dir:
        print(f"[错误] 找不到项目目录：{args.project}")
        return 1
    data_path = os.path.join(proj_dir, "data.json")
    if not os.path.exists(data_path):
        print(f"[错误] 缺 data.json：{data_path}")
        return 1
    data = json.load(open(data_path, encoding="utf-8"))
    base = data.get("base") or {}
    unit = base.get("unit_short") or base.get("unit_name") or ""

    info, warns, ev = detect_gas_use(data)
    md = os.path.join(proj_dir, "chapter_md", "ch5_import.md")
    subject = unit
    if os.path.exists(md):
        try:
            _lines, _lead, prefix, _rest = locate_lead(md, args.heading)
            subject = prefix or unit          # 段1 里是简称（"医院"）就沿用，避免同一节两个称呼
        except SystemExit as exc:
            print(str(exc))
            return 1
    else:
        print(f"[错误] 缺 chapter_md/ch5_import.md：{md}")
        return 1
    new_lead = build_lead_sentence(subject, info)

    print(f"[5.2.3] 项目：{unit}")
    for k, v in ev.items():
        print(f"  · {k}：{v}")
    print(f"  段1 新句：{new_lead}")
    print(f"  天然气年度用量：" + "、".join(f"{y}年 {fmt_num(v)} m³" for y, v in info["gas_years"]))
    for w in warns:
        print(f"  [告警] {w}")

    if args.json:
        json.dump({"unit": unit, "lead": new_lead, "info": info, "warns": warns},
                  open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
        print(f"  JSON 已写：{args.json}")

    if args.apply:
        apply_to_md(md, new_lead, warns, args.heading)
        print(f"  已写回：{md}")
    return 2 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
