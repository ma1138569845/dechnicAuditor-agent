#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ch5_water_attribution.py — 第5章 5.2.2 用水情况分析判定器

背景（2026-10-15 用户定）：
  改造前 5.2.2 只有一句归因模板「用水量较大月份为制冷季（冷却塔及管路补水）／
  无冷却塔机构＝用水量全年较为稳定，主要为生活用水」，段1 的用水构成是硬编码字符串
  （chapter5-spec.md 的 `eq_str = "用水系统主要为生活用水、卫生清洁用水等"`），
  逐月高峰靠写作模型现场判断。结果：段1 与段4 各说一套（岚山实测段1 写「空调、供暖
  系统补水」、段4 只写「制冷」），该报的水量高峰不报（中医医院 2024 年 1 月、3 月
  分别高出当年月均 38.7%、37.7%，被写成「全年较为稳定」）。

本脚本按判定表机械生成，可复现、可核对：

  第0步  补水项判定（清单＝用户 2026-10-15 定，与平台字典 cold_device/heat_device/
         hotwater_device 对齐；判据来源＝设备台账，不是「有没有冷却塔」）：
         · 冷源清单 ∩（buildings[].cooling_source ∪ equipment 空调类目）
           ＋（equipment 其他设备含「冷却塔」或「空调系统补水装置」）→ 空调系统补水
         · 热源清单 ∩ equipment **空调类目**（＝供暖设备台账）→ 供暖系统补水
           ⛔ 蒸汽类目里的锅炉是工艺/消毒蒸汽，**不计入**（2026-10-15 用户定）
         · 生活热水：空气源热泵系统 / 燃气热水锅炉 / 太阳能系统
           （生活热水的「空气源热泵系统」≠ 清单里的「空气源热泵」；电热水器、小厨宝不算）
  第1步  段1 用水构成句 ＝ {单位}用水主要为{生活用水 ＋ 平台附属用水项 ＋ 清单命中的
         补水项}，由{供水方式}供水。 —— 同一判据供段1 与段4 两处使用（方案A）
  第2步  高峰判定（丙案）：基准＝当年月均（含当月）；单月 > 基准×1.2 → 点名并写
         「较当年月均高出X%」；> 基准×2.0 → ⑥ 红色注待核实；**逐年写、不设年数门槛**
         （用水受抄表周期影响，年际不可比；照电力那套 4/5/10 月基准实测会漏报）
  第3步  归因句：按命中的补水项挂设备/系统形式；挂不上时允许挂季节性规律
         （2026-10-15 用户定；不写「成因待核实」）
  第4步  异常说明：只认能源名归一到「水」的平台登记；月粒度合并成一段（段4 之后）、
         年粒度另起一段（段2 之后）；库中无记录 → 不写、不编原因
  第5步  写回 chapter_md/ch5_import.md：段1 首句替换 + 段4 区整段重建

用法:
    python ch5_water_attribution.py <项目名|项目目录>            # 只打印（dry-run）
    python ch5_water_attribution.py <项目名|项目目录> --apply    # 幂等写回 chapter_md/ch5_import.md
    python ch5_water_attribution.py <项目名|项目目录> --json out.json

退出码: 0 正常；1 输入缺失；2 有告警（缺逐月水量 / 附属用水登记缺失 / 锚点异常等，
        仍会输出可判定的部分）
