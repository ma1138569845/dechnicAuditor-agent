#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prepare_writing_context.py — 生成/刷新"三批写章接续契约" <项目>/chapter_md/_context.md

用途（2026-09-18 新增）：三批写章采用"批间不信上文、只信文件"的策略，本文件就是
**每批开工必读的那份文件**——把"唯一口径 + 关键数字 + 已落盘章节 + 术语与写法"固化下来，
解决分批写章容易出现的"软一致性漂移"（措辞/术语/口径）。

用法:
    python prepare_writing_context.py <项目名|项目目录> [--quiet]

退出码:
    0  正常（已生成/刷新）
    1  缺 data.json（先跑采集）

产物: <项目>/chapter_md/_context.md（幂等，可反复运行；每批收工后重跑以刷新"已落盘章节"）
"""
import argparse
import json
import os
import sys
from datetime import datetime

INDICATOR_LABELS = [
    ("unit_area_non_heating_energy", "单位建筑面积非供暖能耗", "kgce/(m²·a)"),
    ("unit_area_heating", "单位采暖建筑面积供暖能耗", "kgce/(m²·a)"),
    ("unit_area_electricity", "常规用能系统单位建筑面积电耗", "kWh/(m²·a)"),
    ("per_capita_energy", "人均综合能耗", "kgce/(p·a)"),
    ("water_indicator", "取水指标（按机构类型自适应）", "见指标定义"),
]

VALUE_KEYS = ("kgce_per_m2", "kgce_per_person", "kwh_per_m2", "value", "v", "water_value")

# 本批蓝本：按机构类型映射到 audit-examples.md 的对应小节（2026-09-20）
BLUEPRINT_SECTIONS = {
    "medical": "§医院实例（含 §三级医院案例）",
    "government": "§法院/党政机关实例",
    "education": "§学校实例模板",
    "venue": "§法院/党政机关实例（场馆类暂无专用蓝本，形态参照机关）",
    "service": "§法院/党政机关实例（政务服务中心暂无专用蓝本，形态参照机关）",
}


def blueprint_section(inst_type: str, category: str) -> str:
    key = (inst_type or "").strip().lower()
    if not key:
        cat = category or ""
        if "医" in cat:
            key = "medical"
        elif any(k in cat for k in ("教育", "学校", "高校", "学院")):
            key = "education"
        elif any(k in cat for k in ("场馆", "体育", "文化", "图书馆")):
            key = "venue"
        elif "政务" in cat:
            key = "service"
        else:
            key = "government"
    return BLUEPRINT_SECTIONS.get(key, BLUEPRINT_SECTIONS["government"])


def projects_root() -> str:
    return os.environ.get("HERMES_PROJECTS_ROOT") or os.path.join(
        os.path.expanduser("~"), "projects", "energy-audit"
    )


def resolve_project_dir(arg: str) -> str:
    if os.path.isdir(arg):
        return os.path.abspath(arg)
    cand = os.path.join(projects_root(), arg)
    return os.path.abspath(cand) if os.path.isdir(cand) else ""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def pick_value(node: dict):
    for key in VALUE_KEYS:
        if isinstance(node.get(key), (int, float)):
            return node[key], key
    return None, None


def first_heading(md_path: str) -> str:
    try:
        with open(md_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        pass
    return ""


# S3（datava V1 DATA_CHECK）产出的第7章写作素材。2026-09-20 接入契约：
# 此前它只在 datava 侧落盘、author 侧**没有任何指令去读**（P3-2 的缺口）。
DIAGNOSIS_FILE = "diagnosis_chapter7_material.txt"


def diagnosis_digest(pdir: str, limit: int = 8):
    """解析第7章素材 → [(问题标题, 严重程度)]，按严重程度排序（critical 优先）。"""
    path = os.path.join(pdir, DIAGNOSIS_FILE)
    if not os.path.isfile(path):
        return []
    rows, cur = [], ""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                s = raw.strip()
                if s.startswith("### "):
                    cur = s[4:].strip()
                elif cur and s.startswith("- 严重程度"):
                    rows.append((cur, s.split(":", 1)[-1].strip()))
                    cur = ""
    except OSError:
        return []
    order = {"critical": 0, "warning": 1, "info": 2}
    rows.sort(key=lambda r: order.get(r[1], 3))
    return rows[:limit]

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成写章接续契约 _context.md")
    ap.add_argument("project", help="项目名（对应 ~/projects/energy-audit/<项目名>/）或项目目录")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    pdir = resolve_project_dir(args.project)
    if not pdir:
        print(f"[错误] 项目目录不存在：{args.project}（查找根 {projects_root()}）")
        return 1
    data = load_json(os.path.join(pdir, "data.json"))
    if not data:
        print(f"[错误] 缺 data.json：{pdir}（先跑采集）")
        return 1

    base = data.get("base") or {}
    ind = load_json(os.path.join(pdir, "indicators.json")) or {}
    md_dir = os.path.join(pdir, "chapter_md")
    os.makedirs(md_dir, exist_ok=True)

    lines = [
        "# 接续契约（写章三批开工必读）",
        "",
        f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M}　来源：`data.json` + `indicators.json` + `chapter_md/`。",
        "> 三批写章策略是「批间不信上文、只信文件」——**本文件就是每批开工第一步要读的文件**；",
        "> 每批收工后重跑本脚本，刷新「已落盘章节」一节，供下一批接续。",
        "",
        "## 一、唯一口径（数值只从这里取，禁从会话上下文或前序章节文本提取）",
        "",
        "| 项 | 值 | 来源 |",
        "|---|---|---|",
        f"| 单位全称 | {base.get('unit_name') or '【待补充】'} | data.json → base.unit_name |",
        f"| 审计期 | {base.get('audit_period') or '【待补充】'} | data.json → base.audit_period |",
        f"| 基准期 | {base.get('base_period') or '【待补充】'} | data.json → base.base_period |",
        f"| 建筑面积（m²） | {base.get('building_area') or '【待补充】'} | data.json → base.building_area |",
        f"| 用能人数 | {base.get('people_count') or '【待补充】'} | data.json → base.people_count |",
        f"| 机构类型 | {ind.get('institution_type') or base.get('institution_category') or '【待补充】'} | data.json / indicators.json |",
        "",
        "## 二、关键数字（正文引用必须与此一致）",
        "",
    ]

    if ind:
        lines += [
            f"> 指标计算年度：{ind.get('year')}　计算时间：{ind.get('calculated_at')}",
            "",
            "| 指标 | 值 | 定额（约束/基准/引导） | 标准与来源 | 评价结果 |",
            "|---|---|---|---|---|",
        ]
        for key, label, unit in INDICATOR_LABELS:
            node = ind.get(key)
            if not isinstance(node, dict):
                continue
            value, vkey = pick_value(node)
            bench = node.get("benchmark") or {}
            quota = " / ".join(
                str(bench.get(k)) for k in ("约束值", "基准值", "引导值") if bench.get(k) is not None
            ) or "—"
            std = bench.get("标准") or "—"
            anchor = bench.get("锚点") or bench.get("原文锚点") or "【缺锚点】"
            lines.append(
                f"| {label} | {value if value is not None else '【待补充】'} {unit} | {quota} "
                f"| {std}（来源 {bench.get('来源') or '—'}；锚点 {anchor}） | {bench.get('评价结果') or '—'} |"
            )
        baseline = ind.get("baseline") or {}
        usage = (baseline.get("usage") or {}) if isinstance(baseline, dict) else {}
        if usage:
            lines += ["", "### 能耗基准（第5.4 / 第8.3 引用）", "", "| 品种 | 基准值 | 单位 | 取法 |", "|---|---|---|---|"]
            for name, item in usage.items():
                if isinstance(item, dict):
                    lines.append(
                        f"| {name} | {item.get('基准值')} | {item.get('单位') or ''} | {item.get('方法') or ''} |"
                    )
    else:
        lines.append("> ⚠️ 未找到 `indicators.json`：请先跑 `caliber_agent.py` 再写章（第5章与指标以它为唯一来源）。")

    lines += ["", "## 三、已落盘章节（其余为待写；**禁止重复生成已存在的章**）", ""]
    order = [f"ch{i}.md" for i in range(1, 9)] + ["appendix.md"]
    found = []
    for name in order:
        path = os.path.join(md_dir, name)
        if os.path.isfile(path):
            found.append((name, first_heading(path), os.path.getsize(path)))
    if found:
        lines += ["| 文件 | 首标题 | 大小 |", "|---|---|---|"]
        for name, head, size in found:
            lines.append(f"| {name} | {head or '—'} | {size} B |")
    else:
        lines.append("（尚无落盘章节：本批为批1）")
    lines += [
        "",
        "## 四、术语与写法统一（跨批必须一致）",
        "",
        "- 称谓：首次出现用**单位全称**，其后可在括号内给简称；正文禁止「贵单位／本单位」。",
        "- 时间口径：`审计期`（被审计年度）、`基准期` 三个字不要混用；格式 `YYYY年M月—YYYY年M月`（全角 —）。",
        "- 指标名称：与第二节表格中的名称逐字一致（不同机构类型取水指标名称不同）。",
        "- 占位语义：`【待补充】`= 数据缺失待人工补录；`【待核验】`= 标准/定额未取得权威原文；`【待核实】`= 数据存疑已提请单位确认。",
        "- 措辞与禁词：见 `energy-audit-style/references/rules.md`（评价短语、禁词表、句法骨架）。",
        "- 数值引用：只从 `data.json` / `indicators.json` / `chapter5.md` 读取；**禁止引用前序章节文本里的数字**。",
        "",
        "## 五、本批蓝本（形态参照，只学形态）",
        "",
        "| 项 | 值 |",
        "|---|---|",
        "| 蓝本文件 | `energy-audit-report/references/audit-examples.md` |",
        f"| 本机构类型小节 | {blueprint_section(ind.get('institution_type'), base.get('institution_category'))} |",
        "| 可复用（形态 + 固定表述） | 章节骨架 / 表格习惯 / 措辞粒度；1.1 定义段、1.3 三段式、1.5 审计过程、1.6 依据清单、4.1 计量六条、5.3 指标定义等固定表述 |",
        "| **必须替换为本项目数据** | 单位名 / 地址 / 人数 / 面积 / 能耗 / 费用 / 设备 / 定额取值 / 问题与建议 |",
        "| 交付前自检 | `python <skills>/ea-validation/scripts/verify_variables_provenance.py <项目名> [--blueprint <本类成稿.md>]` |",
        "",
        "> 批1（封面+第1~4章）读本类小节的「报告结构 / 报告编写要点 / 表格骨架」；批2/批3（第5~8章）读「指标口径 / 节能潜力·问题清单」。",
        "",
        "## 六、本批可用素材（写作输入；先用现成的，不要临场编）",
        "",
    ]

    # 6.1 第7章诊断素材（S3 产出）
    diag = diagnosis_digest(pdir)
    diag_path = os.path.join(pdir, DIAGNOSIS_FILE)
    if diag:
        lines += [
            f"**第7章诊断素材**：`<项目>/{DIAGNOSIS_FILE}`（S3 产出，共 {len(diag)} 条，按严重度排序）",
            "",
            "| # | 诊断出的问题 | 严重程度 |",
            "|---|---|---|",
        ]
        for i, (title, sev) in enumerate(diag, 1):
            lines.append(f"| {i} | {title} | {sev} |")
        lines += [
            "",
            "> **使用规则（写 7.1 前必读原文）**：",
            "> 1. 素材里的「推断原因」是**候选**（带置信度）——必须用本项目台账/逐月数据验证后再写，**不得直接当结论**；验证不了就写「疑似」并注明待核实。",
            "> 2. 素材里的「建议措施」及节能率/投资级别/回收期是**通用区间**，写进 7.2 前须与本项目实际（设备型号/投资额/运行工况）对齐，或明确标注为参考区间。",
            "> 3. `critical` / `warning` 的条目**必须**进 7.1；再按 `chapter-guides-6-8.md` 第7章的「实锤类」规则补足；问题条数 = 数据异常类（素材） + 实锤类，与 7.2 建议一一对应。",
            "> 4. 素材只覆盖「数据异常类」，**不能替代**实锤类问题（计量/设备/围护结构）。",
            "",
        ]
    elif os.path.isfile(diag_path):
        lines += [f"- 第7章诊断素材存在但未解析出条目：`{diag_path}`（请人工查看）", ""]
    else:
        lines += [
            f"- ⚠️ **无第7章诊断素材**（`{DIAGNOSIS_FILE}` 不存在）：请确认 S3（datava `--mode DATA_CHECK`）已跑；",
            "  7.1 只能按 `chapter-guides-6-8.md` 第7章的规则从本项目数据自行归纳，**不得编造异常**。",
            "",
        ]

    # 6.2 同类成稿参考（按章取全文）
    inst_cat = base.get("institution_category") or ""
    lines += [
        "**同类成稿参考（按章取全文）**：`reference_library.search_local_references(chapter, tags)`"
        "（本地打分、离线可用；无同类型时返回空并给出 note，**不要用不相关报告充当参考**）",
        "",
        f"- tags 至少含 `institution_category={inst_cat or '【待补充】'}`；`chapter` 取本章名（如 `第7章`）。",
        "- 想跨库扩大召回：`energy_audit_rag_search`（多路召回 + 重排，返回带 route/rerank 可解释）。",
        "- **查依据/条文原文**（定额出自哪一条、规范怎么要求、办法怎么规定）："
        "`energy_audit_rag_search(query, kbs=\"standards\")` —— 命中定额标准库 + 技术规范库的"
        "**条文**（`kind=standard_clause`）。它**不是**同类成稿：可作依据引用，"
        "**不得**照它的写法仿报告段落。",
        "- 「参考什么」的完整决策表见 `energy-audit-core/references/WORKFLOW.md` 第六节。",
        "",
        "## 七、本批开工/收工检查",
        "",
        "- [ ] 开工：已读本文件；数值口径与第一节一致",
        "- [ ] 开工：写第 6/7 章前已读第六节列出的素材（尤其第7章诊断素材原文）",
        "- [ ] 写章：只写 `chapter_md/` 中尚不存在的章（见第三节）",
        "- [ ] 收工：本章已落盘 `chapter_md/chN.md`，并**重跑本脚本**刷新第三节",
        "",
    ]

    out = os.path.join(md_dir, "_context.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    if not args.quiet:
        print(f"[契约] 已生成/刷新：{out}")
        print(f"       已落盘章节 {len(found)} 个：" + ("、".join(n for n, _, _ in found) if found else "（无，批1）"))
        if ind:
            missing = [
                label for key, label, _ in INDICATOR_LABELS
                if isinstance(ind.get(key), dict)
                and not ((ind[key].get("benchmark") or {}).get("锚点"))
            ]
            if missing:
                print(f"       ⚠️ 以下指标的定额值缺「原文锚点」（建议跑 verify_benchmark_sources.py 并补锚点）：{'、'.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
