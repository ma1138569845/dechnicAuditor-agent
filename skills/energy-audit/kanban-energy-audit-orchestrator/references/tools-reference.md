# 工具集参考：energy_audit 工具与各角色使用矩阵

> 权威定义：repo `toolsets.py` 的 `energy_audit` toolset（9 个工具）。
> 各 profile config.yaml 须配置 `toolsets: [hermes-cli, energy_audit]`（已配，2026-09 校验）。
> hermes-cli 提供 terminal/file/web 等默认工具；energy_audit 提供能源审计专用工具。

## 工具清单（9 个）

| 工具 | 能力 | 底层 |
|------|------|------|
| `energy_audit_search_projects` | 按名称模糊搜索项目（确认项目存在/名称不确定时） | pg_query.py |
| `energy_audit_get_project` | 项目完整信息（基本信息+建筑+能耗+设备+人员+计量） | pg_collector.py |
| `energy_audit_get_buildings` | 建筑信息查询 | pg_query.py（版本归一） |
| `energy_audit_get_energy` | 能耗数据查询（可按年度） | pg_query.py（版本归一） |
| `energy_audit_get_energy_meter` | 计量表具查询（电表/水表、分项计量、计量深度） | pg_query.py |
| `energy_audit_get_equipment` | 设备清单（空调/照明/办公/动力/卫生器具/生活热水/蒸汽/特殊） | pg_query.py |
| `energy_audit_rag_search` | **RAG/知识图谱检索**（历史报告、法规标准、机构资料） | rag_retrieval.py |
| `energy_audit_imitate_paragraph` | 按参考报告段落结构仿写段落 | imitate_pipeline.py |
| `energy_audit_imitate_report` | 整份同类报告仿写生成 Word | imitate_pipeline.py |

## 关键机制：service-gated

- PG 查询类工具在**未配置 PG 连接时会被 check_fn 自动过滤**（worker 拿不到工具）。
- 前置条件：Hermes config.yaml 的 `energy_audit.database` 段已配（10.10.1.165/dc_energy_audit2），
  见 kanban-setup.md 的"环境前置检查"。
- RAG 工具依赖 Qdrant（10.10.2.55:6333）在线；不可用时该工具返回错误，须降级（见下）。

## 各角色使用矩阵

| 工具 | datacollection | datava | caliber | author | editor |
|------|:-:|:-:|:-:|:-:|:-:|
| search_projects | ● | ○ | | ○ | |
| get_project | ● | ● | | ● | ○ |
| get_buildings | ● | ● | | ○ | ○ |
| get_energy | ● | ● | ● | ● | ○ |
| get_energy_meter | ● | ● | | ○ | ○ |
| get_equipment | ● | ● | | ● | ○ |
| **rag_search** | ○ | ● | ● | ● | |
| imitate_paragraph | | | | ● | |
| imitate_report | | | | ● | |

● 主要使用　○ 复核/交叉核对时使用

## RAG 检索（energy_audit_rag_search）使用场景

RAG 检索知识库内容（历史审计报告、法规标准文档、机构资料），四个角色的典型用法：

| 角色 | 场景 | 检索目标 |
|------|------|----------|
| datava | V1 异常诊断佐证、V3 报告审查对照 | 同类机构历史报告的异常处理方式 |
| caliber | 定额标准核验（DB37/T 2672/2673 原文段落）、省级规章确认 | 标准原文、省级规章条款 |
| author | 1.6 审计依据的省级规章原文、机构背景资料、同类报告写作参考 | 法规条款、同类报告段落 |
| datacollection | 数据采集口径参考 | 历史项目采集口径 |

**铁律**：
1. RAG 检索结果只是**参考线索**，写入报告的定额值/法规条文必须以
   `energy-audit-core/references/standards-values.md`（定额矩阵权威）和
   web_search 验证的原文为准，禁止把 RAG 命中段落直接当权威抄写。
2. 省级规章必须 web_search 验证（禁止字符串替换省份名）——RAG 命中可作为
   "哪个规章哪条"的线索，但最终表述要与检索到的官方原文核对。
3. RAG 不可用时降级链：core skill 的 standards-values/coefficient-caliber →
   web_search → 向用户索取。

## 工具 vs CLI 脚本的分工

- **采集主链路**：`python tools/energy_audit/data_collection_cli.py <项目名>`
  （版本归一+异常检测+图片采集+指标预计算一体，输出 data.json）。
- **单点查询/核对**：energy_audit_* 工具（worker 中途反查 DB、验证某个值）。
- 规则：worker 禁止手写 psycopg2 脚本直连 DB（2026-08 断链事故），
  一律走工具或 CLI；DB 写操作只由主会话执行（带备份）。

## 各角色工具集配置（config.yaml 实际值）

| Profile | toolsets | disabled_toolsets |
|---------|----------|-------------------|
| datacollection | hermes-cli, energy_audit | browser, vision, video, image_gen |
| datava | hermes-cli, energy_audit | browser, vision, video, image_gen, moa |
| caliber | hermes-cli, energy_audit | browser, vision, video, image_gen |
| author | hermes-cli, energy_audit | browser, vision, video, image_gen |
| editor | kanban, hermes-cli, terminal, file, vision | —（编排者：不装 energy_audit；hermes-cli 提供 web_search/execute_code，供 V3 审查做规章验证与程序化核对；DB 核对通过读 data.json 或用主会话） |

> 若 worker 报告"没有 energy_audit 工具"，先查 profile config 的 toolsets 与
> Hermes config 的 energy_audit.database 段，再查 sync_ea_skills.py 是否发布
> 了对应技能（工具和技能是两套体系，缺一不可）。