"""
import argparse
import json
import os
import re
import sys

# 用户 2026-10-15 定：两张清单（与平台字典 cold_device / heat_device 对齐）
COOL_LIST = (
    ("冷水机组", ("冷水机组",)),
    ("地源热泵", ("地源热泵",)),
    ("冰蓄冷系统", ("冰蓄冷",)),
    ("风冷模块机组", ("风冷模块",)),
    ("空气源热泵", ("空气源热泵",)),
    ("燃油/燃气吸收式溴化锂", ("溴化锂", "吸收式")),
    ("水环热泵", ("水环热泵",)),
)
HEAT_LIST = (
    ("燃气热水锅炉", ("燃气热水锅炉",)),
    ("地源热泵", ("地源热泵",)),
    ("空气源热泵", ("空气源热泵",)),
    ("燃油/燃气吸收式溴化锂", ("溴化锂", "吸收式")),
    ("燃气蒸汽锅炉", ("燃气蒸汽锅炉",)),
    ("水环热泵", ("水环热泵",)),
)
HOTWATER_LIST = (
    ("燃气热水锅炉", ("燃气热水锅炉",)),
    ("空气源热泵系统", ("空气源热泵",)),
    ("太阳能系统", ("太阳能",)),
)

WATER_THR = 1.2          # 丙案：单月 > 当年月均 ×1.2 → 点名
WATER_RED_THR = 2.0      # 强异常：单月 > 当年月均 ×2.0 → 红色注待核实
SUPPLY_MAP = {"市政给水": "市政自来水", "市政供水": "市政自来水"}
WATER_ENERGY_TOKENS = ("水", "水耗", "水资源", "自来水", "用水")
ZW = "\u200c\u200b\u200d\ufeff"


# ---------------------------------------------------------------- 基础工具
def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit")


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def fmt_num(v) -> str:
    """数值格式（2026-10-15 用户定）：整数不带小数位，小数保留两位；全文禁千分位。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v or "")
    return f"{f:.0f}" if abs(f - round(f)) < 1e-6 else f"{f:.2f}"


def pct_text(value: float, base: float) -> str:
    """(单月 ÷ 当年月均 − 1) 的百分比文本，如 29.6%。"""
    if not base:
        return ""
    return fmt_num((value / base - 1) * 100) + "%"


def clean(v) -> str:
    return str(v or "").translate({ord(c): None for c in ZW}).strip()


def months_text(months, order=tuple(range(1, 13))) -> str:
    """月份压缩成中文表述：相邻两个月用「和」，连续多月用「至」。"""
    ms = [m for m in order if m in set(months)]
    if not ms:
        return ""
    idx = [order.index(m) for m in ms]
    segs, cur = [], [idx[0]]
    for a, b in zip(idx, idx[1:]):
        if b == a + 1:
            cur.append(b)
        else:
            segs.append(cur)
            cur = [b]
    segs.append(cur)
    parts = []
    for seg in segs:
        first, last = order[seg[0]], order[seg[-1]]
        if len(seg) == 1:
            parts.append(f"{first}月")
        elif len(seg) == 2:
            parts.append(f"{first}月和{last}月")
        else:
            parts.append(f"{first}月至{last}月")
    if len(parts) == 1:
        return parts[0]
    return "、".join(parts[:-1]) + "以及" + parts[-1]


# ---------------------------------------------------------------- 判定
def _match_lists(names, table):
    """名字清单 ∩ 判定表 → [(清单项, 命中的原文名), ...]（去重、保序）。"""
    hits, seen = [], set()
    for raw in names:
        n = clean(raw)
        if not n:
            continue
        for label, keys in table:
            if any(k in n for k in keys) and label not in seen:
                seen.add(label)
                hits.append((label, n))
    return hits


