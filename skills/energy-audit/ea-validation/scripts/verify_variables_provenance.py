#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_variables_provenance.py — 变量一致性闸门（2026-09-20 新增）

判据（与"防抄查重"不同，见 energy-audit-style/references/rules.md《变量一致性闸门》）：
  **该相同的不查，只查该变的是否真变。**

  固定条款/标准原文/审计程序叙述/结构骨架/术语 —— 相同是正常的，本工具不看；
  项目事实（数值、单位名、地址、人员、设备名、机构名）—— 必须来自本项目数据源。

做法：
  1) 从生成稿抽"变量"：数值（≥3 位或有单位/百分号）、机构名、设备名；
  2) 建三个集合：本项目数据源 S_data（data.json / indicators.json / chapter5.md）、
     蓝本 S_ref（--blueprint 指定，可多个，通常是同类正式成稿）；
  3) 判定：
     · 变量 ∈ S_ref 且 ∉ S_data      → P0【蓝本变量泄漏】（实证串数据）
     · 机构名 ∈ S_ref 且 ∉ S_data    → P0【蓝本专名泄漏】
     · 命中蓝本特征词（仅未提供 --blueprint 时启用；命中词属本项目数据源专名的除外）→ P0
     · 变量 ∉ S_data 且 ∉ S_ref      → P1【待确认：可能编造或派生值（如百分比/均值）】
     · 变量 ∈ S_data                 → 通过

用法:
    python verify_variables_provenance.py <项目名|项目目录> [--file <md>]^
        [--blueprint <蓝本md> ...] [--json] [--quiet]

