# tools/energy_audit 工具包 API 索引

> 位置：`$HERMES_AGENT_HOME/tools/energy_audit/`（`HERMES_AGENT_HOME` 环境变量指定项目根；缺省按 `_paths.py` 三级降级自动解析）
> 当前项目根：`D:/data/pyProject/dc_agent/dechnicAuditor-agent`
> 导入前置：`tools.energy_audit._paths.project_root()`（模块加载即注入 sys.path）
> 数据库：PG `10.10.1.165:5432/dc_energy_audit2`，连接配置见 `db_config.py`（运行时密码用 `EA_PG_PASSWORD` 传入）

## A. 通用数据层（所有 Agent 按需使用）

| 模块 | 入口 | 场景 |
|------|------|------|
| `project_data.py` | `AuditProject` / `ProjectBase` / `BuildingInfo` / `EnergyYearly` / `EnergyMonthly` / `Equipment` / `MeteringInfo` / `save_project(proj)` / `load_project(unit_name)` | data.json 标准数据模型 + 持久化/读取（`~/projects/energy-audit/<单位名>/data.json`） |
| `_paths.py` | `project_root()` | 统一解析项目根目录 |
| `db_config.py` | `get_pg_config()` | PG 连接配置解析 |
| ~~`config_validator.py`~~ | — | ⚠️ 已删除：旧 config JSON Schema 校验不复存在，当前无独立 config 校验，由调用方 / `data_check.py` 负责 |
| ~~`data_validator.py`~~ | — | ⚠️ 已删除：data.json 校验已并入 `data_check.py::check_completeness` |

## B. datacollection（采集）

| 模块 | 入口 | 场景 |
|------|------|------|
| ~~`data_collector.py`~~ | — | ⚠️ 已删除：采集编排在 `data_collection_cli.py`，异常检测（`detect_anomalies` / `detect_area_mismatch`）在 `data_analysis.py` |
| `pg_collector.py` | `collect_from_pg(project_name)` / `build_and_save_project(project_name, excel_data=None, pg_result=None)` | PG 表查询（ts_institution_* 系列）+ 构建持久化 |
| `pg_query.py` | `PgDataQuery` | 周期明细查询 + `expand_periods_to_monthly()` 均摊为 12 月 |
| `excel_processor.py` | `ExcelDataProcessor(file_path)` / `compute_audit_indicators` | Excel 读表 + 列头模糊映射 |
| `data_check.py` | `check_completeness(report_data)` / `print_missing_report` | 完整性检查（关键字段缺失逐项列出） |
| `institution_classifier.py` | `classify_institution` | 机构类型分类 |
| `province_regulations.py` | `get_generic_regulations` / `get_provincial_regulations` | 省级能源审计规章查询 |
| `photo_manager.py` | `check_photos` / `get_photo_checklist` | 现场照片需求检查 |

```python
from tools.energy_audit.pg_collector import collect_from_pg
result = collect_from_pg("日照市岚山区人民医院")   # → {'found': {...}, 'missing': [...], 'project_id': ...}
```

## C. datava（异常检测 / 深度诊断）

| 模块 | 入口 | 场景 |
|------|------|------|
| `data_analysis.py` | `analyze_with_diagnosis` / `analyze_energy_data` / `format_anomaly_report` / `infer_system` / `AnomalyItem` / `AnalysisResult` | 异常检测 + KG 因果诊断 + 分诊（V1 DATA_CHECK 全量执行） |

## D. caliber（指标计算 / 第5章 / 能流图）

| 模块 | 入口 | 场景 |
|------|------|------|
| `indicators.py` | `YearlyEnergyData` / `resolve_coefficient` / `resolve_benchmark` / `lookup_coefficient_from_db` / `lookup_benchmark_from_db` / `institution_category_to_type` | 5 项指标计算 + 折标系数/定额三级兜底 |
| `energy_flow_chart.py` | `draw_energy_flow_diagram` | 能源流向图（Graphviz） |
| `chapter5_agent.py` | `generate_chapter5_md` / `generate_charts` / `calc_yearly_tce` / `load_from_db` / `load_from_user` | 第5章 Markdown + 图表 |

## E. author / editor（报告生成与质检）

| 模块 | 入口 | 场景 |
|------|------|------|
| `report_generator.py` | `WordReportBuilder`（仿写渲染）/ `CHAPTER_STRUCTURES` / `load_from_project` | 仅供 imitate 仿写模式渲染；正文生成已退役 |
| `report_qa.py` | `check_report` | 报告自动质检 |
| `example_report.py` | `generate_sample_report` | 示例报告生成（参考模板） |
| `ingest_reports.py` | （见下方废弃标注） | 历史报告入库（已迁移） |

## ⚠️ 废弃/迁移（不要调用）

| 模块 | 状态 | 新位置 |
|------|------|--------|
| `energy_kg.py` | DEPRECATED | `rag.knowledge_graph.energy_kg` |
| `kg_visualizer.py` | DEPRECATED | `rag.knowledge_graph.kg_visualizer` |
| `knowledge_schema.py` | DEPRECATED | `rag.knowledge_graph.knowledge_schema` |
| `ingest_reports.py` | DEPRECATED | `rag.ingestion.ingest_reports` |

## 🗑 临时脚本（已清理）

`_apply_tasks.py`、`_fix_task6.py` — 一次性历史任务脚本，已从目录删除。

## 使用铁律

1. **按需调用**：先看本索引确认入口函数名，再 import，勿凭文件名猜测
2. **不重复造轮子**：已有模块实现的逻辑（折标系数兜底、月度均摊、路径解析）不要重写
3. **废弃模块不用**：DEPRECATED 的 4 个模块 import 会失败或指向 rag.*，直接用新位置
4. **环境对齐**：`HERMES_AGENT_HOME` 指向项目根（或 `pip install -e .`），路径解析统一走 `_paths.py`