def detect_makeup(data: dict):
    """判定三类补水项，返回 (info, warns)。"""
    warns, ev = [], {}
    buildings = data.get("buildings") or []
    equip = data.get("equipment") or []

    # 冷源：buildings[].cooling_source ∪ 空调类目设备名
    cool_names = [b.get("cooling_source") for b in buildings]
    cool_names += [e.get("name") for e in equip if clean(e.get("category")) == "空调"]
    cool_hits = _match_lists(cool_names, COOL_LIST)

    # 空调水系统的旁证：其他设备里的 冷却塔 / 空调系统补水装置
    aux_names = [clean(e.get("name")) for e in equip
                 if clean(e.get("category")) == "其他设备"]
    tower = any("冷却塔" in n for n in aux_names)
    makeup_dev = any("补水装置" in n for n in aux_names)

    # 热源：**只看空调类目**（＝供暖设备台账）；蒸汽类目是工艺/消毒蒸汽
    heat_names = [e.get("name") for e in equip if clean(e.get("category")) == "空调"]
    heat_hits = _match_lists(heat_names, HEAT_LIST)

    # 生活热水：独立清单，与供暖补水分开表述
    hw_names = [e.get("name") for e in equip if clean(e.get("category")) == "生活热水"]
    hw_hits = _match_lists(hw_names, HOTWATER_LIST)

    ac = bool(cool_hits) or tower or makeup_dev
    ev["cool"] = [f"{lbl}（{src}）" for lbl, src in cool_hits]
    if tower:
        ev["cool"].append("冷却塔（其他设备台账）")
    if makeup_dev:
        ev["cool"].append("空调系统补水装置（其他设备台账）")
    ev["heat"] = [f"{lbl}（{src}）" for lbl, src in heat_hits]
    ev["hotwater"] = [f"{lbl}（{src}）" for lbl, src in hw_hits]
    steam_boilers = [clean(e.get("name")) for e in equip
                     if clean(e.get("category")) == "蒸汽"
                     and any(k in clean(e.get("name")) for k in ("燃气蒸汽锅炉", "锅炉"))]
    if steam_boilers and not heat_hits:
        warns.append("蒸汽类目有锅炉（%s）但未计入供暖补水——按口径它是工艺/消毒蒸汽；"
                     "若实为供暖热源，请在平台改登记到供暖设备台账"
                     % "、".join(sorted(set(steam_boilers))))
    if not ev["cool"] and not ev["heat"] and not ev["hotwater"]:
        warns.append("三类补水项全未命中（冷源/热源/生活热水台账均无清单内设备）")
    return {"ac": ac, "heat": bool(heat_hits), "hotwater": bool(hw_hits),
            "evidence": ev}, warns


def aux_water_items(data: dict):
    """平台附属用水登记 → 段1 里要列举的用水项（含证据）。"""
    aux = data.get("water_aux") or {}
    items, ev = [], []
    if aux.get("greening"):
        r = aux["greening"][0]
        items.append("绿化灌溉用水")
        ev.append("绿化灌溉用水＝灌溉形式 %s／水源 %s"
                  % (r.get("irrigation_type") or "未填", r.get("irrigation_source") or "未填"))
    if aux.get("road"):
        r = aux["road"][0]
        items.append("道路冲洗用水")
        ev.append("道路冲洗用水＝用水类型 %s" % (r.get("water_type") or "未填"))
    if aux.get("other"):
        r = aux["other"][0]
        items.append("其他用水")
        ev.append("其他用水＝用水系统 %s" % (r.get("water_system") or "未填"))
    return items, ev


def yearly_profile(data: dict):
    """逐年算当年月均与命中月份（丙案）；返回 (明细, 告警)。"""
    out, warns = [], []
    for ey in sorted(data.get("energy_yearly") or [], key=lambda x: x.get("year") or 0):
        year = ey.get("year")
        m = ey.get("monthly_water_m3") or []
        if len(m) < 12 or not any(float(v or 0) for v in m):
            warns.append(f"{year}年 逐月用水量不足 12 个月（{len(m)}），已跳过")
            continue
        vals = [float(v or 0) for v in m]
        base = sum(vals) / 12.0
        hits = [(i + 1, vals[i]) for i in range(12) if base > 0 and vals[i] > base * WATER_THR]
        red = [(i + 1, vals[i]) for i in range(12) if base > 0 and vals[i] > base * WATER_RED_THR]
        out.append({"year": year, "base": base, "values": vals,
                    "hits": hits, "red": red})
    return out, warns


