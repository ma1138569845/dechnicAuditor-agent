#!/usr/bin/env python3
"""
能源审计 Kanban 编排器 — 从 plan.json 生成 setup.sh。

一个公共机构 = 一个项目 = 一份能源审计报告。
每项目 6 步任务 + 1 汇总 Director。

任务图:
  Collect → DataVA(DATA_CHECK) → Calculate → DataVA(INDICATOR_REVIEW)
    → Report → DataVA(REPORT_REVIEW) → Director(editor, 专职汇总审查)

Director assignee = profiles["director"]（推荐 editor 专职），缺省回退 reporter。

DataVA 在三个检查点各介入一次，每次审查不同内容：
  V1: 数据完整性 + 异常检测 + KG诊断
  V2: 指标年际对比 + 对标合理性 + 数据一致性
  V3: 跨章一致性 + 格式规范 + 结论完整性

工作区根目录: <HERMES_HOME>/projects/energy-audit/
所有 task body 路径在 bootstrap 时完全展开为绝对路径。

参考: kanban-video-orchestrator/scripts/bootstrap_pipeline.py (MIT, Nous Research)
"""

from __future__ import annotations

import argparse, json, os, re, shlex, sys
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_GREP_TASK_ID = r"grep -oP 't_[a-z0-9]+(?=\s|\$|\")'"


def _hermes_home() -> str:
    h = os.environ.get("HERMES_HOME", "")
    if h:
        return h
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser("~/AppData/Local"))
    return os.path.join(local, "hermes")


def _resolve_base() -> str:
    return os.path.join(_hermes_home(), "projects", "energy-audit").replace("\\", "/")