退出码: 0 = 无 P0（P1 仅提示）；1 = 存在 P0
"""
import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
sys.path.insert(0, _REPO)
try:  # 复用查重白名单：固定条款/标准原文/结构骨架里的内容不算项目变量
    from tools.energy_audit.similarity_gate import filter_whitelist  # type: ignore
except Exception:  # pragma: no cover - 部署环境缺 tools 时降级为不过滤
    def filter_whitelist(text):  # type: ignore
        return text, {}

UNIT = r"(?:kWh|kwh|KWH|m³|m3|GJ|tce|kgce|kg|t|万元|元|人|平方米|m²|%|℃|床|台|只|盏)"
NUM_RE = re.compile(rf"\d[\d,，]*(?:\.\d+)?\s*{UNIT}?")
ORG_RE = re.compile(
    r"[\u4e00-\u9fff]{2,22}?"
    r"(?:人民法院|人民检察院|法院|医院|大学|学院|学校|中学|小学|幼儿园|"
    r"人民政府|管理局|服务中心|事务管理局|机关事务|图书馆|博物馆|体育馆|科技馆|"
    r"委员会|中心|局|厅|公司|集团|研究院|设计院|事务所)"
)
STD_RE = re.compile(r"(?:DB\s?37\s?/?\s?T?|GB\s?/?\s?T?|JGJ|CJJ\s?/?\s?T?|JS\s?/?\s?T)\s?\d+")
# 标准/法规编号整体跨度（含年份、"第N号"）：这些数字属"固定条款"，不是项目变量
STD_SPAN_RE = re.compile(
    r"(?:DB\s?37\s?/?\s?T?|GB\s?/?\s?T?|JGJ|CJJ\s?/?\s?T?|JS\s?/?\s?T|鲁事管发|国管局令|"
    r"省政府令|国家发展改革委|第)\s?[〔\[（(]?\s?\d+(?:\s?[-—–]\s?\d+)?\s?[〕\]）)]?\s?号?"
)
# 年份：4 位数字后紧跟「平方米/㎡/m²/万元」等量纲的属于数量（如"约2000平方米"），不是年份
YEAR_RE = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)(?!\s*[平㎡mM万])")
# 蓝本特征词兜底（未提供 --blueprint 时用；可在项目侧扩充）
BLUEPRINT_HINTS = ("烟台", "开发区", "人社厅", "纪委监委", "审判", "岚山", "高院", "黄渤海新区")

# 通用功能区/举例用语：不是机构专名，也不属于"该变"的项目变量
ORG_SKIP_PREFIX = ("如", "例如", "包括", "即", "含", "以及", "等")
GENERIC_ORG_STOPWORDS = {
    "数据中心", "调度中心", "监控中心", "指挥及控制中心", "办事大厅", "信息机房", "机房",
    "食堂", "洗衣房", "手术室", "消毒供应室", "会议室", "档案室", "地下车库", "门诊楼",
    "病房楼", "综合楼", "办公楼", "教学楼", "宿舍楼", "服务中心",
}
# 纯通用后缀（没有专名部分的匹配不是机构名）
GENERIC_SUFFIX_ONLY = {
    "管理局", "事务管理局", "机关事务管理局", "服务中心", "中心", "局", "厅", "公司",
    "集团", "医院", "学校", "学院", "大学", "委员会", "事务所", "研究院", "设计院",
}
# 固定设定值（空调温度等，属固定条款，不是项目变量）
VALUE_STOPLIST = {"20℃", "26℃", "18℃", "24℃", "22℃", "25℃"}
# 机构名清洗：句首虚词要剥掉；含这些词的匹配是句子片段，直接丢弃
ORG_LEAD_STOP = set("为在由对向其该本与和及等是将把使让经据按的了并而从以")
ORG_FRAGMENT_WORDS = (
    "作为", "现有", "制定", "建立", "完善", "开展", "组织", "加强", "推进", "负责",
    "承担", "按照", "依据", "结合", "满足", "实现", "确保", "医院现有", "下属", "所属",
)


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit"
    )


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def norm_num(token: str) -> str:
    t = token.replace(",", "").replace("，", "").replace(" ", "")
    m = re.match(r"(\d+(?:\.\d+)?)(.*)", t)
    if not m:
        return ""
    number, unit = m.group(1), m.group(2)
    digits = number.replace(".", "")
    if len(digits) < 3 and not unit:
        return ""
    return f"{number}{unit}"


def blank_fixed_spans(text: str) -> str:
    """把标准/法规编号跨度清空，避免把 GB/T 29149 里的 29149 当成项目变量。"""
    return STD_SPAN_RE.sub(" ", text or "")


def extract_numbers(text: str):
    out = set()
    for m in NUM_RE.finditer(blank_fixed_spans(text)):
        v = norm_num(m.group(0))
        if v:
            out.add(v)
    return out


def extract_years(text: str):
    return set(YEAR_RE.findall(blank_fixed_spans(text)))


def extract_orgs(text: str):
    out = set()
    for m in ORG_RE.finditer(text or ""):
        name = m.group(0)
        while name and name[0] in ORG_LEAD_STOP:
            name = name[1:]
        if any(w in name for w in ORG_FRAGMENT_WORDS):
            continue
        if STD_RE.search(name):
            continue
        if name.startswith(ORG_SKIP_PREFIX) or name in GENERIC_ORG_STOPWORDS:
            continue
        if name in GENERIC_SUFFIX_ONLY:
            continue
        if len(name) <= 3 and name.endswith(("局", "厅", "中心", "公司", "集团")):
            continue
        if 3 <= len(name) <= 15:
            out.add(name)
    return out


def is_known_org(name: str, known: set) -> bool:
    """与数据源里的机构名互为子串即视为已知（如『山东省立医院』⊂『山东省立医院东院区』）。"""
    for item in known:
        if item and (name in item or item in name):
            return True
    return False


def numbers_in(obj, acc: set):
    if isinstance(obj, dict):
        for v in obj.values():
            numbers_in(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            numbers_in(v, acc)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        acc.add(f"{obj:g}")
    elif isinstance(obj, str):
        acc |= extract_numbers(obj)


def collect_data_side(project_dir: str):
    numbers, orgs, device_names = set(), set(), set()
    years_from_payload = set()
    for name in ("data.json", "indicators.json"):
        path = os.path.join(project_dir, name)
        if os.path.isfile(path):
            try:
                payload = json.load(open(path, encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            numbers_in(payload, numbers)
            base = payload.get("base") or {}
            for key in ("unit_name", "unit_short", "auditor", "audit_org_name", "address"):
                if base.get(key):
                    orgs |= extract_orgs(str(base[key]))
                    orgs.add(str(base[key]))
            for eq in payload.get("equipment") or []:
                if isinstance(eq, dict) and eq.get("name"):
                    device_names.add(str(eq["name"]))
                    orgs |= extract_orgs(str(eq["name"]))
            for row in payload.get("buildings") or []:
                if isinstance(row, dict) and row.get("name"):
                    device_names.add(str(row["name"]))
                    orgs |= extract_orgs(str(row["name"]))
            # 数据源里文本提到的年份（历史沿革/沿革年份）也算"本项目数据里有的"
            try:
                years_from_payload = extract_years(json.dumps(payload, ensure_ascii=False))
            except (TypeError, ValueError):
                years_from_payload = set()
    # 项目年份：既含审计期/基准期/数据年，也含数据源文本里提到的年份（如单位历史沿革年份）
    years = set(years_from_payload)
    data_path = os.path.join(project_dir, "data.json")
    if os.path.isfile(data_path):
        try:
            payload = json.load(open(data_path, encoding="utf-8"))
            base = payload.get("base") or {}
            for key in ("audit_period", "base_period", "data_start", "data_end",
                        "audit_start", "audit_end"):
                years |= set(re.findall(r"(19\d{2}|20\d{2})", str(base.get(key) or "")))
            for row in payload.get("energy_yearly") or []:
                if isinstance(row, dict) and row.get("year"):
                    years.add(str(int(row["year"])))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    ch5 = os.path.join(project_dir, "chapter5.md")
    if os.path.isfile(ch5):
        text = open(ch5, encoding="utf-8").read()
        numbers |= extract_numbers(text)
    # 裸数字变体：报告里常写"7282人""20549.74平方米"，数据源里存的是数值本身
    bare = set()
    for token in list(numbers):
        m = re.match(r"(\d+(?:\.\d+)?)", token)
        if m:
            bare.add(m.group(1))
    return numbers | bare, orgs, device_names, years


def collect_ref_side(paths):
    numbers, orgs, raw, years = set(), set(), [], set()
    for p in paths:
        if not os.path.isfile(p):
            continue
        text = open(p, encoding="utf-8", errors="replace").read()
        raw.append(text)
        numbers |= extract_numbers(text)
        orgs |= extract_orgs(text)
        years |= extract_years(text)
    return numbers, orgs, raw, years


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="变量一致性闸门：该变的是否真变")
    ap.add_argument("project", help="项目名或项目目录")
    ap.add_argument("--file", action="append", help="生成稿（默认 chapter_md/ch*.md + appendix.md）")
    ap.add_argument("--blueprint", action="append", default=[],
                    help="蓝本文件（同类正式成稿 .md，可多个）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在：{args.project}")
        return 1

    if args.file:
        targets = [p for p in args.file if os.path.isfile(p)]
    else:
        md_dir = os.path.join(pdir, "chapter_md")
        targets = sorted(
            os.path.join(md_dir, n) for n in os.listdir(md_dir)
            if re.match(r"^(ch[1-8]|appendix)\.md$", n)
        ) if os.path.isdir(md_dir) else []
    if not targets:
        print(f"[错误] 未找到生成稿（{pdir}\\chapter_md\\ch*.md）")
        return 1

    data_numbers, data_orgs, device_names, data_years = collect_data_side(pdir)
    ref_numbers, ref_orgs, _, ref_years = collect_ref_side(args.blueprint)
    text = "\n".join(open(p, encoding="utf-8", errors="replace").read() for p in targets)
    # 先剔除"该相同的固定条款"（1.6 依据清单、4.1 计量条文、标准原文、表格骨架、标题），
    # 再抽变量——否则法规年份、条文里的"如数据中心/调度中心"会被误判成蓝本变量。
    text, whitelist_stats = filter_whitelist(text)
    report_whitelist = {"excluded_blocks": whitelist_stats, "excluded_total": sum(whitelist_stats.values())}

    p0, p1 = [], []
    # 1) 蓝本特征词兜底（仅未提供 --blueprint 时启用——提供了蓝本按 2)~3) 逐项比对；
    #    命中词属本项目数据源专名（单位名/地址/建筑名）的，不算泄漏，防本项目专名误报）
    if not args.blueprint:
        _known_names = data_orgs | device_names
        for hint in BLUEPRINT_HINTS:
            if hint in text and not any(hint in str(n) for n in _known_names if n):
                p0.append(f"命中蓝本特征词：{hint}")
    # 2) 数值
    gen_numbers = extract_numbers(text)
    for v in sorted(gen_numbers):
        if v in VALUE_STOPLIST:
            continue
        num = re.match(r"(\d+(?:\.\d+)?)", v).group(1)
        in_data = num in data_numbers or any(
            abs(float(num) - float(d)) <= max(0.01, abs(float(num)) * 0.005)
            for d in data_numbers if d.replace(".", "").isdigit()
        )
        if in_data:
            continue
        if num in ref_numbers:
            p0.append(f"数值 {v} 出现在蓝本、但不在本项目数据源（疑似蓝本变量泄漏）")
        else:
            p1.append(f"数值 {v} 未在本项目数据源找到（可能为派生值或缺失来源）")
    # 2b) 年份
    for y in sorted(extract_years(text)):
        if y in data_years:
            continue
        if y in ref_years:
            p0.append(f"年份 {y} 出现在蓝本、但不在本项目审计期/基准期/数据年（疑似蓝本年份泄漏）")
        else:
            p1.append(f"年份 {y} 未在本项目数据源找到（请核对口径）")
    # 3) 机构名 / 设备名
    gen_orgs = extract_orgs(text)
    for name in sorted(gen_orgs):
        if is_known_org(name, data_orgs):
            continue
        if is_known_org(name, ref_orgs):
            p0.append(f"机构名「{name}」出现在蓝本、但不在本项目数据源（疑似蓝本专名泄漏）")
        else:
            p1.append(f"机构名「{name}」未在本项目数据源找到")
    for name in sorted(device_names):
        if name and name not in text:
            p1.append(f"本项目设备/建筑「{name}」未在文中出现（可能有遗漏）")

    report = {
        "project": os.path.basename(pdir),
        "files": [os.path.basename(p) for p in targets],
        "whitelist": report_whitelist,
        "data_numbers": len(data_numbers),
        "ref_numbers": len(ref_numbers),
        "generated_numbers": len(gen_numbers),
        "p0": p0,
        "p1": p1[:30],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.quiet:
        print(f"=== 变量一致性闸门：{report['project']} ===")
        print(f"  生成稿：{'、'.join(report['files'])}")
        if report_whitelist["excluded_total"]:
            detail = "、".join(f"{k} {v}" for k, v in whitelist_stats.items())
            print(f"  已剔除固定条款块 {report_whitelist['excluded_total']} 个（{detail}）——这些不属于「该变」的变量")
        print(f"  数据源数值 {len(data_numbers)} 个 | 蓝本数值 {len(ref_numbers)} 个 | 生成稿数值 {len(gen_numbers)} 个")
        print(f"  【P0 蓝本变量泄漏】{len(p0)} 项")
        for item in p0[:15]:
            print(f"     ⚠️ {item}")
        print(f"  【P1 待确认（不含固定条款）】{len(p1)} 项" + ("（仅列前 30）" if len(p1) > 30 else ""))
        for item in p1[:10]:
            print(f"     · {item}")
        print(f"=== 结论：{'通过（无蓝本变量泄漏）' if not p0 else '存在 ' + str(len(p0)) + ' 项 P0'} ===")
    return 0 if not p0 else 1


if __name__ == "__main__":
    sys.exit(main())