def build_blocks(unit, details, makeup, aux_items, fig_mth, anomalies):
    """段4 四块 + ⑤ 月异常段 + ⑥ 红色注（顺序固定，红色注永远在最后）。"""
    blocks, warns = [], []

    # ① 高峰点名（逐年）
    hit_years = [d for d in details if d["hits"]]
    if hit_years:
        # ★2026-10-15 用户定 A 案：括号内只承载单位，禁用「月份（数值…）」形态。
        # 反例（禁用）：医院用水量较大月份为2022年7月（17622m³）和8月（16724m³）。
        # 正例：医院2022年7月和8月用水量分别为17622 m³、16724 m³，较当年月均分别高出…。
        segs = []
        for d in hit_years:
            ms = months_text([m for m, _ in d["hits"]])
            vals = "、".join(fmt_num(v) for _, v in d["hits"])
            pcts = "、".join(pct_text(v, d["base"]) for _, v in d["hits"])
            if len(d["hits"]) == 1:
                segs.append(f"{d['year']}年{ms}用水量为{vals} m³，"
                            f"较当年月均高出{pcts}")
            else:
                segs.append(f"{d['year']}年{ms}用水量分别为{vals} m³，"
                            f"较当年月均分别高出{pcts}")
        blocks.append(f"由图5.{fig_mth}分析，{unit}" + "；".join(segs) + "。")
        calm = [d for d in details if not d["hits"]]
        if calm:
            yrs = "、".join(f"{d['year']}年" for d in calm)
            blocks.append(f"{yrs}各月用水量均在当年月均的20%以内，用水相对平稳。")
    else:
        blocks.append(f"由图5.{fig_mth}分析，{unit}各年用水量均在当年月均的20%以内波动，"
                      f"全年用水较为平稳。")

    # ②③ 归因句（有夏季/供暖季命中才写）
    months_all = [m for d in details for m, _ in d["hits"]]
    cool_hit = any(6 <= m <= 9 for m in months_all)
    heat_hit = any(m in (11, 12, 1, 2, 3) for m in months_all)
    if cool_hit:
        if makeup["ac"]:
            blocks.append("夏季用水量偏高与空调系统冷却塔及管路补水、卫生清洁用水增加有关。")
        elif any("绿化" in i for i in aux_items):
            blocks.append("夏季用水量偏高与绿化灌溉用水、卫生清洁用水增加有关。")
        else:
            blocks.append("夏季用水量偏高与夏季卫生清洁用水增加有关。")
    if heat_hit:
        if makeup["heat"] and makeup["hotwater"]:
            blocks.append("供暖季用水量偏高与供暖系统补水及生活热水系统用量增加有关。")
        elif makeup["heat"]:
            blocks.append("供暖季用水量偏高与供暖系统补水有关。")
        elif makeup["hotwater"]:
            blocks.append("供暖季用水量偏高与生活热水系统用量增加有关。")
        else:
            blocks.append("供暖季用水量偏高，符合供暖季用水的季节性变化规律。")

    # ④ 收尾句
    blocks.append(f"{unit}逐月用水量变化符合单位用水及季节性用水变化规律。")

    # ⑤ 平台异常说明段（月粒度，合并一段）
    month_notes = []
    for a in anomalies["month"]:
        month_notes.append(a)
    if month_notes:
        blocks.append("；".join(month_notes) + "。")

    # ⑥ 红色注（强异常待核实，固定在最后）
    for d in details:
        for mm, v in d["red"]:
            blocks.append(f"注：{d['year']}年{mm}月用水量为{fmt_num(v)}m³"
                          f"明显高于当年月均，异常原因请核实。")
    return blocks, warns


def pick_anomalies(data: dict):
    """平台异常登记 → 只认「水」；返回 {'year': [...], 'month': [...]}（句式已成形）。"""
    res = {"year": [], "month": []}
    for ey in sorted(data.get("energy_yearly") or [], key=lambda x: x.get("year") or 0):
        year = ey.get("year")
        for a in (ey.get("anomalies") or []):
            name = clean(a.get("energy_name"))
            if not any(t in name for t in WATER_ENERGY_TOKENS):
                continue                     # 跨能源串味闸：电力/热力/油气的登记不进用水节
            title = a.get("title") or ""
            direction = "下降" if "下降" in title else "上升"
            rate = a.get("rate_value")
            rate_txt = (fmt_num(float(rate)) + "%") if rate is not None else ""
            desc = (a.get("desc_no_year") or a.get("desc") or "").strip().rstrip("。；")
            if not desc:
                continue
            mth = re.match(r"(\d{1,2})月", clean(a.get("period")))
            when = f"{year}年{mth.group(1)}月" if mth else f"{year}年"
            line = f"{when}用水量同比{direction}{rate_txt}，主要是{desc}"
            res["month" if mth else "year"].append(line)
    return res


