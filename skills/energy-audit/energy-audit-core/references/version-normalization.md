# 版本归一规则（权威）

> 适用所有 `ts_institution_*` 业务表取数。**禁止多数投票**。

## 版本机制（对齐后端 dc_audit-main）

同一条业务数据在 DB 中并存多个版本：

| 版本类型 | 标识 | 说明 |
|---------|------|------|
| 草稿（原始数据） | `is_draft=1`、`version_code=NULL` | **平台编辑中的最新数据**（用户每次修改都落在这里） |
| 正式版本（快照） | `is_draft=0`、`version_code` 非空（如 `PL2026080401`） | 发布时由后端 `CustomerVersionService.saveVersion` 把当时的草稿**复制**一份并打版本号，草稿本身保留继续作活数据 |

后端取数口径（`ExtractDataAgent.applyVersionOrDraft`）：报告生成指定版本号时按 `version_code` 取快照；未指定时取草稿（`is_draft=1`）。

## 归一规则（采集取数时）

同一业务键并存多版本时，**只取一条**：

1. **草稿优先**（is_draft=1，最新编辑数据）；
2. 无草稿时，正式版本 version_code 字符串大者优先（PL2026080402 > PL2026080401）；
3. 同版本号多条时 id 大者优先（历史垃圾兜底）。

> ⚠️ 项目表 `ts_institution_project.version_code` 存在"锁定版本"字段，但采集**不按它过滤**（用户 2026-09-04 明确：不锁版本，一律取草稿=最新数据）。后端报告生成若锁了版本，其数据可能与采集的草稿不一致——以平台实际发布状态为准。

## 各表业务键

| 表 | 业务键（分组键） | 说明 |
|----|----------------|------|
| ts_institution_energy_main | year + data_type + energy_code | 如 (2025, 1, '45') |
| ts_institution_build | build_name + build_func | 同名建筑 = 同楼多版本 |
| ts_institution_scene | year | |
| ts_institution_energy_meter | data_type + statistical_year | |
| ts_institution_energy_saving | statistical_year（NULL 用 0 兜底） | |
| ts_institution_device_* | device_name + power + power_unit | 无版本列的表回退全量 |

## 为什么禁止多数投票

历史事故：错误值被平台升级流程复制进多个正式版本后，多数投票 2:1 会选中错误值
（烟台法院 2024/2025 热力 3,246↔3,575 颠倒即由此造成）。版本优先级规则只依赖版本元数据，
不依赖数据正确性：草稿=最新编辑，永远是用户最后意图的体现，故草稿优先。

## 代码落点

- 能耗（含费用）：`tools/energy_audit/pg_query.py::get_institution_energy`（子查询 DISTINCT ON，`COALESCE(is_draft,0) DESC` 草稿优先）
- 建筑/场景/表具/节能管理/设备：`pg_query.py::get_institution_build / get_institution_scene / get_energy_meter / get_institution_energy_saving / _get_device_by_table`（同口径）
- 采集侧校验：`data_collection_cli.py` 的 anomalies 检测
