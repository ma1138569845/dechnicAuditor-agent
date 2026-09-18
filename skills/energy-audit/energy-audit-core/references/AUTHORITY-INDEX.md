# AUTHORITY-INDEX — 主题 → 唯一权威（2026-09-17 建）

**用法**：动笔或改脚本前先在这里查"这个主题的权威文件是哪个"；只能读那一个文件，其他地方出现同样内容一律视为副本。
**规则**：

1. 每个主题**只有一个**权威文件；发现第二处副本 → 改成引用或归档（本索引的"禁止复述在"列就是副本黑名单）。
2. 改权威文件后必须跑验收：`python scripts/sync_ea_skills.py --verify`（退出码 0 = 已对齐）。
3. 新增主题必须登记到本表；SOUL 与 SKILL 都**不内嵌具体数值**。

## 一、口径类（最容易出错，历史上都出过事故）

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 定额三档值（机构类型 × 机构等级 × 气候区） | `energy-audit-core/references/standards-values.md` | caliber、datava V2、author（1.6 / 5.3 / 8.1） | 任何 SKILL / SOUL / 章节指南（曾因取错气候区写成"来源：DB"不实） |
| 折标系数与综合能耗口径（水不折算） | `energy-audit-core/references/coefficient-caliber.md` | caliber、datava V2、author 第5章 | 同上（旧 caliber SOUL 曾写"水 0.2571 / 气 1.33 / 电 0.1229"，已删除） |
| 版本归一（草稿优先，禁多数投票） | `energy-audit-core/references/version-normalization.md` | datacollection、datava、energy-audit-pg-data | pg-data SKILL 的"版本机制"复述段 |
| 5 项指标定义与兜底链 | `ea-calculation/SKILL.md` | caliber、datava V2、author 第8章 | 章节指南、SOUL（曾出现"4 项指标"） |
| 兜底层数（系数四级 / 定额三级） | `ea-calculation/SKILL.md` | 同上 | `three-layer-fallback.md`（原理保留，层数以 SKILL 为准） |
| 指标/取水口径按机构类型自适应 | `energy-audit-core/references/standards-values.md` | caliber、author 1.2/5.3.4 | 章节指南 |

## 二、写作类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 第1/2/3/4/6/7/8 章写作规则 | `ea-authoring/references/chapter*-guide.md`（第6章另见 `chapter6-sub-system-spec.md`） | author、datava V3 | 旧 8 章骨架（已归档）、`chapter-writing-specs.md`（已归档） |
| 第5章结构 / 表号图号 / 写作细节 | `ea-calculation/references/chapter5-52-final-spec.md`（结构）+ `chapter5-53-templates.md`（模板）+ `chapter5-52-writing-lessons.md`（细节） | caliber、author 批2 | 3 个已废弃 5.2 文件（已归档） |
| 市州 0-11 章模板骨架 | `energy-audit-report/references/city-template-guide.md` | author、caliber | — |
| 报告实例库（法院/医院/学校） | `energy-audit-report/references/examples/*.md` | author、energy-audit-style | 章节指南里不复述实例原文 |
| 写作论证链 / 句式 / 防抄 | `energy-audit-style/references/argument-logic.md`、`writing-style.md`、`anti-copy-gate.md` | author、editor（**注意：当前未接入写作主流程，待决**） | — |

## 三、成品与校验类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 格式规范（字体/字号/行距/表格/封面/目录/图片/水印） | `energy-audit-core/references/report-format-spec.md` + `tools/energy_audit/format_spec.py` | 全角色、datava V3、装配脚本 | core SKILL / ea-authoring SKILL / author SOUL 的字体表（已改指针） |
| 装配主链（构建 → 收尾 → 断言） | `energy-audit-report/references/script-assembly-chain.md` | author、editor | 旧 `word-finishing.md`（已归档） |
| 仿写链 spec.json 语法与图表标记 | `energy-audit-imitate/SKILL.md` + `references/assemble-format-notes.md`、`chapter-outlines.md` | author（仿写模式） | — |
| 验收口径（四类合规 + 高频错误 + 根因链） | `energy-audit-report-qa/SKILL.md`（+ `references/audit-info-tables-fix.md`、`collector-chain-fixes.md`） | editor、datava V3、default 交付前 | editor SOUL 的 A~O 自查清单（已删除） |
| 三张信息表的表结构与来源链路 | `energy-audit-core/references/audit-info-tables.md`（结构）+ `energy-audit-report-qa/references/audit-info-tables-fix.md`（来源与修复） | author、datacollection、V1/V3 | — |

## 四、数据与运维类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 数据契约与字段取值路径 | `ea-authoring/references/data-model-reference.md` | author、caliber、datava、datacollection | SOUL 里的字段清单（已改指针） |
| PG 表结构 / 能源代码 / 图片链路 / 取数陷阱 | `energy-audit-pg-data/SKILL.md` | datacollection、datava | — |
| 流程与调度（分诊 / 直跑 / 批量 / 角色矩阵） | `energy-audit-routing/SKILL.md`（分诊与直跑）+ `kanban-energy-audit-orchestrator/SKILL.md` 与 `references/{workflow.md, role-definitions.md, tools-reference.md}`（批量与角色） | default、editor、全角色 | 旧 `pipeline-architecture.md`（已归档）；**待办：合并为单一 workflow.md** |
| SOUL 编写与发布 | `energy-audit-core/references/soul-purity-principle.md` + `skills/energy-audit/_soul/*.md` + `scripts/sync_ea_skills.py` | 全角色 | SOUL 不内嵌数值与框架生命周期 |
| 部署前提与自检 | `energy-audit-core/references/deployment-prerequisites.md` | 全角色（新机/换机） | — |
| 辅助视觉模型（图片识别：铭牌/仪表/图纸） | `energy-audit-core/references/auxiliary-vision-config.md` | author、datacollection、视觉核验环节 | 别的技能不复述 provider/model/端点 |
| 数据导出与整库导出 | `energy-audit-pg-data/references/data-export.md` | datacollection | — |