# ---------------------------------------------------------------- md 写回
def apply_to_md(md_path: str, new_lead: str, blocks: list, year_note: str, warns: list,
                rebuild_lines: list = None):
    """幂等写回 5.2.2：段1 首句替换 + 段4 区（逐月图注之后 → 小节末）整段重建。"""
    lines = open(md_path, encoding="utf-8").read().splitlines()
    s = next((i for i, l in enumerate(lines)
              if re.match(r"^### 5\.2\.2", l.strip())), None)
    if s is None:
        raise SystemExit("[错误] md 里找不到 '### 5.2.2' 小节")
    e = next((i for i in range(s + 1, len(lines))
              if re.match(r"^#{2,3} ", lines[i].strip())), len(lines))
    sec = lines[s + 1:e]
    caps = [i for i, l in enumerate(sec) if re.match(r"^图5\.\d", l.strip())]
    if len(caps) < 2:
        raise SystemExit("[错误] 5.2.2 内图注行不足 2 条（应有 总量图 与 逐月图）")

    if rebuild_lines is not None:
        open(md_path, "w", encoding="utf-8").write(
            "\n".join(lines[:s + 1] + [""] + rebuild_lines + [""] + lines[e:])
            .rstrip("\n") + "\n")
        return md_path

    tot_cap, mth_cap = caps[0], caps[-1]
    lead = next((i for i in range(0, tot_cap) if LEAD_RE.search(sec[i])), None)
    if lead is None:
        raise SystemExit("[错误] 5.2.2 段1 里找不到 '用水主要为' 句子（锚点缺失）")
    d2 = next((i for i in range(tot_cap + 1, mth_cap) if sec[i].strip()), None)
    if d2 is None:
        warns.append("段2 锚点缺失（总量图注之后没有正文段）→ 年异常段未落位")

    out, placed = [], False
    for i, l in enumerate(sec):
        if i > mth_cap:
            if i == mth_cap + 1:
                out.append("")
                out.extend(blocks)
            continue
        if re.match(r"^\d{4}年用水量同比(?:上升|下降)", l.strip()):
            continue                          # 旧年异常段丢弃（由本次重写）
        if i == lead:
            out.append(new_lead)
            continue
        out.append(l)
        if year_note and not placed and i == d2:
            out.append(year_note)
            placed = True
    if year_note and not placed:
        out.insert(0, year_note)
        warns.append("年异常段未找到段2 锚点，已退到小节首部插入")

    new_lines = lines[:s + 1] + out + lines[e:]
    open(md_path, "w", encoding="utf-8").write("\n".join(new_lines).rstrip("\n") + "\n")
    return md_path


LEAD_RE = re.compile(r"用水(?:系统)?主要为")


def build_lead_line(orig_line: str, items: list, supply: str) -> str:
    """把段1 的「用水（系统）主要为…」首句替换为新构成句，保留其后的数据句。"""
    m = LEAD_RE.search(orig_line)
    if not m:
        raise ValueError("段1 里找不到 '用水主要为' / '用水系统主要为'")
    prefix, tail = orig_line[:m.start()], orig_line[m.start():]
    end = tail.find("供水。")
    if end >= 0:
        end += 3
    else:
        dot = tail.find("。")
        end = dot + 1 if dot >= 0 else len(tail)
    rest = tail[end:]
    body = "用水主要为" + "、".join(items)
    body += f"，由{supply}供水。" if supply else "。"
    return prefix + body + rest


def yearly_totals(data: dict):
    """[(year, 年用水量)]，按年份升序；只取有值的年。"""
    out = []
    for ey in sorted(data.get("energy_yearly") or [], key=lambda x: x.get("year") or 0):
        v = float(ey.get("water_m3") or 0)
        if v > 0:
            out.append((ey.get("year"), v))
    return out


