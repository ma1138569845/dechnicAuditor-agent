---
name: kanban-energy-audit-orchestrator
description: 能源审计报告Kanban多Agent编排器——自动化大规模公共机构能源审计。
version: 1.0.0
author: 同方德诚（山东）科技股份公司
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [energy-audit, kanban, multi-agent, orchestration, batch-processing]
    related_skills:
      - ea-datacollection
      - ea-validation
      - ea-calculation
      - ea-authoring
      - energy-audit-core
---

# Kanban Energy Audit Orchestrator

将一批公共机构的能源审计报告编制工作——从数据采集、验证、指标计算到报告生成——封装在 Hermes Kanban 流水线中，由专门的 Agent Profile 分工执行。

此技能是**元编排器**，不执行任何采集/验证/计算/报告生成本身。它做五件事：

1. **范围探索** — 确认审计项目（公共机构列表、审计周期、机构类型）
2. **计划生成** — 产出 plan.json（每个项目的配置路径、Profiles映射、并行度）
3. **环境搭建** — 生成 setup.sh，创建工作区 + kanban 任务图
4. **监控执行** — 轮询 kanban 状态，检测卡住/超时/重复重试
5. **质量审查** — 报告生成后进行跨章交叉校验

实际的采集/验证/计算/报告工作由以下四个 Profile 完成（第 5 个 editor 专职 Director 汇总审查）：

| Profile | 职责 | 工具集 |
|---------|------|--------|
| `datacollection` | PG数据库 + config +Excel识别多源数据采集 | terminal, file |
| `datava` | 数据完整性检查 + KG因果诊断 | terminal, file |
| `caliber` | 5项指标计算 + 定额对标 + 图表 + 第5章 | terminal, file |
| `author` | 第1/2/3/4/6/7/8章 + 最终报告组装 | terminal, file |

## 何时使用

- **≥1个项目** — 任何需要自动化审计流程的场景
- **需要并行加速** — 多个项目时 kanban 自动并行调度
- **需要容错** — 任一步骤失败自动重试，不丢进度
- **需要进度可见** — kanban board 实时查看每个项目的当前步骤

## 何时不使用

- **数据严重不足** — 大量字段缺省，需先逐个补全
- **纯手动交互场景** — 不需要自动化流水线

---

## 工作流

```
DISCOVER  →  PLAN  →  SETUP  →  EXECUTE  →  MONITOR  →  REVIEW
```

### Step 1 — Discover（范围确认）

确认以下信息：

- **项目列表** — 公共机构名称、slug、config.json 路径
- **审计周期**（默认最近三年）
- **机构类型**（医疗/党政/教育/服务中心/场馆）
- **并行度**（同时跑几个项目，默认 5）

如果一个项目下有多栋建筑，config.json 中包含全部建筑数据，
流水线一次处理完整个项目，生成一份报告。

### Step 2 — Plan（生成 plan.json）

使用 `scripts/bootstrap_pipeline.py` 生成 `plan.json`。该脚本：

1. 校验所有 config.json 文件是否存在且格式正确
2. 校验 Profiles（datacollection/datava/caliber/author）是否存在
3. 确定并行度和调度参数
4. 输出 `plan.json`

**plan.json 结构**参见 [references/plan-schema.md](references/plan-schema.md)。

### Step 3 — Setup（生成并执行 setup.sh）

**完整引导与配置规则见 [references/kanban-setup.md](references/kanban-setup.md)**；
**energy_audit 工具集（9 工具）与各角色使用矩阵见 [references/tools-reference.md](references/tools-reference.md)**：
工作区目录树、Profile 配置规则（toolsets 含 energy_audit、cwd 指 repo）、
技能发布前置（sync_ea_skills.py）、初始任务创建模式、环境前置检查、Critical rules。

```
python scripts/bootstrap_pipeline.py plan.json --out setup.sh
bash setup.sh
```

`setup.sh` 执行：

1. 创建工作区 `~/projects/energy-audit/`
2. 为每个项目创建子目录 `<slug>/`
3. 复制对应 config.json
4. **创建 kanban 任务图**（每项目 6 个父子链接任务 + 1 汇总 Director，见 workflow.md）
5. 打印监控命令

### Step 4 — Execute（启动调度）

```bash
# 查看任务板
hermes kanban list

# 启动看板面板
hermes dashboard

# 或使用命令行实时监控
python scripts/monitor.py --tenant <slug>
```

Kanban dispatcher 自动：
- 最多同时运行 `max_concurrent_projects` 个项目
- 每个项目的 6 步**严格串行**（父子依赖自动控制）
- 不同项目之间**完全并行**
- 任务失败**自动重试**（最多 2 次）

### Step 5 — Monitor（监控）

定期检查：
- `hermes kanban list --status running` — 正在运行
- `hermes kanban list --status blocked` — 阻塞
- `python scripts/monitor.py --tenant <slug> --once` — 快照

标准干预：
1. 评论阻塞任务 → `hermes kanban comment <id> "反馈"`
2. 解除阻塞 → `hermes kanban unblock <id>`
3. 重跑失败 → `hermes kanban reclaim <id>`

### Step 6 — Review（质量审查）

全部项目完成后，对报告进行交叉校验：

1. 第4章能耗数据 vs 第5章指标数据一致性
2. 第7章建议措施数量是否合理（不过多重复）
3. 第8章审计结论是否覆盖所有核心指标
4. 格式：H1 宋体15pt / H2 宋体14pt / 正文12pt / 表格12pt居中

---

## 关键规则

1. **Profile 不动态创建。** 五个 Profile（datacollection/datava/caliber/author/editor）必须已存在；editor 专职 Director 汇总审查；技能由 repo 根 `scripts/sync_ea_skills.py` 按角色矩阵发布（发任务前必须跑，见 references/kanban-setup.md）。
2. **一个项目一个 workspace。** 每个项目有独立子目录，避免文件冲突。
3. **父子任务严格串行。** 采集→验证→计算→报告，不可跳跃。
4. **不同项目之间完全并行。** 互不依赖，dispatcher 自动调度。
5. **Director 任务负责汇总。** 所有项目完成后，director 汇总统计。
6. **数据文件接力。** 下游任务从上游任务的 metadata 获取输出文件路径。
7. **每个项目一个工作区。** 某个审计项目的所有 profiles 共享同一个 `dir:`
   工作区。任务通过共享文件系统和结构化的交接来传递产物。**每一次**
   `kanban_create` 调用都要传 `workspace_kind="dir"` +
   `workspace_path="<绝对项目路径>"`。
8. **尊重既有技能。** 当某个场景符合某个既有技能时，相应的渲染器应该在其
   任务上通过 `--skill <name>` 或在其 profile 里用 `always_load` 加载该技能。
   不要重新推导技能已经提供的东西。

---

## 文件映射

```
SKILL.md                                          ← 本文件
scripts/
  bootstrap_pipeline.py                           ← plan.json → setup.sh
  monitor.py                                      ← 监控轮询
assets/
  setup.sh.tmpl                                   ← setup.sh 模板
references/
  plan-schema.md                                  ← plan.json 结构定义
  role-definitions.md                             ← 5个Profile角色详述（4执行 + editor Director）
  workflow.md                                     ← 每步详细工作流
  monitoring.md                                   ← 监控与干预指南
  examples.md                                     ← 示例项目
```
