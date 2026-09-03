# 版本归一规则（权威）

> 适用所有 `ts_institution_*` 业务表取数。**禁止多数投票**。

## 版本机制

同一条业务数据在 DB 中并存多个版本：

| 版本类型 | 标识 | 说明 |
|---------|------|------|
| 草稿 | `is_draft=1`、`version_code=NULL` | 平台编辑中的未发布数据 |
| 正式版本 | `is_draft=0`、`version_code` 非空（如 `PL2026080401`） | 已发布快照，可能有多个 PL 号 |

## 归一规则（取数时）

同一业务键并存多版本时，**只取一条**：

1. 正式版本（is_draft=0 且 version_code 非空）优先；
2. 多个正式版本时，version_code 字符串大者优先（PL2026080402 > PL2026080401）；
3. 无正式版本时草稿兜底。

## 各表业务键

| 表 | 业务键（分组键） | 说明 |
|----|----------------|------|
| ts_institution_energy_main | year + data_type + energy_code | 如 (2025, 1, '45') |
| ts_institution_build | build_name | 同名建筑 = 同楼多版本 |
| ts_institution_scene | year | |
| ts_institution_energy_meter | data_type + statistical_year | |
| ts_institution_energy_saving | （节能量类型） | |
| ts_institution_device_* | device_name + power + power_unit | 无版本列的表回退全量 |

## 为什么禁止多数投票

历史事故：错误值被平台升级流程复制进多个正式版本后，多数投票 2:1 会选中错误值
（烟台法院 2024/2025 热力 3,246↔3,575 颠倒即由此造成；草稿正确、两个正式版本皆错，
多数投票取正式版本错误值）。版本优先级规则不依赖数据正确性，只依赖版本元数据。

## 代码落点

- 能耗：`tools/energy_audit/pg_query.py::get_institution_energy`（子查询 DISTINCT ON）
- 建筑/场景/表具/设备：`pg_query.py::get_institution_build / get_institution_scene / get_energy_meter / _get_device_by_table`
- 采集侧校验：`data_collection_cli.py` 的 anomalies 检测