def build_paragraph2(subject: str, totals: list, fig_tot: str):
    """段2（年际段）：整体评价 + 逐年增减量/率 + >15% 异常标注；**不写归因**。"""
    if len(totals) < 2:
        return ""
    y1, v1 = totals[0]
    y3, v3 = totals[-1]
    rates = []
    for (py, pv), (cy, cv) in zip(totals, totals[1:]):
        rates.append((cv - pv) / pv if pv else 0)
    # 阈值与 5.2.1 口径一致：各年变幅都在 ±10% 以内 → "整体波动不大"（岚山电量 ±7.5% 即用此说法）
    trend = ("整体波动不大" if all(abs(r) < 0.10 for r in rates)
             else ("整体呈逐年上升趋势" if all(r > 0 for r in rates)
                   else ("整体呈逐年下降趋势" if all(r < 0 for r in rates)
                         else "整体呈波动变化")))
    parts, abnormal = [], []
    for (py, pv), (cy, cv), r in zip(totals, totals[1:], rates):
        word, tone = ("增加", "升幅") if cv >= pv else ("减少", "降幅")
        parts.append(f"{cy}年用水量较{py}年{word}{fmt_num(abs(cv - pv))} m³，"
                     f"{tone}为{fmt_num(abs(r) * 100)}%")
        if abs(r) > 0.15:
            abnormal.append(f"其中{cy}年用水量变化幅度超过15%，属于异常波动，"
                            f"建议进一步核实该年度用水异常原因。")
    text = (f"由图5.{fig_tot}分析，{subject}{y1}年-{y3}年用水量{trend}："
            + "；".join(parts) + "。")
    return text + ("".join(abnormal) if abnormal else "")


def build_paragraph3(subject: str, totals: list, fig_mth: str):
    y1, y3 = totals[0][0], totals[-1][0]
    return (f"结合{subject}{y1}年-{y3}年逐月用水量统计数据，逐月用水情况"
            f"变化趋势如图5.{fig_mth}所示。")


def build_section_lines(subject, supply, items, totals, details, makeup, aux_items,
                        anomalies, cap_tot, cap_mth, fig_tot, fig_mth):
    """按「四段两图」骨架重建整节正文（--rebuild，给旧骨架的 md 用）。"""
    lead = build_lead_line(f"{subject}用水主要为生活用水。", items, supply)
    vals = "，".join(f"{y}年全年用水量为{fmt_num(v)} m³" for y, v in totals)
    lead_tail = (f"根据所提供能耗账单及缴费发票统计分析，{subject}{vals}，"
                 f"变化趋势如图5.{fig_tot}所示。" if totals else "")
    lines = [lead.rstrip("。") + "。" + lead_tail, "", cap_tot, ""]
    lines.append(build_paragraph2(subject, totals, fig_tot))
    year_note = "；".join(anomalies["year"]) + "。" if anomalies["year"] else ""
    if year_note:
        lines += ["", year_note]
    lines += ["", build_paragraph3(subject, totals, fig_mth), "", cap_mth, ""]
    blocks, _ = build_blocks(subject, details, makeup, aux_items, fig_mth, anomalies)
    lines += blocks
    return lines


