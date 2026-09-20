# 能源审计工作流（唯一状态机）— 2026-09-20 建

> **本文件是"下一步做什么"的唯一权威**：阶段定义、产物、门禁、失败回退一律以此为准。
> 其它文档只写自己角色的细节，不再复述阶段表：
> - 分诊决策（走哪条轨） → `energy-audit-routing/SKILL.md`
> - 批量调度实现（plan.json / setup.sh / 任务图 / Profile 矩阵） → `kanban-energy-audit-orchestrator/`
> - 各阶段怎么做 → 对应技能（见每行"执行者"列）

## 一、阶段表（单项目 / 直跑轨）

| # | 阶段 | 执行者 | 输入 | 命令 / 动作 | 产物 | 门禁 |
|---|---|---|---|---|---|---|
| S1 | 分诊 | default | 用户诉求 | 加载 `energy-audit-routing` | 轨道判定 | ≥2 项目 → 转 editor（批量轨） |
| S2 | 采集 | datacollection | PG / Excel / config | `tools/energy_audit/data_collection_cli.py <项目名>` | `data.json` + 采集报告 | 版本冲突必须告警；工具链 import 失败 → **停下报告断链** |
| S3 | V1 验证 | datava | `data.json` | `data_verification_agent.py <项目名> --mode DATA_CHECK` | `validation.json`、`diagnosis_chapter7_material.txt` | exit 1 缺输入→回问用户；exit 2 P0→停 |
| S4 | 计算 + 第5章 | caliber | `data.json`+`validation.json` | `caliber_agent.py <项目名>` | `indicators.json`、`chapter5.md`、`charts/*.png` | 缺数据标【待补充】，不编造 |
| S5 | 第5章就位 | caliber | `chapter5.md` | `prepare_chapter_md.py <项目名>` | `chapter_md/ch5_import.md` | exit 2（装配稿早于计算产物）→ 人工确认后 `--force` |
| S6 | V2 复核 | datava | `indicators.json` | `… --mode INDICATOR_REVIEW` | `indicator_review.json` | P0（如评价与数值不符）→ 停 |
| S7 | 写章 批1 | author | S2~S6 产物 + 蓝本 | 契约 → 蓝本 → 第1~4章写作 | `chapter_md/ch1~ch4.md` | 每章落盘；收工重跑契约脚本 |
| S8 | 写章 批2 | author | 同上 | 第5章装配（禁重算）+ 第6/7章 | `ch5_import.md`（已就位）、`ch6.md`、`ch7.md` | 同上 |
| S9 | 写章 批3 | author | 同上 | 第8章 + 附录 | `ch8.md`、`appendix.md` | 同上 |
| S10 | 装配 | author | `data.json`+`chapter_md/`+`report_images.json` | `build_energy_audit_docx.py --project-dir <项目>` | `output/_script_build/<单位>能源审计报告.docx` | 缺章仅告警（会出空章）；公式占位必须命中资产库 |
| S11 | 收尾 | author | 上一步 docx | `finalize_energy_audit_pdf.py --project-dir <项目>` | 同名 `.pdf`（刷目录+盖章） | Word COM 必须绝对路径；updateFields 自动补写 |
| S12 | 断言 | author | docx + pdf | `ea_docx_asserts.py <docx> --pdf <pdf>` | 断言结果 | **10 项硬检查全过，失败不得报"完成"** |
| S13 | V3 审查 | datava | 落盘的 docx | `… --mode REPORT_REVIEW --report <docx>` | `report_review.json` | P0 阻塞；直跑轨结论**必须完整展示给用户确认** |
| S14 | 变量一致性 | datava / author | 生成稿 + 蓝本 | `verify_variables_provenance.py <项目名> [--blueprint …]` | P0/P1 清单 | P0（蓝本变量泄漏）→ 必须改回本项目数据 |
| S15 | 交付 | author | 上一步产物 | 复制（不移动） | `output/交付件/<单位>能源审计报告.docx\|pdf` | 交付件为唯一对外出口 |
| S16 | 沉淀 | 全员 | 本次踩坑 | 写进对应权威文件 + `lessons-learned.md` 登记一行 | 经验索引 | 只做索引，不复制细节 |

## 二、写章三步（每批固定，S7~S9 共用）

