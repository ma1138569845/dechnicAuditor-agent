---
name: energy-audit-core
description: 能源审计共享核心知识——全流程概览、报告8章结构、格式规范、三级兜底、DB37对标标准。所有能源审计 Agent 共享的基础知识，各 Agent 专属深度知识见 ea-datacollection / ea-validation / ea-calculation / ea-authoring。
version: 5.0.1
author: 马天远
---

# 能源审计共享核心知识

本技能提供能源审计全流程所有 Agent 共享的领域知识（格式规范、章节结构、兜底原则、对标标准）。
各 Agent 的专属深度知识在对应专属技能中：

| 专属技能 | 所属 Agent | 内容 |
|---------|-----------|------|
| `ea-datacollection` | datacollection | PG 采集、数据流、DB schema、图片采集 |
| `ea-validation` | datava | 异常检测、KG 因果诊断、完整性校验 |
| `ea-calculation` | caliber | 指标计算（非供暖/电耗/人均综合/取水/供暖能耗 5 项）、第5章、能流图 |
| `ea-authoring` | author (小德) | 第1~8章写作指南、docx 排版 |

调用：
- 单项目/批量: `kanban-energy-audit-orchestrator` 技能（editor Agent 内）

### ⚠️ Step 4 异常确认阻塞（必读）

首次运行时 Step 4 检测到异常后会**阻塞**并提示：
> "共发现 N 项异常，其中 N 项待确认。请编辑 analysis_result.json..."

**pipeline 直接 return None，不生成报告。** 原因是 `analysis.anomalies[].confirmed` 初始为 `null`，`pending_count > 0` 时退出。

**自动化跳过方法**（用户偏好全自动时使用）：

1. 编辑项目的 `analysis_result.json`（项目数据目录为 `~/projects/energy-audit/<单位名>/`，由 `project_data.py::save_project` 写入；`analysis_result.json` 由 `data_analysis.py::save_analysis_result` 落盘——当前代码未见生产调用方，实际路径以落盘位置为准）
2. 将每项的 `confirmed` 设为 `true`，`is_data_error` 设为 `false`，`reason` 填写说明
3. 重新触发异常分析（`run_pipeline.py` 已移除；入口为 `tools/energy_audit/data_analysis.py::analyze_energy_data` / `analyze_with_diagnosis`），此时 `pending_count == 0`，流程继续

此设计意在强制人工审核——用户同意后直接批量确认即可。

##  公共机构能源审计报告章节结构

1. 能源审计执行概要（1.1-1.6）
2. 公共机构基本情况（2.1-2.3）
3. 能源资源管理状况（3.1-3.3）
4. 能源资源计量及统计状况（4.1-4.4）
5. 能源资源消费/消耗指标分析（5.1-5.4）
6. 主要能源资源利用系统分析（6.1-6.3）
7. 节能效果与节能潜力分析（7.1-7.2）
8. 审计结论

## 格式规范

| 元素 | 字体 | 字号 | 加粗 |
|------|------|------|------|
| H1一级标题 | 宋体 | 15pt | 是 |
| H2二级标题 | 宋体 | 14pt | 是 |
| H3三级标题 | 宋体 | 12pt | 是 |
| 正文 | 宋体+TNR | 12pt | 否 |
| 表格内容 | 宋体 | 12pt | 否 |

## 关键原则

- 1.6 省级规章需 web_search 验证，不可字符串替换
- **批量生成：`kanban-energy-audit-orchestrator` 技能**。利用 Hermes Kanban 实现并行调度。
  一个公共机构 = 一个项目 = 一份报告。每项目 4 步串行（采集→验证→计算→报告），不同项目完全并行。
  适合 1~100+ 栋的规模。详见 `kanban-energy-audit-orchestrator/SKILL.md`。
- 第5章 5.2 按用能类型动态分节、第6章 6.1 分系统详述、第7章问题从实际数据推断——具体规则见各专属技能 references。
- 报告章节细节与编写规范见 `references/` 目录（report-format-spec、chapter-writing-specs、public-institution-report-structure 等）。

## 参考文件索引

`references/` 下的核心文档：

| 文件 | 用途 |
|------|------|
| `energy-audit-core/references/standards-values.md（权威单点）` | ★权威·定额标准矩阵（DB37/T 2672-2019 表1-5 党政机关 + DB37/T 2673-2019 医院 + DB37/T 4452-2021 水）。任何定额值只以此文件为准 |
| `energy-audit-core/references/coefficient-caliber.md（权威单点）` | ★权威·折标系数口径（电0.31/热34.12kgce每GJ/气1.2143/油1.4714/水不折算） |
| `version-normalization.md` | ★权威·版本归一规则（草稿优先=最新数据，禁多数投票） |
| `report-format-spec.md` | 报告格式总规范 |
| `public-institution-report-structure.md` | 公共机构报告 8 章结构 |
| `chapter-writing-specs.md` | 章节写作通用规范 |
| `audit-info-tables.md` | 审计信息表结构（ts_register_dept 等数据源链路） |
| `config-schema.md` | config JSON 结构（采集/计算/报告均依赖） |
| `three-layer-fallback.md` | 三级兜底原则 |
| `agent-profile-architecture.md` | Profile-Skill 架构文档 |
| `soul-purity-principle.md` | SOUL.md 编写原则 |
| `hermes-operations.md` | Hermes 操作通用知识 |
| `complete-markdown-workflow.md` | Markdown 工作流 |
| `pipeline-architecture.md` | 流水线架构 |
| `agent-startup-workflow.md` | Agent 启动流程 |
| `project-granularity.md` | 项目粒度定义 |
| `iso-date-to-cn.md` | 日期转换工具 |
| `patch-replace-all-danger.md` | 编辑安全警示 |
