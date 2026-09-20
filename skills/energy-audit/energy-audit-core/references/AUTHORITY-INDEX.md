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
| 兜底层数（系数四级 / 定额三级） | `ea-calculation/SKILL.md` | 同上 | `conventions.md`《兜底原则》一节（原理保留，层数以 SKILL 为准） |
| 指标/取水口径按机构类型自适应 | `energy-audit-core/references/standards-values.md` | caliber、author 1.2/5.3.4 | 章节指南 |

## 二、写作类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 第1/2/3/4/6/7/8 章写作规则 | `ea-authoring/references/chapter*-guide.md`（第2章含建筑参数表定义、第6章含 6.1 分系统规范；2026-09-18 合并后以此为准） | author、datava V3 | 旧 8 章骨架、`chapter-writing-specs.md`、`chapter6-sub-system-spec.md`、`building-param-table-spec.md`（均已归档至 `_archive/`） |
| 第5章结构 / 表号图号 / 写作细节 | `ea-calculation/references/chapter5-spec.md`（结构+逻辑+细节）+ `chapter5-templates.md`（模板+生成逻辑）★2026-09-18 合并后以此二者为准 | caliber、author 批2 | 原 8 个 5.x 文件（已归档 `_archive/2026-09-18/`） |
| 市州 0-11 章模板骨架 | `energy-audit-report/references/city-template-guide.md` | author、caliber | — |
| 报告实例库 / 蓝本（法院/医院/学校） | `energy-audit-report/references/audit-examples.md`（2026-09-18 三合一） | author、energy-audit-style | 章节指南里不复述实例原文；蓝本只提供**形态**，变量必须来自本项目数据源 |
| 写作论证链 / 句式 / 防抄 | `energy-audit-style/references/rules.md`、`rules.md`、`rules.md` | author、editor（**注意：当前未接入写作主流程，待决**） | — |

## 三、成品与校验类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 格式规范（字体/字号/行距/表格/封面/目录/图片/水印） | `energy-audit-core/references/report-format-spec.md` + `tools/energy_audit/format_spec.py` | 全角色、datava V3、装配脚本 | core SKILL / ea-authoring SKILL / author SOUL 的字体表（已改指针） |
| 装配主链（构建 → 收尾 → 断言） | `energy-audit-report/references/script-assembly-chain.md` | author、editor | 旧 `word-finishing.md`（已归档） |
| 仿写链 spec.json 语法与图表标记 | `energy-audit-imitate/SKILL.md` + `references/assemble-format-notes.md`、`assemble-format-notes.md` | author（仿写模式） | — |
| 验收口径（四类合规 + 高频错误 + 根因链） | `energy-audit-report-qa/SKILL.md`（+ `references/fixes.md`、`fixes.md`） | editor、datava V3、default 交付前 | editor SOUL 的 A~O 自查清单（已删除） |
| 三张信息表的表结构与来源链路 | `energy-audit-core/references/conventions.md`《审计基本信息三张表的表结构》一节（结构）+ `energy-audit-report-qa/references/fixes.md`（来源与修复） | author、datacollection、V1/V3 | — |

## 四、数据与运维类

| 主题 | 唯一权威 | 谁引用它 | 禁止复述在 |
|---|---|---|---|
| 数据契约与字段取值路径 | `ea-authoring/references/data-model-reference.md` | author、caliber、datava、datacollection | SOUL 里的字段清单（已改指针） |
| PG 表结构 / 能源代码 / 图片链路 / 取数陷阱 | `energy-audit-pg-data/SKILL.md` | datacollection、datava | — |
| 流程与调度（分诊 / 直跑 / 批量 / 角色矩阵） | `energy-audit-routing/SKILL.md`（分诊与直跑）+ `kanban-energy-audit-orchestrator/SKILL.md` 与 `references/{workflow.md, role-definitions.md, tools-reference.md}`（批量与角色） | default、editor、全角色 | 旧 `pipeline-architecture.md`（已归档）；**待办：合并为单一 workflow.md** |
| SOUL 编写与发布 | `energy-audit-core/references/soul-purity-principle.md` + `skills/energy-audit/_soul/*.md` + `scripts/sync_ea_skills.py` | 全角色 | SOUL 不内嵌数值与框架生命周期 |
| 部署前提与自检 / Hermes 运维 | `energy-audit-core/references/deployment-ops.md`（2026-09-18 三合一） | 全角色（新机/换机） | — |
| 辅助视觉模型（图片识别：铭牌/仪表/图纸） | `energy-audit-core/references/deployment-ops.md`《辅助视觉模型配置》一节 | author、datacollection、视觉核验环节 | 别的技能不复述 provider/model/端点 |
| 数据导出与整库导出 | `energy-audit-pg-data/references/data-export.md` | datacollection | — |
| 跨项目经验（踩坑结论） | `energy-audit-core/references/lessons-learned.md`（索引式，2026-09-18 建） | 全角色（开工前扫一遍） | 细节仍以本表其它权威文件为准，本文件只做索引 |
| 变量一致性（该变的是否真变） | `ea-validation/scripts/verify_variables_provenance.py` + `energy-audit-style/references/rules.md`《变量一致性闸门》 | datava（V3 后）、author（交付前）、editor | 文字相同=正常（固定条款），只查变量；相似度查重降为参考信息 |
| 工作流 / 阶段 / 门禁 / 回退 / 术语 | `energy-audit-core/references/WORKFLOW.md`（唯一状态机，2026-09-20 建） | default、editor、全角色 | routing 只写分诊、kanban 只写调度实现，均不复述阶段表 |
| **参考与知识读取**（读哪层 / 目录 / 检索入口 / 降级链） | `energy-audit-core/references/WORKFLOW.md` **第六节**（2026-09-20 建） | 全角色；knowledger 亦以本节为准 | 各 SKILL/SOUL 只写"何时读哪层"，不复述路径与目录（`rag/standards`/`rag/report`/`rag/data`/`rag/wiki` 的语义只在第六节） |
| 知识层资产治理（目录规约 / 元数据 / 副本 / 点数对账 / 死资产） | `_changes/verify_knowledge_assets.py`（2026-09-20 建）+ `%LOCALAPPDATA%\hermes\rag\ingest_log.json` | editor、knowledger | — |
| **标准条文检索**（定额/规范条文原文，`kbs="standards"`） | `rag/rag_search.py: search_standards()` + `rag/config.py: kb_collection()/STANDARD_KB_IDS`（2026-09-20 P3-3 建）+ `tools/energy_audit_rag_tool.py` 的 `kbs` 参数 | author、knowledger、caliber（查依据） | 各 SKILL 只写"何时用 kbs=standards"，不复述库名/集合名/参数细节 | 
