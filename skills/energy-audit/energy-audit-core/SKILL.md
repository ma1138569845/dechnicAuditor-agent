---
name: energy-audit-core
description: "能源审计共享核心知识：报告族路由、全流程、8章结构、格式规范、三级兜底与地区定额对标."
version: 5.1.0
author: 马天远
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [energy-audit, core, standards, db37]
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

### 异常确认机制（datava 验证阶段）

datava 验证发现异常后写入 analysis_result.json（`anomalies[].confirmed` 初始 `null`），
需人工确认（`confirmed=true` + `reason`）后指标复核与报告装配才继续——强制人工审核异常项，防止脏数据进报告。
批量流水线场景可在用户确认后由 editor 批量确认再继续下游。

## 报告族选择（先于章节与标准）

报告族由 `data.json → base.unit_type + base.province` 决定，禁止按医院/学校/办公等建筑功能猜；`indicators.json`、蓝本或文件名都不能反向决定报告族：

| 报告族 | 当前状态 | 标准与写作入口 |
|---|---|---|
| 山东公共机构 | 在用（兼容主链） | `standards-values.md`、公共机构 `chapter-guides-1-4.md` / `chapter-guides-6-8.md` |
| 山东公共建筑 | 已接入（DB37 二档） | `standards/shandong/public_building/`、`families/public-building/` |
| 浙江公共建筑 | 已接入（DB33/T 736/760） | `standards/zhejiang/`、`families/public-building/` |
| 浙江公共机构 | 已接入（DB33/T 736/737/738） | `standards/zhejiang/public_institution/`、公共机构章节指南 |

唯一路由代码：`tools/energy_audit/report_family.py::resolve_report_family()`。
公共建筑当前只接入山东、浙江；其他省份必须停止并说明，不得静默套用 DB33/T 或 DB37/T。
山东公共建筑只有约束值、先进值二档；浙江公共机构使用约束值、基准值、引导值三档，两者不得混写。

## 公共机构能源审计报告章节结构

1. 能源审计执行概要（1.1-1.6）
2. 公共机构概况（2.1-2.3）
3. 能源资源管理状况（3.1-3.3）
4. 能源资源计量及统计状况（**4.1-4.3**；原「4.3 统计情况」已废止并入 4.3 成效及问题）
5. 能源资源消费/消耗指标分析（5.1-5.4）
6. 主要能源资源利用系统分析（6.1-6.3）
7. 节能效果与节能潜力分析（7.1-7.2）
8. 审计结论

## 格式规范

格式权威单点：`references/report-format-spec.md`（全文规范）+ `tools/energy_audit/format_spec.py`（代码常量）。
装配脚本链、仿写链、office_editor 备用路径**共用同一份**，本文件不再复述字体字号表（曾因四处副本导致口径漂移）。

## 关键原则

### 术语表与阶段表

**唯一权威 = `references/WORKFLOW.md`**（阶段表 / 门禁 / 回退 / 术语表 / 批量轨差异）。本文件不复述，避免多处副本。

- 1.6 省级规章需 web_search 验证，不可字符串替换
- **批量生成：`kanban-energy-audit-orchestrator` 技能**。利用 Hermes Kanban 实现并行调度。
  一个公共机构 = 一个项目 = 一份报告。每项目 8 步串行（采集→V1验证→计算→V2复核→报告卡1基础章→报告卡2数据章→报告卡3收尾章→V3审查），不同项目完全并行。
  适合 1~100+ 栋的规模。详见 `kanban-energy-audit-orchestrator/SKILL.md`。
- 第5章 5.2 按用能类型动态分节、第6章 6.1 分系统详述、第7章问题从实际数据推断——具体规则见各专属技能 references。
- 报告章节细节与编写规范按报告族取：山东公共机构、浙江公共机构见 `ea-authoring/references/chapter-guides-1-4.md`、`chapter-guides-6-8.md`；山东/浙江公共建筑见 `ea-authoring/references/families/public-building/`。"主题 → 唯一权威"映射见 `references/AUTHORITY-INDEX.md`。

## 参考文件索引

`references/` 下的核心文档：

| 文件 | 用途 |
|------|------|
| `AUTHORITY-INDEX.md` | ★总索引："主题 → 唯一权威文件"映射（**先查这里，再查具体文件**） |
| `WORKFLOW.md` | ★工作流唯一状态机（阶段表/门禁/回退/术语表/批量轨差异；2026-09-20 建） |
| `energy-audit-core/references/standards-values.md（权威单点）` | ★权威·定额标准矩阵（DB37/T 2672-2019 表1-5 党政机关 + DB37/T 2673-2019 医院 + DB37/T 4452-2021 水）。任何定额值只以此文件为准 |
| `energy-audit-core/references/coefficient-caliber.md（权威单点）` | ★权威·折标系数口径（电0.31/热34.12kgce每GJ/气1.2143/油1.4714/水不折算） |
| `version-normalization.md` | ★权威·版本归一规则（草稿优先=最新数据，禁多数投票） |
| `report-format-spec.md` | 报告格式总规范（唯一权威全文） |
| `conventions.md` | ★通用约定（2026-09-18 五合一）：项目粒度 + 兜底原则 + config 结构 + 审计三张表结构 + ISO 日期转换 |
| `deployment-ops.md` | ★部署与运维（2026-09-18 三合一）：新机自检清单 + Hermes 运维（含"SOUL 改动需重启 gateway"）+ 视觉模型配置（证书默认 DeepSeek V4.1-Flash，Qwen-VL 备用） |
| `soul-purity-principle.md` | SOUL.md 编写原则（`skills/energy-audit/_soul/` 的唯一编写依据） |
| `lessons-learned.md` | ★跨项目经验库（教训索引：现象→铁律→详见，按数据源/标准/报告/装配/协作五类，2026-09-18 建） |
| `knowledge-base-maintenance.md` | ★知识库维护（**写侧**）：谁在何时喂料 / 边界 / 验收四条硬指标 / 删除禁令（knowledger 专属；editor 的巡检也引它；原 S16a「交付件入库」2026-10-10 废止） |
| `standards-sources/` | 定额**原文摘录件**（包内机读件：`DB37T2671-2019-全文抽取.txt`、`DB37-5026-2022-气候区划表3.0.1.md`）。**原始 PDF 已移出包**（与知识库重复件，2026-09-22 瘦身），位置见 `standards-values.md` 内的指针 |
| `standards/shandong/public_building/` | 山东公共建筑 DB37/T 5076/5078/5079-2024 包；人读 `quota-values.md`，代码只读 `quota-values.json` |
| `standards/zhejiang/public_institution/` | 浙江公共机构 DB33/T 736/737/738-2021 包；736 数值共享 `standards/zhejiang/quota-values.json` |
| `_archive/2026-09-17/`、`_archive/2026-09-18/` | 历史文档与合并前原件归档（仅供追溯，勿引用） |

**本技能 `scripts/`（随技能发布，knowledger/author/editor 直接用）**：

| 脚本 | 用途 |
|---|---|
| `ingest_kb_files.py` | 投递区 → 向量化/实体/wiki → 归档 + 台账（`--dry-run` / `--move` / `--vector-only`） |
| `sync_report_library.py` | 成稿库↔向量库两张清单门禁（`--check`）；**自产件不入库**（`--add` 按 `EAWatermark`/`python-docx` 指纹拒绝，`--allow-self` 才放行）——原 S16a「交付件入库」2026-10-10 废止 |
| `verify_knowledge_assets.py` | 知识层资产治理检查（目录规约/元数据/副本/点数对账/死资产/切片体检/归档完备；`--fix-payload`、`--write-log`） |
