#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ch5_monthly_attribution.py — 第5章 5.2.1 逐月段（段4）归因判定器

背景（2026-10-14 用户定）：5.2.1 的逐月段归因以前靠 LLM 现场判断，结果不稳定。
本脚本按判定表机械生成，可复现、可核对：

  第0步  基准 B =（4月 + 5月 + 10月）÷ 3  ← 取**平均**（取最低会因单月异常低而失真）
  第1步  供冷季（6/7/8/9）单月 > B×1.3 命中；供热季（11/12/1/2/3）单月 > B×1.2 命中；
         过渡季（4/5/10）单月 > B×1.3 命中（只进红色注）
  第2步  多数年份（≥2 年）命中的月份才写进月份首句；仅 1 年命中的高月不写、不提
  第3步  按冷源类型/供暖缴费方式/热源/设备存在性选句，生成：
         ① 月份首句 ② 供冷季原因句 ③ 供热季原因句 ④ 收尾句
         ⑤ 平台异常说明段（月粒度 anomalies，合并一段）
         ⑥ 红色注（过渡季待核实，固定最后）

用法:
    python ch5_monthly_attribution.py <项目名|项目目录>            # 只打印（dry-run）
    python ch5_monthly_attribution.py <项目名|项目目录> --apply    # 幂等写回 chapter_md/ch5_import.md
    python ch5_monthly_attribution.py <项目名|项目目录> --json out.json

