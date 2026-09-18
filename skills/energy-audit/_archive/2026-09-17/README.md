# 归档说明（2026-09-17）

本目录存放**已从技能包移出**的历史文档。移动原因分三类：
① 内容已被现行权威文件取代；② 描述的是已退役链路的实现细节；③ 自标"已降级/历史"却仍被当作权威引用。

**规则**：归档 ≠ 删除。文件内容原样保留，git 继续跟踪；`sync_ea_skills.py` 按 `_` 前缀跳过本目录，因此不会发布到任何 profile。
如需引用归档内容，请在正文里写明"历史参考（2026-09-17 归档）"，不要当作现行权威。

## 已归档文件与去向

| 归档文件 | 原因 | 内容去向 / 替代权威 |
|---|---|---|
| `energy-audit-core/references/public-institution-report-structure.md` | 旧通用 8 章骨架，与 R7 正式版口径系统性不符（6.1~6.5、7.1~7.4 结构全不同），却被 4 处当权威引用 | 逐章指南 `ea-authoring/references/chapter*-guide.md` + `energy-audit-report/references/city-template-guide.md` |
| `energy-audit-core/references/chapter-writing-specs.md` | 第2/5/6 章旧写作规范（6.1 用电/6.2 用水/6.3 供暖、5.2 要求插占位提示段、表号"表6.1-N"） | 同上；月度数据"三处同步"说明仍有效，已并入 `ea-authoring/references/data-model-reference.md` 的字段规则 |
| `energy-audit-core/references/agent-profile-architecture.md` | v2.0 架构记录（"只保留 2 个技能"）与现行 11 技能 + kanban 架构矛盾 | 现行角色映射见 `kanban-energy-audit-orchestrator/references/role-definitions.md`；`config.yaml` 要点与启动脚本模板待并入 `deployment-prerequisites.md` |
| `energy-audit-core/references/pipeline-architecture.md` | 第 3 份流程描述（旧 `run_pipeline.py` 已移除），与 routing SKILL、kanban SKILL 重叠 | `energy-audit-routing/SKILL.md`（直跑轨）+ kanban 技能（批量轨） |
| `energy-audit-core/references/tools-api.md` | 代码层 API 索引，描述已退役的 `report_generator` 入口与已删除模块 | 工具链入口速查待重写为 10 行清单；现行链路见 `ea-datacollection` / `ea-calculation` / `energy-audit-report` |
| `energy-audit-core/references/patch-replace-all-danger.md` | 事故场景属 `report_generator` 时代，教训通用 | 教训已抽 3 条并入 `ea-authoring/references/word-generation-tips.md` |
| `energy-audit-report/references/word-finishing.md` | 旧 report_generator/assemble 链路的收尾工艺 | `energy-audit-report/references/script-assembly-chain.md`（当前主链）+ `energy-audit-imitate/references/assemble-format-notes.md` |
| `ea-calculation/references/chapter5-52-spec.md` | 自标"已废弃（v3.4）" | `chapter5-52-final-spec.md` |
| `ea-calculation/references/chapter5-52-writing-spec.md` | 自标"已废弃" | `chapter5-52-writing-lessons.md` |
| `ea-calculation/references/chapter5-52-reference-style.md` | 自标"已废弃"（图号/费用节为旧口径） | `chapter5-52-final-spec.md` + `chapter5-53-templates.md` |
| `ea-authoring/references/chapter6-indoor-env.md` | 自标"已废弃"——室内环境检测归附录4，不再生成 6.5 节 | `energy-audit-report/references/assembly-workflow.md`（附录4） |
| `soul-before/<role>.md`（6 份） | 改造前的旧 SOUL（caliber 含错系数、author 含"精通 Python-docx"等） | 现行 SOUL = `skills/energy-audit/_soul/<role>.md`（由 sync 发布到 `profiles/<role>/SOUL.md`） |

## 未归档但已处置的项

- `auxiliary-vision-config.md`：环境配置（Qwen-VL 辅助视觉），与报告质量无关但采集/写章/视觉核验都需要 → **2026-09-17 从 `ea-authoring/references/` 移到 `energy-audit-core/references/`**（并修正 `~/.hermes` → `%LOCALAPPDATA%\hermes`）。
- `energy-audit-core/references/hermes-operations.md`：保留，但"多 profile 运维"一节仍是 default/coder/xiaocheng 旧部署，待通用化（批 4）。
