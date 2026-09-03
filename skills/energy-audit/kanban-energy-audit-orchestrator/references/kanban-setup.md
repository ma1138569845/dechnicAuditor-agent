# Kanban Setup — EA 项目引导与 Profile 配置

能源审计 Kanban 流水线的项目引导文档：工作区结构、Profile 配置规则、
初始任务创建模式、环境前置检查。配套脚本 `scripts/bootstrap_pipeline.py`
（输入 plan.json，见 plan-schema.md），模板 `assets/setup.sh.tmpl`。

## 项目工作区结构

一个公共机构 = 一个项目 = 一个工作区 = 一份报告：

```
~/projects/energy-audit/<slug>/
├── plan.json                      ← 项目输入（机构名/config/审计年度/角色映射，见 plan-schema.md）
├── config.json                    ← 项目配置（复制进 workspace）
├── data.json                      ← Step1 采集产出（project_data.py::save_project 落盘）
├── validation.json                ← Step2 验证产出（V1 DATA_CHECK）
├── indicator_review.json          ← V2 指标复核产出
├── indicators.json                ← Step3 指标计算产出
├── chapter5.md                    ← Step3 第5章 Markdown
├── charts/                        ← Step3 图表 PNG
├── report_review.json             ← V3 报告审查产出
└── output/
    └── <单位全称>能源审计报告.docx  ← Step4 最终报告
```

**slug 规则**：项目名（机构全称）前若干字符，URL 友好。task body 中所有路径必须
**绝对路径**（如 `C:/Users/<user>/projects/energy-audit/<slug>/data.json`），
禁止用 shell 变量/相对路径——kanban worker 看不到主会话的环境变量（历史事故）。

## setup.sh 流程（assets/setup.sh.tmpl）

1. **环境检查** — hermes CLI 存在、5 个 profile 存在（4 执行 + editor Director）、kanban board 已初始化
2. **创建工作区** — 按上表建目录树
3. **复制配置** — config.json 复制进 workspace
4. **创建 Kanban 任务图** — 每项目 6 步串行任务 + 1 个 Director 汇总（见 workflow.md）
5. **完成提示** — 监控命令/报告收集路径

## Profile 配置规则

每个 profile 的 `~/.hermes/profiles/<name>/config.yaml` 需要且只需要：

| 键 | EA 要求 | 说明 |
|----|---------|------|
| `toolsets` | `[hermes-cli, energy_audit]`（hermes-cli 提供 terminal/file/web 默认工具） | **必须有 energy_audit**（9 工具：PG 查询/RAG/仿写），否则 worker 看不到 pg_query 等工具会断链自建 psycopg2 脚本（2026-08 事故）；工具详解见 tools-reference.md |
| `terminal.cwd` | 指向 dechnicAuditor-agent repo（`D:\data\pyProject\dc_agent\dechnicAuditor-agent`） | 供 `from tools.energy_audit import ...` 导入 |
| `skills` | **不配置 always_load**，技能由 sync_ea_skills.py 按角色矩阵发布到 `<profile>/skills/energy-audit/` | 角色技能矩阵权威：references/role-definitions.md |

**禁止修改**：`approvals.mode`（安全设置）。`terminal.cwd` 与视频流水线规则不同
（视频版不碰 cwd，由 dispatcher `--workspace dir:` 覆盖；EA 版 worker 必须能导入
repo 工具链，故 cwd 固定指 repo）。

配置用 **PyYAML patch**（非字符串替换），改完回读校验。

## 技能发布前置（必做，2026-09 起）

发任务前必须先跑发布器，否则 worker 拿旧技能/无技能：

```bash
cd D:\data\pyProject\dc_agent\dechnicAuditor-agent
python scripts/sync_ea_skills.py && python scripts/sync_ea_skills.py --verify
# [校验] profile 侧不一致文件: 0  → 才能发 kanban
```

## SOUL.md per profile

- SOUL.md = 权威身份（角色定位/职责/输入输出/行为边界），**不内嵌数值与规则**——
  知识引用 `energy-audit-core/references/`（防失同步，见 core 的 soul-purity-principle.md）。
- editor（Director）的 SOUL 应含反代劳铁律："不亲自执行任务；对每个具体任务创建
  kanban 任务并指派；分解、路由、评论、批准——这就是全部工作。"
  （kanban 生命周期指引由框架自动注入每个 worker 的 system prompt，无需在 SOUL 重复。）
- 其他 profile 的 SOUL 简短：你是谁、读什么、产什么、用哪些技能工具、写到哪里。

## 初始 kanban 任务

```bash
hermes kanban create "<机构全称> 能源审计 — 数据采集" \
    --assignee datacollection \
    --workspace dir:"$HOME/projects/energy-audit/<slug>" \
    --tenant <slug> \
    --priority 2 \
    --max-runtime 30m \
    --body "使用 ea-datacollection 技能采集 PG 数据。
必须使用绝对路径：
  项目数据目录: C:/Users/<user>/projects/energy-audit/<slug>/
  输入 config.json: C:/Users/<user>/projects/energy-audit/<slug>/config.json
  产出 data.json 后 kanban_complete(metadata={'data_path': '<绝对路径>'})"
```

- `--workspace dir:<绝对路径>` **关键**：所有子任务共享该工作区；漏配或误用 worktree
  会隔离 profile、阻断产物共享。
- **tenant**：每个项目一个 tenant，任务板隔离，防止多项目交叉污染。

## 环境前置检查

```bash
# 1) PG 连通（worker 会直连取数）
python -c "import psycopg2; psycopg2.connect(host='10.10.1.165', dbname='dc_energy_audit2', user='postgres', password='<DB密码>', connect_timeout=5); print('PG OK')"
# 2) repo venv 依赖
cd D:\data\pyProject\dc_agent\dechnicAuditor-agent && .venv/Scripts/python.exe -c "import tools.energy_audit.pg_collector; print('tools OK')"
# 3) 技能已发布（见上）
# 4) file base_url（建筑照片下载，缺失时自动回退 DB 主机）
python -c "from tools.energy_audit.db_config import get_file_base_url; print(get_file_base_url())"
```

任一失败则中止，不发出会中途失败的 kanban。

## Critical rules

1. **workspace_kind="dir" + workspace_path="<绝对路径>"** 写进每个 kanban_create。
2. **tenant 每个任务**（`--tenant <slug>`）。
3. **幂等**：setup 类任务用 idempotency_key 或先检查存在性，防止重跑重复创建。
4. **max_runtime_seconds 按步设置**：采集 1800s / 验证 900s / 计算 1200s / 报告 1800s（默认）。
5. **心跳**：>5min 的任务周期性 `kanban_heartbeat`（progress 字段写阶段名+完成项数）。
6. **config.json 在任务发出前复制进 workspace**，不要让采集任务自行寻找。
7. **DB 写操作只在数据修复环节做**（带备份），kanban worker 默认只读 DB；
   worker 遇到 DB 数据错误 → V1 记 P0 block，不自行改库（改库由主会话执行并备份）。