退出码: 0 正常；1 输入缺失；2 有告警（缺逐月数据/分支无法判定等，仍会输出可判定的部分）
"""
import argparse
import json
import os
import re
import sys

# 季节月份（常规规则，2026-10-14 用户定）
COOL = (6, 7, 8, 9)
HEAT = (11, 12, 1, 2, 3)
SHOULDER = (4, 5, 10)
COOL_ORDER = [6, 7, 8, 9]
HEAT_ORDER = [11, 12, 1, 2, 3]      # 11月 → 12月 → 次年1月 → 次年2月 → 次年3月
COOL_THR, HEAT_THR, SHOULDER_THR = 1.3, 1.2, 1.3

# 电驱动冷源关键词 / 吸收式关键词
ELEC_COOLING = ("冷水机组", "多联机", "分体", "挂机", "柜机", "热泵", "空调")
ABSORPTION = ("吸收式", "溴化锂", "直燃")

MONTH_RE = re.compile(r"^\s*(\d{1,2})\s*月\s*$")
ANOM_MONTH_RE = re.compile(r"^\d{4}年(?:\d{1,2}月)?[^，]{1,10}同比(?:上升|下降)[^，]{0,12}，主要是")
RED_NOTE_RE = re.compile(r"^注：.*异常原因请核实。$")


# ---------------------------------------------------------------- 基础工具
def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit")


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def fmt_num(v: float) -> str:
    """数值格式：整数不带小数点，非整数保留两位（全文禁千分位）。"""
    return f"{v:.0f}" if abs(v - round(v)) < 1e-6 else f"{v:.2f}"


def months_text(months, order) -> str:
    """把命中的月份压缩成中文表述（按给定季节顺序），如 [6,7,8,9]→“6月至9月”、
    [12,1]→“12月和1月”、[11,12,1,2,3]→“11月至次年3月”。"""
    ms = [m for m in order if m in set(months)]
    if not ms:
        return ""
    # 在 order 里找连续区段
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
        cross = first in (11, 12) and last in (1, 2, 3)      # 跨年
        if len(seg) == 1:
            parts.append(f"{first}月")
        elif len(seg) == 2:
            parts.append(f"{first}月和{last}月")              # 两个月用“和”（与样板一致）
        elif cross:
            parts.append(f"{first}月至次年{last}月")
        else:
            parts.append(f"{first}月至{last}月")
    if len(parts) == 1:
        return parts[0]
    return "以及".join([("和".join(parts[:-1])), parts[-1]]) if len(parts) == 2 else \
        "、".join(parts[:-1]) + "以及" + parts[-1]


# ---------------------------------------------------------------- 判定
def yearly_hits(data: dict):
    """逐年算基准与三季命中；返回 (明细列表, 告警列表)。"""
    out, warns = [], []
    for ey in sorted(data.get("energy_yearly") or [], key=lambda x: x.get("year") or 0):
        year = ey.get("year")
        m = ey.get("monthly_electricity_kwh") or []
        if len(m) < 12:
            warns.append(f"{year}年 逐月用电量不足 12 个月（{len(m)}），已跳过")
            continue
        trio = {k: float(m[k - 1]) for k in SHOULDER}
        base = sum(trio.values()) / 3
        hits = {
            "cool": sorted(k for k in COOL if float(m[k - 1]) > base * COOL_THR),
            "heat": sorted(k for k in HEAT if float(m[k - 1]) > base * HEAT_THR),
            "shoulder": sorted(k for k in SHOULDER if float(m[k - 1]) > base * SHOULDER_THR),
        }
        out.append({"year": year, "base": base, "trio": trio, "hits": hits,
                    "monthly": [float(v) for v in m]})
    return out, warns


def majority(details, key):
    from collections import Counter
    c = Counter()
    for d in details:
        c.update(d["hits"][key])
    return sorted(k for k, n in c.items() if n >= 2)


def detect_devices(data: dict):
    """从 equipment 判 循环水泵 / 分体空调 是否存在（返回 (有泵, 有分体, 佐证名)）。"""
    pump, split, names = False, False, []
    for e in data.get("equipment") or []:
        cat = (e.get("category") or "").strip()
        name = (e.get("name") or "").strip()
        if "泵" in name and ("循环" in name or cat == "输配设备"):
            pump = True
            names.append(f"[泵]{name}")
        if cat == "空调" and any(k in name for k in ("分体", "挂机", "柜机")):
            split = True
            names.append(f"[分体]{name}")
    return pump, split, names


def detect_heating(data: dict):
    """判 市政供暖 / 供暖形式 / 热源是否溴化锂。"""
    m = data.get("metering") or {}
    pay = str(m.get("heat_pay_type") or "")
    forms = sorted({(b.get("heating_source") or "").strip()
                    for b in (data.get("buildings") or []) if (b.get("heating_source") or "").strip()})
    joined = "、".join(forms) + " " + pay
    city = ("市政" in joined) or ("集中供热" in joined)
    absorption = any(k in joined for k in ABSORPTION)
    return city, (forms[0] if forms else "集中供热"), absorption, joined.strip()


def detect_cooling(data: dict):
    """冷源类型 + 是否电驱动 + 是否有输配设备（冷冻/冷却水泵、冷却塔）。"""
    forms = sorted({(b.get("cooling_source") or "").strip()
                    for b in (data.get("buildings") or []) if (b.get("cooling_source") or "").strip()})
    text = "、".join(forms)
    absorption = any(k in text for k in ABSORPTION)
    elec = (not absorption) and any(k in text for k in ELEC_COOLING)
    dist = False
    for e in data.get("equipment") or []:
        name = (e.get("name") or "").strip()
        if any(k in name for k in ("冷冻水泵", "冷却水泵", "冷却塔", "循环水泵")):
            dist = True
    return text or "（未记录）", elec, absorption, dist, forms


# ---------------------------------------------------------------- 造句
def build_sentences(data: dict, details: list, warns: list):
    cool_m = majority(details, "cool")
    heat_m = majority(details, "heat")
    shoulder_hits = [(d["year"], d["hits"]["shoulder"], [d["monthly"][k - 1] for k in d["hits"]["shoulder"]])
                     for d in details if d["hits"]["shoulder"]]
    unit = ((data.get("base") or {}).get("unit_short")
            or (data.get("base") or {}).get("unit_name") or "该单位")
    cool_txt, heat_txt = months_text(cool_m, COOL_ORDER), months_text(heat_m, HEAT_ORDER)
    cooling_txt, elec, absorption, dist, _ = detect_cooling(data)
    city, heat_form, heat_abs, heat_raw = detect_heating(data)
    pump, split, dev_names = detect_devices(data)

    blocks = []
    # ① 月份首句
    if cool_txt or heat_txt:
        body = []
        if cool_txt:
            body.append(cool_txt)
        if heat_txt:
            body.append(heat_txt)
        blocks.append(f"{unit}用电量较大月份为每年的" + "以及".join(body) + "。")
    else:
        warns.append("供冷季与供热季都没有多数年份命中的月份 → 不写月份首句")

    # ② 供冷季原因句
    if cool_m:
        tail_plain = ("6月至9月单月用电量明显高于4月、5月以及10月无制冷需求或需求较少的月份，"
                      "单月用电量变化受季节性影响因素较大。")
        tail_causal = "因此" + tail_plain
        if elec:
            blocks.append(
                f"结合制冷空调形式分析，夏季空调冷源为{cooling_txt}，为电驱动式制冷机组，"
                f"制冷动力消耗为电，受夏季制冷因素的影响，{tail_plain}")
        elif absorption and dist:
            blocks.append(
                f"结合制冷空调形式分析，夏季空调冷源为{cooling_txt}，制冷主机非电驱动，"
                f"但冷冻水泵、冷却水泵及冷却塔等输配设备运行，{tail_causal}")
        elif absorption:
            blocks.append(
                f"结合制冷空调形式分析，夏季空调冷源为{cooling_txt}，制冷主机非电驱动，"
                f"6月至9月单月用电量高于过渡季，主要是有部分其他制冷形式设备导致，"
                f"单月用电量变化受季节性影响因素较大。")
        else:
            warns.append(f"冷源类型无法判定电驱动/吸收式（记录为「{cooling_txt}」）→ 供冷句按电驱动模板写，请人工复核")
            blocks.append(
                f"结合制冷空调形式分析，夏季空调冷源为{cooling_txt}，为电驱动式制冷机组，"
                f"制冷动力消耗为电，受夏季制冷因素的影响，{tail_plain}")
    else:
        warns.append("供冷季无多数年份命中的月份 → 不写供冷句")

    # ③ 供热季原因句
    if heat_m:
        tail_h = "因此供暖季用电量同样高于4月、5月以及10月无供暖需求或需求较少的月份。"
        if city:
            if pump and split:
                blocks.append("冬季以市政供暖为主，热源主要为供暖热水，热源形式虽不是电力直接驱动，"
                              f"但换热站循环泵24h开启，同时部分房间使用分体空调供暖，{tail_h}")
            elif pump:
                blocks.append(f"虽然是市政供暖，但换热站循环泵24h开启，{tail_h}")
            elif split:
                blocks.append(f"部分房间使用分体空调供暖，{tail_h}")
            else:
                blocks.append(f"冬季以市政供暖为主，同时有部分其他供暖形式设备运行，{tail_h}")
        elif heat_abs:
            if pump and split:
                blocks.append(f"冬季以{heat_form}为主，热源为{heat_form}，换热站循环泵24h开启，"
                              f"同时部分房间使用分体空调供暖，{tail_h}")
            elif pump:
                blocks.append(f"冬季以{heat_form}为主，热源为{heat_form}，换热站循环泵24h开启，{tail_h}")
            elif split:
                blocks.append(f"部分房间使用分体空调供暖，{tail_h}")
            else:
                blocks.append(f"冬季以{heat_form}为主，同时有部分其他供暖形式设备运行，{tail_h}")
        else:
            warns.append(f"非市政供暖且热源非溴化锂（记录为「{heat_raw or '未记录'}」）→ 按“其他供暖形式设备”兜底，请人工复核")
            blocks.append(f"冬季以{heat_form}为主，同时有部分其他供暖形式设备运行，{tail_h}")
    else:
        warns.append("供热季无多数年份命中的月份 → 不写供热句")

    # ④ 收尾句
    blocks.append(f"{unit}逐月用电量变化符合单位用能变化以及季节性用能变化规律。")

    # ⑤ 平台异常说明段（月粒度，合并一段）
    month_notes = []
    for ey in sorted(data.get("energy_yearly") or [], key=lambda x: x.get("year") or 0):
        for a in (ey.get("anomalies") or []):
            if a.get("period_type") != "month":
                continue
            # ★2026-10-15 能源名闸：本节是**电力**节，只允许电的月异常进来。
            # 此前不过滤能源名——平台若登记"水/天然气"的月异常，会被写成"…用电量同比…"。
            # （实测全库能源名有 '电'/'电能' 两种写法，故用包含匹配而非等值。）
            _en = str(a.get("energy_name") or "").strip()
            if _en and "电" not in _en:
                warns.append(f"{ey.get('year')}年{a.get('period')}{_en}异常未写入 5.2.1"
                             f"（能源名不含「电」）→ 应写进对应品种小节")
                continue
            title = a.get("title") or ""
            direction = "下降" if "下降" in title else "上升"
            rate = a.get("rate_value")
            # ★2026-10-15 数值口径：整数不带小数位、小数两位（平台登记 39.0 写成 39%）
            rate_txt = (fmt_num(float(rate)) + "%") if rate is not None else ""
            desc = (a.get("desc_no_year") or a.get("desc") or "").strip().rstrip("。；")
            mth = re.match(r"(\d{1,2})月", str(a.get("period") or ""))
            when = f"{ey.get('year')}年{mth.group(1)}月" if mth else f"{ey.get('year')}年"
            month_notes.append((int(ey.get("year") or 0), int(mth.group(1)) if mth else 0,
                                f"{when}用电量同比{direction}{rate_txt}，主要是{desc}"))
    if month_notes:
        month_notes.sort()
        blocks.append("；".join(x[2] for x in month_notes) + "。")

    # ⑥ 红色注（过渡季待核实，仅最后一块）
    for year, ms, vals in shoulder_hits:
        for mm, v in zip(ms, vals):
            blocks.append(f"注：{year}年{mm}月用电量为{fmt_num(v)}kWh明显高于过渡季基准，异常原因请核实。")

    info = {
        "unit": unit, "yearly": details, "cool_months": cool_m, "heat_months": heat_m,
        "shoulder_hits": shoulder_hits, "cooling": cooling_txt, "cooling_elec": elec,
        "cooling_absorption": absorption, "cooling_dist": dist,
        "city_heating": city, "heat_form": heat_form, "heat_absorption": heat_abs,
        "pump": pump, "split_ac": split, "device_evidence": dev_names,
    }
    return blocks, info, warns


# ---------------------------------------------------------------- md 写回
def apply_to_md(md_path: str, blocks: list, info: dict) -> str:
    """幂等写回 5.2.1：替换「图5.3 图注之后 → 下一个 ### 标题之前」的整段。

    保留块内已有的“平台异常说明段”（由本次 ⑤ 重新生成，故先摘除再按新顺序写）。
    """
    lines = open(md_path, encoding="utf-8").read().splitlines()
    s = next((i for i, l in enumerate(lines) if re.match(r"^### 5\.2\.1", l.strip())), None)
    if s is None:
        raise SystemExit("[错误] md 里找不到 '### 5.2.1' 小节")
    e = next((i for i in range(s + 1, len(lines)) if re.match(r"^#{2,3} ", lines[i].strip())), len(lines))
    # 取**最后一个**图注行（＝逐月图 图5.Y）；第一个是总量图（图5.X），不能用
    caps = [i for i in range(s, e) if re.match(r"^图5\.\d", lines[i].strip())]
    if len(caps) < 2:
        raise SystemExit("[错误] 5.2.1 内图注行不足 2 条（应有 总量图 与 逐月图）")
    cap = caps[-1]
    # 图注之后到小节末 = 段4 + ⑤ + ⑥ 的所在区；整段重建
    new_lines = [""] + blocks
    out = lines[:cap + 1] + new_lines + lines[e:]
    open(md_path, "w", encoding="utf-8").write("\n".join(out) + "\n")
    return md_path


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="5.2.1 逐月段归因判定器")
    ap.add_argument("project", help="项目名（~/projects/energy-audit/<项目名>）或项目目录")
    ap.add_argument("--apply", action="store_true", help="写回 chapter_md/ch5_import.md（幂等）")
    ap.add_argument("--json", dest="json_out", default=None, help="把判定结果写成 JSON")
    args = ap.parse_args(argv)

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在: {args.project}")
        return 1
    data_path = os.path.join(pdir, "data.json")
    if not os.path.isfile(data_path):
        print(f"[错误] 缺少 {data_path}")
        return 1
    data = json.load(open(data_path, encoding="utf-8"))

    details, warns = yearly_hits(data)
    if not details:
        print("[错误] 没有可用的逐月用电量（energy_yearly[].monthly_electricity_kwh）")
        return 2
    blocks, info, warns = build_sentences(data, details, warns)

    print(f"[项目] {pdir}")
    print("[逐年判定]")
    for d in details:
        t = d["trio"]
        print(f"  {d['year']}：4月{t[4]:.0f} / 5月{t[5]:.0f} / 10月{t[10]:.0f} → 基准 {d['base']:.0f}"
              f"（平均）｜供冷命中 {'、'.join(str(x)+'月' for x in d['hits']['cool']) or '—'}"
              f"｜供热命中 {'、'.join(str(x)+'月' for x in d['hits']['heat']) or '—'}"
              f"｜过渡季命中 {'、'.join(str(x)+'月' for x in d['hits']['shoulder']) or '—'}")
    print(f"[多数年份] 供冷季 {info['cool_months']}　供热季 {info['heat_months']}")
    print(f"[分支依据] 冷源={info['cooling']}（电驱动={info['cooling_elec']}/吸收式={info['cooling_absorption']}"
          f"/有输配={info['cooling_dist']}）｜市政供暖={info['city_heating']}｜供暖形式={info['heat_form']}"
          f"｜溴化锂={info['heat_absorption']}｜循环水泵={info['pump']}｜分体空调={info['split_ac']}")
    if info["device_evidence"]:
        print(f"           设备佐证：{'、'.join(info['device_evidence'][:8])}")
    print("\n[生成段落]")
    for i, b in enumerate(blocks, 1):
        print(f"  {i}. {b}")
    if warns:
        print(f"\n[告警] {len(warns)} 条：")
        for w in warns:
            print(f"  · {w}")

    if args.json_out:
        json.dump({"info": info, "blocks": blocks, "warnings": warns},
                  open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[输出] {args.json_out}")
    if args.apply:
        md = os.path.join(pdir, "chapter_md", "ch5_import.md")
        if not os.path.isfile(md):
            print(f"[错误] 缺少 {md}（先跑 caliber / prepare_chapter_md）")
            return 1
        apply_to_md(md, blocks, info)
        print(f"[写回] {md}")
    else:
        print("\n（未写回；加 --apply 才落盘）")
    return 2 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