def load_template(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def validate_plan(plan: dict) -> list[str]:
    errors = []
    is_batch = "projects" in plan
    is_single = "project_name" in plan
    if not is_batch and not is_single:
        errors.append("必须包含 'projects'（批量）或 'project_name'（单项目）")
        return errors
    if is_batch and is_single:
        errors.append("'projects' 和 'project_name' 不能同时存在")

    projects = []
    if is_batch:
        if not isinstance(plan.get("projects"), list) or not plan["projects"]:
            errors.append("projects 必须是非空列表")
        else:
            projects = plan["projects"]
    else:
        projects = [{
            "name": plan["project_name"],
            "slug": plan.get("slug", re.sub(r'[^\w\-]', '', plan["project_name"])[:30].lower()),
            "config": plan.get("config", ""),
            "audit_type": plan.get("audit_type", "public_institution"),
            "institution_category": plan.get("institution_category", ""),
            "audit_years": plan.get("audit_years", [2022, 2023, 2024]),
        }]

    seen_slugs = set()
    for i, proj in enumerate(projects):
        for k in ["name", "config"]:
            if k not in proj:
                errors.append(f"项目[{i}] 缺失: {k}")
        slug = proj.get("slug", "")
        if slug:
            if not SLUG_RE.match(str(slug)):
                errors.append(f"项目[{i}].slug='{slug}' 不合法")
            if slug in seen_slugs:
                errors.append(f"项目[{i}].slug='{slug}' 重复")
            seen_slugs.add(slug)
        config_path = proj.get("config", "")
        if config_path and not Path(config_path).exists():
            errors.append(f"项目[{i}]({proj.get('name','?')}) config 不存在: {config_path}")

    pf = plan.get("profiles", {})
    for role in ["collector", "validator", "calculator", "reporter"]:
        if role not in pf or not pf[role]:
            errors.append(f"profiles 缺失角色: {role}")
    # director 可选：缺省时 Director 汇总任务回退 reporter（editor 专职 Director 为推荐配置）
    return errors


def validate_profiles_exist(plan: dict) -> list[str]:
    errors = []
    profiles_root = Path(_hermes_home()) / "profiles"
    for role in ["collector", "validator", "calculator", "reporter"]:
        name = plan.get("profiles", {}).get(role)
        if name and not (profiles_root / name).is_dir():
            errors.append(f"Profile '{name}' ({role}) 不存在于 {profiles_root}")
    return errors


def _extract_projects(plan: dict) -> list[dict]:
    if "projects" in plan:
        projects = list(plan["projects"])
    else:
        projects = [{
            "name": plan["project_name"],
            "slug": plan.get("slug", re.sub(r'[^\w\-]', '', plan["project_name"])[:30].lower()),
            "config": plan.get("config", ""),
            "audit_type": plan.get("audit_type", "public_institution"),
            "institution_category": plan.get("institution_category", ""),
            "audit_years": plan.get("audit_years", [2022, 2023, 2024]),
        }]
    for i, proj in enumerate(projects):
        if not proj.get("slug"):
            proj["slug"] = f"project-{i+1:03d}"
    return projects


def render_setup_sh(plan: dict) -> str:
    tmpl = load_template("setup.sh.tmpl")
    projects = _extract_projects(plan)
    profiles = plan["profiles"]
    kanban = plan.get("kanban", {})
    max_concurrent = kanban.get("max_concurrent_projects", 5)
    max_runtime = kanban.get("max_runtime_per_task_seconds", 1800)
    n_projects = len(projects)

    BASE = _resolve_base()

    mkdir_lines = [f'mkdir -p "{BASE}/{proj["slug"]}/{{data,charts,output}}"'
                   for proj in projects]
    cp_lines = [f'cp "{proj["config"]}" "{BASE}/{proj["slug"]}/config.json"'
                for proj in projects]

    kanban_fn_lines = []
    report_task_vars: list[str] = []

    for i, proj in enumerate(projects):
        idx = i + 1
        slug = proj["slug"]
        name = proj["name"]
        inst_cat = proj.get("institution_category", "")
        years = proj.get("audit_years", [2022, 2023, 2024])
        years_str = ", ".join(str(y) for y in years)
        tenant = slug
        quoted_name = shlex.quote(name)  # V1 body 脚本调用行的安全项目名

        c_var = f'T{idx:03d}_C'
        v1_var = f'T{idx:03d}_V1'
        a_var = f'T{idx:03d}_A'
        v2_var = f'T{idx:03d}_V2'
        r_var = f'T{idx:03d}_R'
        v3_var = f'T{idx:03d}_V3'

        W = f"{BASE}/{slug}"
        D = f"{W}/data"
        CFG = f"{W}/config.json"
        DATA = f"{D}/data.json"
        VAL = f"{D}/validation.json"
        IND = f"{D}/indicators.json"
        CH5 = f"{D}/chapter5.md"
        CHTS = f"{W}/charts"
        RPT = f"{W}/output/{name}_能源审计报告.docx"
        IND_REVIEW = f"{D}/indicator_review.json"
        RPT_REVIEW = f"{D}/report_review.json"

        # ── Task 1: Collect ──
        kanban_fn_lines.append(f'''# ── 项目 {idx}/{n_projects}: {name} ──
echo "  📋 [C] 采集: {name}"
{c_var}=$(hermes kanban create \\
    "采集数据 - {name}" \\
    --assignee {profiles["collector"]} \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是 DataCollection Agent。请采集公共机构「{name}」的能源审计数据。

数据来源（优先级从高到低）:
1. PG 数据库 (10.10.1.165:5432/dc_energy_audit2)
2. 配置文件: {CFG}
3. 对话交互（缺失字段向我确认）

审计年度: {years_str}
机构类型: {inst_cat}

步骤:
1. 读取配置文件 {CFG}
2. 从 PG 查询项目/建筑/能耗/设备/人员数据；PG 不可用则从 config 取
3. 持久化到: {DATA}
4. 缺失字段标注【待补充】，不可编造

完成后调用 kanban_complete(summary="...", metadata={{"data_path":"{DATA}"}})。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${c_var}"''')

        # ── Task 2: DataVA V1 (DATA_CHECK) ──
        kanban_fn_lines.append(f'''echo "  📋 [V1] 数据审查: {name}"
{v1_var}=$(hermes kanban create \\
    "[V1] 数据审查 - {name}" \\
    --assignee {profiles["validator"]} \\
    --parents "${{{c_var}}}" \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是 DataVA Agent。当前模式: DATA_CHECK — 采集后数据审查。

输入: {DATA}

审查内容:
1. 完整性检查: 封面/建筑/能耗/设备/人员 15+字段逐项检查
2. 异常检测: 年度同比≥±30% + 月度离群>2σ
3. KG 因果诊断: 30条因果链推理异常原因+措施
4. 质量评级: A/B/C/D

规则:
- 不修改原始数据（只读）
- 异常自动确认(confirmed:true)，明显数据错误标记(is_data_error:true)
- 省级规章 web_search 验证
- 用电、用水月度数据不存在时提示缺失

输出: {VAL}

完成判定（按 data_verification_agent.py 退出码路由）:
- 退出码 0 (pass/warn): kanban_complete(summary="<结论>", metadata={{"validation_path":"{VAL}"}})
- 退出码 1 (error): kanban_block(reason="<脚本 error 原文，三段式>", kind="dependency")
  -> error 含"由 datacollection 通过..."时，主编会解析并派补采工单
- 退出码 2 (P0 阻塞): kanban_block(reason="P0: <首条 Finding title>", kind="needs_input")

运行脚本获取退出码与 error:
python "<skill>/scripts/data_verification_agent.py" {quoted_name} --mode DATA_CHECK --json
从输出 JSON 的 error 字段取三段式 reason，传入 kanban_block。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${v1_var}"''')

        # ── Task 3: Calculate ──
        kanban_fn_lines.append(f'''echo "  📋 [A] 计算: {name}"
{a_var}=$(hermes kanban create \\
    "计算指标+第5章 - {name}" \\
    --assignee {profiles["calculator"]} \\
    --parents "${{{v1_var}}}" \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是 Caliber Agent。请为「{name}」计算能耗指标并生成第5章。

输入: {VAL}

指标（三级兜底 DB→用户→GB/DB37）:
1. 单位建筑面积非供暖能耗 (等效电法 0.31)
2. 常规用能系统单位建筑面积电耗
3. 人均综合能耗
4. 单位开放床日用水量（如为医疗机构且床位数>0）

定额对标: DB37/T 2673-2019（医疗）/ DB37/T 2672-2019（党政机关）

第5章:
- 5.1 能耗概况 + 能源流向图
- 5.2 逐类型逐月数据分析 + 图表
- 5.3 五项指标对标表
- 5.4 能耗基准

输出:
- {IND}
- {CH5}
- {CHTS}/

完成后调用 kanban_complete(summary="...", metadata={{"chapter5_path":"{CH5}","indicators_path":"{IND}"}})。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${a_var}"''')

        # ── Task 4: DataVA V2 (INDICATOR_REVIEW) ──
        kanban_fn_lines.append(f'''echo "  📋 [V2] 指标审查: {name}"
{v2_var}=$(hermes kanban create \\
    "[V2] 指标审查 - {name}" \\
    --assignee {profiles["validator"]} \\
    --parents "${{{a_var}}}" \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是 DataVA Agent。当前模式: INDICATOR_REVIEW — 计算后指标审查。

输入:
- 指标: {IND}
- 第5章: {CH5}
- 原始验证: {VAL}

审查内容:
1. 年际对比: 逐年非供暖能耗/电耗/水耗变化是否在合理范围
   - 非供暖能耗变化>±15% → 检查用电量对应变化
   - 电耗变化>±15% → 检查建筑/设备清单
   - 水耗变化>±25% → 标记建议核实漏损
2. 对标合理性:
   - 约束值/基准值/引导值与 DB37/T 标准一致
   - 医疗机构用 DB37/T 2673-2019，机关用 DB37/T 2672-2019
   - 评价结论与数值一致（如 23.95>22.6 约束值 → "高于约束值"）
3. 数据一致性:
   - 指标中面积/人数与 validation.json 一致
   - 非供暖能耗中供暖电是否正确排除
   - 床位数>0 时床日用水量计算是否正确

输出: {IND_REVIEW}

完成后调用 kanban_complete(summary="...", metadata={{"indicator_review_path":"{IND_REVIEW}"}})。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${v2_var}"''')

        # ── Task 5: Report ──
        kanban_fn_lines.append(f'''echo "  📋 [R] 报告: {name}"
{r_var}=$(hermes kanban create \\
    "生成报告 - {name}" \\
    --assignee {profiles.get("director") or profiles["reporter"]} \\
    --parents "${{{v2_var}}}" \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是小德 Agent（能源审计报告生成专家）。请为「{name}」生成完整报告。

输入:
- 指标: {IND}
- 第5章: {CH5}
- 验证: {VAL}
- 指标审查: {IND_REVIEW}
- 配置: {DATA}

报告结构（8章 .docx）:
1. 审计执行概要（1.6 法规需 web_search 验证）
2. 公共机构基本情况
3. 能源资源管理状况
4. 能源资源计量及统计状况
5. 能耗指标分析（使用 Caliber 产出，不做二次计算）
6. 主要用能系统分析（有数据才写段）
7. 节能效果与潜力分析（从数据推断问题，引用 V1 诊断结果）
8. 审计结论（LLM 自然语言综合，拉前7章数据）

格式规范:
- H1 宋体15pt居中加粗 | H2 宋体14pt加粗 | H3 宋体12pt加粗
- 正文 宋体+TNR 12pt | 表格 宋体12pt 居中对齐 行高1.01cm 垂直居中
- LLM 自然文本，拒绝死板模板填充

输出: {RPT}

完成后调用 kanban_complete(summary="...", metadata={{"report_path":"{RPT}"}})。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${r_var}"''')

        # ── Task 6: DataVA V3 (REPORT_REVIEW) ──
        kanban_fn_lines.append(f'''echo "  📋 [V3] 报告审查: {name}"
{v3_var}=$(hermes kanban create \\
    "[V3] 报告审查 - {name}" \\
    --assignee {profiles["validator"]} \\
    --parents "${{{r_var}}}" \\
    --workspace dir:"{W}" \\
    --tenant {tenant} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 2 \\
    --body "$(cat <<'BODY_EOF'
你是 DataVA Agent。当前模式: REPORT_REVIEW — 生成后报告审查。

输入: {RPT}

审查内容:
1. 数据一致性:
   - 第2章面积 vs 第5章指标所用面积，差值>1%标记
   - 第4章能耗 vs 第5.2逐类型数据，任一能源差值>5%标记
   - 第5.3非供暖能耗 vs 第4章数据反算值（电×0.31/面积），偏差>3%标记
   - 第7章问题数量 = 建议数量（每个问题至少一条建议）
2. 章节完整性:
   - 第1章1.6审计依据含省级规章≥3条，文号格式正确
   - 第6章按设备类别动态H3，有数据才写
   - 第8章含指标汇总、问题摘要、建议条数
3. 格式规范:
   - H1宋体15pt居中加粗/H2宋体14pt加粗/正文12pt
   - 表格12pt居中，行高1.01cm，垂直居中
   - 文件≥100KB，可正常打开

输出: {RPT_REVIEW}

发现严重问题(P0)时调用 kanban_block(reason="P0: ...")。
无严重问题时调用 kanban_complete(summary="...", metadata={{"report_review_path":"{RPT_REVIEW}"}})。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → ${v3_var}"''')

        report_task_vars.append(f'"${{{v3_var}}}"')

    # ── Director ──
    all_vars = " ".join(report_task_vars)
    DIR_SLUG = "director"
    DIR_W = f"{BASE}/{DIR_SLUG}"
    DIR_SUMMARY = f"{DIR_W}/summary"

    kanban_fn_lines.append(f'''# ── Director 汇总 ──
echo "  📋 [D] 汇总: {n_projects} 个项目"
mkdir -p "{DIR_SUMMARY}"
DIRECTOR_TASK=$(hermes kanban create \\
    "[D] 汇总 {n_projects} 个项目" \\
    --assignee {profiles.get("director") or profiles["reporter"]} \\
    --parents {all_vars} \\
    --workspace dir:"{DIR_W}" \\
    --tenant {DIR_SLUG} \\
    --max-runtime {int(max_runtime)}s \\
    --priority 1 \\
    --body "$(cat <<'BODY_EOF'
你是审计汇总审查员。全部 {n_projects} 个项目的报告+审查已完成。

任务:
1. 收集各项目的 report_review.json，统计 P0/P1/P2 问题分布
2. 跨项目指标对比（同类机构，相同指标，是否有异常离群值）
3. 汇总写入 review_report.md

输出:
- {DIR_SUMMARY}/review_report.md
- {DIR_SUMMARY}/all_reports.json

完成后调用 kanban_complete(summary="全部 {n_projects} 项目审查完成")。
BODY_EOF
)" 2>&1 | {_GREP_TASK_ID} || echo "SKIP")
echo "    → $DIRECTOR_TASK"''')

    # 组装
    out = tmpl
    out = out.replace("{{BASE}}", BASE)
    out = out.replace("{{PROJECT_COUNT}}", str(n_projects))
    out = out.replace("{{MAX_CONCURRENT}}", str(max_concurrent))
    out = out.replace("{{COLLECTOR_PROFILE}}", profiles["collector"])
    out = out.replace("{{VALIDATOR_PROFILE}}", profiles["validator"])
    out = out.replace("{{CALCULATOR_PROFILE}}", profiles["calculator"])
    out = out.replace("{{REPORTER_PROFILE}}", profiles["reporter"])
    out = out.replace("{{DIRECTOR_PROFILE}}", profiles.get("director") or profiles["reporter"])
    out = out.replace("{{MKDIR_COMMANDS}}", "\n".join(mkdir_lines))
    out = out.replace("{{CP_COMMANDS}}", "\n".join(cp_lines))
    out = out.replace("{{KANBAN_TASKS}}", "\n".join(kanban_fn_lines))

    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan_json", help="plan.json 路径")
    ap.add_argument("--out", default="setup.sh")
    args = ap.parse_args()

    plan_path = Path(args.plan_json)
    if not plan_path.exists():
        print(f"✗ 文件不存在: {plan_path}", file=sys.stderr)
        return 1
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析失败: {e}", file=sys.stderr)
        return 1

    errors = validate_plan(plan)
    if errors:
        print("✗ 校验失败:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    profile_errors = validate_profiles_exist(plan)
    if profile_errors:
        print("⚠ Profile 缺失:", file=sys.stderr)
        for e in profile_errors:
            print(f"  - {e}", file=sys.stderr)

    setup = render_setup_sh(plan)
    out_path = Path(args.out)
    out_path.write_text(setup, encoding="utf-8")
    os.chmod(str(out_path), 0o755)

    print(f"✓ setup.sh → {out_path}")
    print(f"  基础路径: {_resolve_base()}")
    print(f"  项目数: {len(_extract_projects(plan))}")
    print(f"  总任务数: {len(_extract_projects(plan)) * 6 + 1}")
    print(f"  并行度: {plan.get('kanban', {}).get('max_concurrent_projects', 5)} 项目")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
