# 角色定义

能源审计 Kanban 编排器使用 4 个固定的 Profile 角色。每个角色是一个独立的 Hermes Profile，有专属的 SOUL.md、技能和工具集。

## 角色总览

```
数据采集          验证分析          指标计算          报告生成
DataCollection → DataVA      → Caliber        → author
(采集所有数据)    (完整性+异常)    (5项指标+5章)    (全8章报告)
```

## 1. 数据采集 Agent (DataCollection)

| 项 | 值 |
|----|-----|
| Profile 名 | `datacollection` |
| 技能 | `ea-datacollection` + `energy-audit-core` + `energy-audit-pg-data` |
| 工具集 | hermes-cli + energy_audit（9 工具：PG 查询/RAG/仿写，详见 references/tools-reference.md） |
| 输入 | config.json, PG 数据库 |
| 输出 | `data.json` (项目数据) |
| SOUL | "严谨的数据专员，只采集不编造，每字段标注来源" |

**任务 Body 要素:**
- config.json 路径
- 输出目录
- 缺失字段处理方式（标注【待补充】vs 跳过）

## 2. 数据验证 Agent (DataVA)

| 项 | 值 |
|----|-----|
| Profile 名 | `datava` |
| 技能 | `ea-validation` + `energy-audit-core` + `energy-audit-pg-data` |
| 工具集 | hermes-cli + energy_audit（9 工具：PG 查询/RAG/仿写，详见 references/tools-reference.md） |
| 输入 | `data.json` (上游产出) |
| 输出 | `validation.json` (验证结果+KG诊断) |
| SOUL | "严谨客观的数据质检员，不修改原始数据" |

**任务 Body 要素:**
- data.json 路径
- 异常阈值（默认同比±30%, 月离群>2σ）
- 是否需要 KG 因果诊断

## 3. 指标计算 Agent (Caliber)

| 项 | 值 |
|----|-----|
| Profile 名 | `caliber` |
| 技能 | `ea-calculation` + `energy-audit-core` + `energy-audit-report` |
| 工具集 | hermes-cli + energy_audit（9 工具：PG 查询/RAG/仿写，详见 references/tools-reference.md） |
| 输入 | `validation.json` (上游产出) |
| 输出 | `indicators.json`, `chapter5.md`, `charts/` |
| SOUL | "严谨精确的能耗分析师，三级兜底+定额对标" |

**任务 Body 要素:**
- validation.json 路径
- 机构类型（决定定额标准 DB37/T 2673 vs 2672）
- 非供暖能耗折标系数（默认等效电 0.31）
- 指标项（默认 4 项全算）

## 4. 报告生成 Agent -author(小德)

| 项 | 值 |
|----|-----|
| Profile 名 | `author` |
| 技能 | `ea-authoring` + `energy-audit-core` + `energy-audit-report`（含实例库与Word工艺，已合并原 energy-audit-reports） + `energy-audit-imitate` |
| 工具集 | hermes-cli + energy_audit（9 工具：PG 查询/RAG/仿写，详见 references/tools-reference.md） |
| 输入 | `indicators.json`, `chapter5.md` (上游产出) |
| 输出 | `能源审计报告.docx` (完整 8 章) |
| SOUL | "用自然语言写出专业的能源审计报告" |

**任务 Body 要素:**
- 上游产出路径
- 格式规范（H1宋体15pt/H2宋体14pt/正文12pt）
- 省级规章是否需 web_search 验证
- 照片路径（如有）

## 5. 汇总审查 Agent (Director = editor)

| 项 | 值 |
|----|-----|
| Profile 名 | `editor` |
| 技能 | `kanban-energy-audit-orchestrator` + `energy-audit-core` + `energy-audit-report-qa` |
| 工具集 | kanban, hermes-cli, terminal, file, vision（不装 energy_audit，跨项目审查读各项目产出文件） |
| 输入 | 全部项目的 report_review.json + 报告 |
| 输出 | review_report.md + all_reports.json（Director 汇总工作区） |
| SOUL | "专职汇总审查员：只审查不写作，跨项目指标对比，P0 阻塞裁决" |

> 2026-09-03 复位：Director 汇总任务 assignee = profiles["director"]（推荐 editor），
> 与 author（写作）职责分离，保证审查独立性。director 缺省回退 reporter。

## 关键约束

1. **严格串行。** 下游依赖上游产出，不可跳跃。
0. **技能同步（2026-09-02 起）。** 各角色技能由 `scripts/sync_ea_skills.py` 从 repo `skills/energy-audit/` 单向发布；
   角色安装矩阵以本文件"技能"列为准；定额/系数/版本归一权威源为 `energy-audit-core/references/`，SOUL.md 不内嵌数值。
2. **数据交付。** 通过 kanban_complete 的 metadata 传递文件路径。
3. **共享 workspace。** 所有 Profile 使用同一 `dir:` workspace。
4. **Tenant 隔离。** 所有 kanban 调用使用同一 tenant。