```
① 跑并读接续契约：prepare_writing_context.py → chapter_md/_context.md
      （唯一口径 / 关键数字 / 已落盘章节 / 术语写法 / **本批蓝本**）
② 读本批蓝本（形态参照）：energy-audit-report/references/audit-examples.md 对应机构类型小节
      （只学形态：章节骨架 / 表格习惯 / 措辞粒度 / 固定表述）
③ 按本项目数据写 → 落盘 chapter_md/chN.md → 收工重跑①刷新"已落盘章节"
```

- **批间压缩上下文**：交互会话用 `/compact`；非交互模式（`hermes chat -q/-Q`、kanban worker）改为**每批一个独立会话/任务**，批边界即任务边界。
- 数值只从 `data.json` / `indicators.json` / `chapter5.md` 读，**禁从前序章节文本或记忆提取**。

## 三、门禁汇总（统一口径）

| 门禁 | 判据 | 不通过时 |
|---|---|---|
| 退出码（V1/V2/V3） | 0 放行 / 1 输入缺失 / 2 存在 P0 | 1→回问用户；2→停并裁决 |
| 断言器 | docx+PDF 10 项硬检查 | 定点修复后重跑 |
| 合规占位登记 | `<项目>/missing_items.json` 登记的缺失 → P1 放行 | 未登记占位 → P0 |
| 取值锚点 | `verify_benchmark_sources.py`：指标→标准表号 | 缺锚点 → 第5章标【待核验】 |
| 变量一致性 | `verify_variables_provenance.py`：P0=蓝本变量泄漏 | P0 → 改回本项目数据 |
| 表题/图注 | 正文每张表上方一行 `表X.Y`；图注与 `report_images.json` 逐字一致 | V3 记 P2 / 缺表题计 P2 |

## 四、回退路径

| 触发 | 回到 | 动作 |
|---|---|---|
| V1 exit 1（缺输入） | S2 | 对话里问用户补线索 → 重跑 S2/S3 |
| V1/V2 P0 | S2 或 S4 | 修数据后重跑；或升级转 editor |
| 装配缺章 | S7~S9 | 补齐对应章 md 后重跑 S10 |
| 断言失败 | S10 或对应章 | 定点修复 → S11 → S12 |
| V3 P0 | 对应章 | 定点修复 → S10 → S12 → S13 |
| 变量一致性 P0 | 对应章 | 用本项目数据替换 → S10 → S12 → S14 |
| 非交互模式需要"批间压缩" | — | 拆成每批独立会话/任务重跑该批 |

## 五、批量轨差异（≥2 项目）

- 调度入口：`kanban-energy-audit-orchestrator`（editor = 编排入口 + Director 终审；运行时调度归 kanban dispatcher）。
- 每项目 8 步串行（采集→V1→计算→V2→报告3卡→V3），**项目间完全并行**；同一任务同一时间只有一个调度者。
- 角色 Profile 与技能矩阵：`kanban-energy-audit-orchestrator/references/role-definitions.md`。
- 与直跑轨**阶段定义完全相同**（本文件第一节），差别只在"谁调度、谁执行、上下文如何隔离"。

## 六、术语表（对外统一叫法）

| 统一叫法 | 含义 |
|---|---|
| **写章（3 批）** | LLM 逐章写正文：批1 封面+第1~4章 / 批2 第5章装配+第6~7章 / 批3 第8章+附录；批间压缩上下文（kanban 轨内部称"3 卡"，同一件事） |
| **装配** | `build_energy_audit_docx.py`（构建）+ `finalize_energy_audit_pdf.py`（收尾：刷目录/转 PDF/盖章） |
| **断言** | `ea_docx_asserts.py` 的 10 项交付硬检查 |
| **就位** | `prepare_chapter_md.py` 把 `chapter5.md` 变成装配输入 `chapter_md/ch5_import.md` |
| **接续契约** | `prepare_writing_context.py` 生成的 `<项目>/chapter_md/_context.md`（每批开工必读） |
| **蓝本** | 同类正式成稿（`audit-examples.md` / 项目侧成稿），只提供**形态** |
| **变量一致性闸门** | `verify_variables_provenance.py`：检查"该变的是否真变"；文字相同不判违规 |
| **直跑轨 / 批量轨** | 单项目会话内直跑 / ≥2 项目交 kanban 编排 |

## 七、相关文件索引

- 分诊：`energy-audit-routing/SKILL.md`
- 共享口径：`energy-audit-core/references/AUTHORITY-INDEX.md`（主题→唯一权威）
- 经验：`energy-audit-core/references/lessons-learned.md`
- 部署与运维：`energy-audit-core/references/deployment-ops.md`