def main():
    # Windows 控制台默认 GBK，打印 m³ 会 UnicodeEncodeError（实测）→ 强制 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rebuild", action="store_true",
                    help="整节重建（给非四段两图骨架的旧 md 用：段1~段4 全部由数据生成，"
                         "图注行原样保留）")
    ap.add_argument("--json")
    args = ap.parse_args()

    proj_dir = resolve_project_dir(args.project)
    if not proj_dir:
        print(f"[错误] 找不到项目目录：{args.project}")
        return 1
    data_path = os.path.join(proj_dir, "data.json")
    if not os.path.exists(data_path):
        print(f"[错误] 缺 data.json：{data_path}")
        return 1
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    base = data.get("base") or {}
    unit = base.get("unit_short") or base.get("unit_name") or ""
    buildings = data.get("buildings") or [{}]
    supply_raw = clean(buildings[0].get("water_system")) if buildings else ""
    supply = SUPPLY_MAP.get(supply_raw, supply_raw)

    makeup, warns = detect_makeup(data)
    details, w2 = yearly_profile(data)
    warns += w2
    aux_items, aux_ev = aux_water_items(data)
    if not (data.get("water_aux") or {}):
        warns.append("data.json 缺 water_aux（附属用水登记）→ 段1 只列生活用水与补水项；"
                     "需重跑采集（ts_institution_water_greening/_other/_road）")
    anomalies = pick_anomalies(data)

    items = ["生活用水"] + aux_items
    if makeup["ac"]:
        items.append("空调系统补水")
    if makeup["heat"]:
        items.append("供暖系统补水")
    if makeup["hotwater"]:
        items.append("生活热水系统补水")

    md_path = os.path.join(proj_dir, "chapter_md", "ch5_import.md")
    if not os.path.exists(md_path):
        print(f"[错误] 缺 chapter_md/ch5_import.md：{md_path}")
        return 1
    lines = open(md_path, encoding="utf-8").read().splitlines()
    s = next((i for i, l in enumerate(lines) if re.match(r"^### 5\.2\.2", l.strip())), None)
    if s is None:
        print("[错误] md 里找不到 '### 5.2.2' 小节")
        return 1
    e = next((i for i in range(s + 1, len(lines))
              if re.match(r"^#{2,3} ", lines[i].strip())), len(lines))
    sec = lines[s + 1:e]
    caps_ratio = [i for i, l in enumerate(sec) if re.match(r"^图5\.\d", l.strip())]
    lead_i = next((i for i, l in enumerate(sec) if LEAD_RE.search(l)), None)
    if lead_i is None:
        if args.rebuild:
            lead_i = 0
            warns.append("段1 锚点缺失，但指定了 --rebuild → 整节按数据重建")
        else:
            print("[错误] 段1 锚点缺失（'用水主要为' / '用水系统主要为'）。"
                  "若是旧骨架的 md，请加 --rebuild 整节重建。")
            return 1
    # 段4 与段1 用同一个主语（段1 里的主语可能是简称"医院"，与全名混用会读成两个人）
    _m = LEAD_RE.search(sec[lead_i])
    subject = (sec[lead_i][:_m.start()].strip() if _m else "") or unit
    new_lead = (build_lead_line(sec[lead_i], items, supply) if _m
                else build_lead_line(f"{subject}用水主要为生活用水。", items, supply))

    caps = [i for i, l in enumerate(sec) if re.match(r"^图5\.\d", l.strip())]
    fig_mth = ""
    if caps:
        m = re.match(r"^图5\.(\d+)", sec[caps[-1]].strip())
        fig_mth = m.group(1) if m else ""
    if not fig_mth:
        warns.append("未取到逐月图号（图5.X）→ 段4 首句图号留空，请人工补")

    blocks, w3 = build_blocks(subject, details, makeup, aux_items, fig_mth, anomalies)
    warns += w3
    year_note = "；".join(anomalies["year"]) + "。" if anomalies["year"] else ""

    rebuild_lines = None
    if args.rebuild:
        if len(caps_ratio) < 2:
            print("[错误] 5.2.2 内图注行不足 2 条，--rebuild 无法定位图注")
            return 1
        m_tot = re.match(r"^图5\.(\d+)", sec[caps_ratio[0]].strip())
        rebuild_lines = build_section_lines(
            subject, supply, items, yearly_totals(data), details, makeup, aux_items,
            anomalies, sec[caps_ratio[0]].strip(), sec[caps_ratio[-1]].strip(),
            m_tot.group(1) if m_tot else fig_mth, fig_mth)
        warns.append("已按 --rebuild 整节重建（段1~段4 全部由数据生成）")

    print(f"[5.2.2] 项目：{unit}")
    print(f"  段1 新句：{new_lead.split('。')[0]}。")
    print(f"  补水项：空调={makeup['ac']} 供暖={makeup['heat']} 生活热水={makeup['hotwater']}")
    for k, v in makeup["evidence"].items():
        if v:
            print(f"    · {k}：{'；'.join(v)}")
    for ev in aux_ev:
        print(f"    · {ev}")
    print("  段4 文本块：")
    for b in blocks:
        print(f"    {b}")
    if year_note:
        print(f"  年异常段：{year_note}")
    for w in warns:
        print(f"  [告警] {w}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"unit": unit, "lead": new_lead, "items": items,
                       "makeup": makeup, "blocks": blocks, "year_note": year_note,
                       "warns": warns, "details": details}, f,
                      ensure_ascii=False, indent=2, default=str)
        print(f"  JSON 已写：{args.json}")

    if args.apply:
        apply_to_md(md_path, new_lead, blocks, year_note, warns, rebuild_lines)
        print(f"  已写回：{md_path}")

    return 2 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
