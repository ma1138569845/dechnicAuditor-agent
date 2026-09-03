# 多 Agent 流水线架构 (v3.0)

> 历史 `run_pipeline.py` 工作流**已移除**（该脚本全库不存在）。当前流水线由
> **Hermes 模型工具**（`tools/energy_audit_*_tool.py`）+ **CLI 编排脚本**
> （`data_collection_cli.py`）+ **数据持久化**（`project_data.py::save_project`）驱动。

## 当前调用方式

### 方式 A：Hermes Agent 工具（模型自主调用）

8 个 `energy_audit_*` 工具注册于 `toolset="energy_audit"`，工具名写在
`toolsets.py::_HERMES_CORE_TOOLS`（= 默认 `hermes-cli` toolset），对所有
profile 默认可见（`check_fn` 通过时）：

| 工具 | 能力 |
|------|------|
| `energy_audit_search_projects` / `_get_project` / `_get_equipment` / `_get_buildings` / `_get_energy` / `_get_energy_meter` | PG 查询（`pg_collector.py` / `pg_query.py`） |
| `energy_audit_rag_search` | RAG 检索（`rag/rag_retrieval.py`） |
| `energy_audit_imitate_paragraph` | 仿写（`imitate_pipeline.py`） |

### 方式 B：CLI 编排（采集 → 构建 → 质量检查）

```bash
python tools/energy_audit/data_collection_cli.py <项目名>
```

执行流程：
`collect_from_pg`（PG 取数）→ 能耗异常检测 / 建筑面积校验 → 格式化采集报告

## 数据持久化

- 项目数据：`project_data.py::save_project()` → `~/projects/energy-audit/<单位名>/data.json`
- 各组件从 `data.json` 读取，不再各查各的数据

## 阶段分工（对应 agent 技能）

| 阶段 | 模块 | 技能 | 说明 |
|------|------|------|------|
| 采集 | `pg_collector.py` / `pg_query.py` / `excel_processor.py` | `ea-datacollection` | PG 取数 + 构建 `AuditProject` |
| 验证 | `data_analysis.py` / `data_check.py` | `ea-validation` | 异常检测 + KG 因果诊断 |
| 计算 | `indicators.py` / `chapter5_agent.py` / `energy_flow_chart.py` | `ea-calculation` | 5 项指标 + 第5章 + 能流图 |
| 报告 | `report_generator.py` / `report_qa.py` | `ea-authoring` | 8 章 .docx / .md 生成 + 质检 |

## 与旧方式对比

| 旧 (`run_pipeline.py`，已删除) | 新 |
|-------------------------------|-----|
| 单一 Python 脚本串起全流程 | Hermes 工具（模型自主）+ `data_collection_cli.py`（CLI）双入口 |
| 数据在内存中用完丢弃 | `save_project()` 持久化到 `~/projects/energy-audit/` |
| 每个项目单独写脚本 | 统一入口，换项目只改配置/参数 |
