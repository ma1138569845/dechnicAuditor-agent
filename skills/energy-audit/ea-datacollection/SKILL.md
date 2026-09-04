---
name: ea-datacollection
description: 能源审计项目多源统一数据采集能力。当需要为能源审计项目采集数据、从PG数据库/Excel/用户提供汇总项目信息、构建AuditProject数据模型、检查数据完整性时使用。支持多源兜底采集、字段来源追踪、基础数据问题标记。
version: 2.1.0
---

# Data Collection Skill

## Overview

该 Skill 提供能源审计项目的数据采集能力，是报告生成前的第一道工序。

目标：将数据库、Excel、配置文件和用户输入的数据统一转换为标准 AuditProject 数据模型并持久化。

职责边界：本 Skill 只负责**采集、整理、追踪、基础完整性检查**。深度异常分析、能效指标判断、设备性能诊断由下游分析 Agent 完成。

---

## Capability 1: Multi Source Collection

### 数据来源优先级

```
PG数据库（首选）
   ↓ 缺失
Excel文件（用户提供）
   ↓ 缺失
对话引导（询问用户）
   ↓ 缺失
Default 默认值（必须标注）
```

规则：

- 高优先级覆盖低优先级（PG 已有的字段不可被 Excel 覆盖）
- 每次覆盖必须记录来源
- 默认值必须明确标记 `source: Default`

---

## Capability 2: PostgreSQL Data Collection

### 连接

```
PostgreSQL
10.10.1.165:5432
dc_energy_audit2
```

连接配置统一走 `db_config.get_pg_config()` 解析链（参数 > 环境变量 > config.yaml > 默认值），密码不得硬编码。

### 采集工具

```python
from tools.energy_audit.pg_collector import collect_from_pg

result = collect_from_pg(project_name)
# → {'found': {...}, 'missing': [...], 'project_id': ...}
```

输出结构化结果：找到 N 类数据、缺失 M 项（逐条列出，含字段名和 PG 表名）。

### 数据覆盖范围

| 数据类别 | PG表 | Excel/Config补充 |
|----------|------|------------------|
| 项目基本信息 | ts_institution_project | unit_short/address/... |
| 客户信息 | ts_customer_info | basic_situation |
| 建筑信息 | ts_institution_build | 层数/结构/保温/冷热源 |
| 年度能耗 | ts_institution_energy_main (data_type=1) | 费用数据 (data_type=2) |
| 周期能耗明细 | ts_institution_energy_data (period_code + energy_value) | 手动录入 |
| 设备清单 | ts_institution_device_air/light/office/power/hygiene/hotwater/other/special/steam | 自定义设备 |
| 计量器具 | ts_institution_scene(计量基本情况)/ts_institution_energy_meter(表具详细) | 现场确认 |
| 节能管理 | ts_institution_energy_saving | 管理文件/制度/奖项 |
| 人员信息 | ts_project_audit_user / ts_project_audited_user | 审计组/被审计方 |
| 图片 | ts_institution_build.build_img（建筑外观）/ ts_institution_energy_meter.device_img（电水表照片）/ 设备分表 _img 列（第6章设备照片）/ ts_institution_energy_invoice+invoice_image（缴费发票照片，record_id 关联）/ meter.ledger_files·year_files·month_files（计量台账）/ 设备分类表 ledger_files | 现场照片补充 |

### 能耗表版本机制（⚠️ 取数铁律）

`ts_institution_energy_main` 同一 (year, data_type, energy_code) 可能并存**三套版本**：草稿（is_draft=1, version_code=NULL）+ 多个正式版本（is_draft=0, version_code 非空，如 PL2026080401/0402）。历史事故：版本间数值冲突时若用"多数投票"消解，错误被复制进两个正式版本后 2:1 必然选中错误值（烟台法院 2025 年电量、2024/2025 热力颠倒事故）。

取数规则（`pg_query.py` 已内置 DISTINCT ON 版本归一，直接调用即可）：

1. 同一键只取一条：**草稿优先**（is_draft=1=最新编辑数据），无草稿时 version_code 大者优先；
2. **禁止多数投票消解冲突**；版本间数值不一致时必须输出冲突告警清单，人工核实后修正 DB；
3. 年度总量与逐月加总交叉校验，费用÷单价=用量校验。

### 能耗表结构（main + data 两表）

原单表 `ts_institution_energy`（value1-value12 月度列）已拆分为两表：

- **ts_institution_energy_main**：元数据 + 年度总量。关键字段：`year`、`data_type`（1=能耗/2=费用/3=供冷能耗/4=供热能耗/5=交通能耗）、`energy_code`/`energy_name`、`energy_unit`、`total_value`（年度合计）、`real_value`(单位实际的用能量)、`standard_coal_coefficient`（折标系数）、`granularity`（记录粒度：1=月/2=双月/3=季度/4=半年）
- **ts_institution_energy_data**：周期明细。`main_id` 外键关联主表，`period_code` 与粒度对应（`'01'`=单月、`'01~02'`=双月、`'01~03'`=季度、`'01~06'`=半年），`energy_value` 为该周期总量

采集逻辑（`pg_query.py` 的 `PgDataQuery.get_institution_energy`）：

```sql
SELECT m.id, m.year, m.data_type, m.energy_code, m.energy_name,
       m.energy_unit, m.standard_coal_coefficient,
       m.total_value AS building_total_value, m.real_value AS unit_total_value,
       m.granularity, m.customer_id, d.period_code, d.energy_value
FROM ts_institution_energy_main m
LEFT JOIN ts_institution_energy_data d ON d.main_id = m.id
WHERE (m.deleted IS NULL OR m.deleted = 0)
```

周期值按覆盖月数**均摊展开**为 12 个月列表（`PgDataQuery.expand_periods_to_monthly()`），保持下游 `monthly_xxx_kwh` 12 元素契约不变：

```
'01'     → [1]         值原样落位
'01~03'  → [1,2,3]     每月 = 周期值 ÷ 3
'01~06'  → [1..6]      每月 = 周期值 ÷ 6
```

注意：本 Skill 的采集仅消费 `data_type=1`（能耗）与 `data_type=2`（费用）；`data_type=3/4/5`（供冷/供热/交通分项）由下游第5章 Agent 处理。

---

## Capability 3: Excel Import

支持：能源账单、设备清单、建筑信息、混合清单、人工补录数据。

### 采集工具（已实现，`excel_processor.py`）

```python
from tools.energy_audit.excel_processor import ExcelDataProcessor
from tools.energy_audit.pg_collector import build_and_save_project

processor = ExcelDataProcessor("能耗数据.xlsx")

# 1) 读取 + 清洗
df = processor.read_excel(sheet_name=0)
df = processor.clean_data(df)

# 2) 按类别转换为 excel_data 字典片段
excel_data = processor.to_excel_data('energy', df)   # → {'energy_yearly': [...]}

# 3) 多类别合并为完整字典（可选）
#    sheets = {'base': df_base, 'buildings': df_b, 'energy': df_e,
#              'equipment': df_eq, 'metering': df_m}
#    excel_data = processor.build_excel_data(sheets)

# 4) 接入构建（excel_data 与 PG 结果合并，优先级 PG > Excel）
proj = build_and_save_project(project_name, excel_data=excel_data, pg_result=result)
```

- `to_excel_data(category, df)`：`'base'`（顶层标量）/ `'buildings'` / `'energy'` / `'equipment'` / `'metering'`，返回 excel_data 字典片段。
- `build_excel_data(sheets)`：多类别 DataFrame 合并为完整 excel_data 字典。
- 未匹配的列自动跳过并打印提示，不阻塞。

### 字段映射规则（自动识别列头，已实现于 `excel_processor.EXCEL_SCHEMAS`）

| Excel字段 | 标准字段 | 适用类别 |
|-----------|----------|----------|
| 年份 / year | year | energy / buildings |
| 用电 / electricity / 电(kWh) / 电量(kWh) / 用电量 | electricity_kwh | energy |
| 用水 / water / 水(m³) / 水量 / 用水量 | water_m3 | energy |
| 天然气 / gas / 气(m³) / 燃气 | natural_gas_m3 | energy |
| 建筑面积 / 面积(㎡) / building_area | building_area（base）/ area（buildings） | 依类别 |
| 设备名称 / equipment_name | name | equipment |
| 数量 / quantity / 台数 / device_num | quantity | equipment |

列头匹配优先级：**精确 > 包含（最长别名优先）> 编辑距离（levenshtein）**。
单字别名（如"电"）不会误吞"电费"等费用列（费用列精确命中断言到 `electricity_cost_wan` 等）。

---

## Capability 4: Data Mapping

所有来源数据统一转换为 AuditProject 结构：

```json
{
  "base": {},
  "buildings": [],
  "energy_yearly": [],
  "equipment": [],
  "metering": {},
  "management": {},
  "energy_saving": [],
  "images": [],
  "data_sources": {}
}
```

### 构建工具

```python
from tools.energy_audit.pg_collector import build_and_save_project

proj = build_and_save_project(project_name, excel_data=excel_data, pg_result=result)
```

- `excel_data` 可选，提供时与 PG 数据合并（**优先级 PG > Excel**）；
- `pg_result` 可选，复用 `collect_from_pg` 已采集的结果，**避免二次查询 PG**；
- **副作用注意**：函数内部会下载附件图片、LLM 提炼管理制度、`save_project(proj)` 持久化，不纯是内存构建。

### 单位转换

- **费用**：PG 中的 `total_value`（单位：元）统一 **÷10000 转成万元**，存入 `xxx_cost_wan` 字段（如 `electricity_cost_wan`、`water_cost_wan`）。

---

## Capability 5: Data Traceability

保存字段级来源追踪（字符串映射，非嵌套对象）：

```json
{
  "unit_name": "PG",
  "address": "Excel",
  "basic_situation": "PG",
  "people_count": "default"
}
```

由 `SourceResolver` 统一记录（`pg_collector.py`），来源取值：`PG` / `Excel` / `default`。最终写入 `AuditProject.data_sources`（`Dict[str, str]`）。

---

## Capability 6: Completeness Check

### 检查工具

```python
from dataclasses import asdict
from tools.energy_audit.data_check import check_completeness

ok, issues = check_completeness(asdict(proj))
# 返回 (bool, List[str])：完整? , 缺失项列表
```

> 注意：`check_completeness` 接收的是 **dict**（`asdict(proj)`），不是 AuditProject 对象。其内部检查的是报告数据结构键（`cover` / `audit_info_tables` / `chapter1` / `chapter2` / `chapter5` / `chapter6`），与 `asdict(proj)` 的键（`base` / `buildings` / ...）并不完全对应，可能列出与项目数据无直接映射的缺失项；最终以 `data_collection_cli` 控制台输出为准。

### 检查项（data_check.py 实际逻辑）

- **封面**：报告标题
- **三张表**：被审计单位名称、审计组人员名单
- **第1章**：单位简称、地址、审计周期、能源类型
- **第2章**：建筑面积、用能人数、建筑列表
- **第5章**：能耗数据
- **第6章**：设备清单

### 输出

```python
(False, ["封面 → 报告标题", "2.1 → 建筑面积", ...])
```

---

## Capability 7: Basic Data Issue Detection

仅进行**基础数据问题标记**（`detect_anomalies()` / `detect_area_mismatch()`，位于 `data_collection_cli.py`），不做专业分析诊断。

### 标记项

1. **完整性检查** — `check_completeness()`：关键字段缺失逐项列出
2. **环比超阈值标记** — 用电/用水环比 >30% 标记"警告"，>50% 升级为"严重"（天然气不做环比检查）；仅标记"需核实"，不做原因判断
3. **月度全零标记** — 用电/用水/天然气某年 12 个月逐月数据全为 0 → 标记"可能漏录"
4. **面积偏差提示** — `detect_area_mismatch()`：各建筑面积合计与声明总面积偏差 >5% 时提示（仅提示，不修正数值，口径由用户确认）

> 注意：当前 `data_collection_cli.py` 的 CLI 流程**只自动调用了 `detect_anomalies`**；`detect_area_mismatch` 已实现但尚未接入命令行流程。

### 输出方式（重要）

异常标记**只体现在采集报告文本中，不持久化到 data.json**：

```
采集 → detect_anomalies() → format_collection_report() 控制台输出
     → build_and_save_project()（内部 save_project，proj 不含 anomalies）
```

正式的异常检测、KG 归因、分诊定级由下游 DataVA 的 V1 DATA_CHECK 独立全量执行（`analyze_with_diagnosis`），不依赖本 Skill 的标记。

### 明确边界

本 Skill **不负责**：

- COP 分析
- 节能潜力判断
- 设备性能诊断
- 单位面积能耗指数合理性评价（属能效指标分析，由 EnergyAnalysisAgent 完成）
- 异常原因的推断与定性（属 datava 职责）

---

## Execution Workflow

```
1. 接收项目任务
   ↓
2. 查询 PG 数据（PG 连接失败会抛异常；项目/数据缺失时落入 missing 清单，不中断）
   ↓
3. 导入 Excel 补充（PG 缺失项）
   ↓
4. 数据字段映射 + 单位转换（元 → 万元）
   ↓
5. 完整性检查 + 基础问题标记
   ↓
6. save_project() 持久化 AuditProject（build_and_save_project 内部完成）
   ↓
7. 输出采集报告（含缺失项/数据问题，引导用户补充）
```

对话引导（与 `pg_collector` 输出一致）：

```python
print(f"[datacollection v2] PG查询完成: 找到{found_count}类数据, 缺失{missing_count}项")
for m in missing_items:
    print(f"  · {m}")
```

---

## Output Template

```
═══════════════════════════════════
📊 DataCollection 采集报告
═══════════════════════════════════

📌 项目: 山东省立医院东院
📡 PG 连接: [✔] 成功

✅ 已采集到:
  · 基本信息: 省立医院东院 / 山东省卫生健康委员会
  · 建筑: 7栋 (合计 67636 m²)
  · 能耗: 3年 (2022-2024) 电/水/天然气/热
  · 设备: 空调 12台, 照明 45类, 办公 30类
  · 计量: 有监测系统

⚠️ 缺失项【待补充】:
  · 建筑信息（ts_institution_build）
  · 乙方审计组长: 请联系管理员获取

🔍 数据问题标记:
  · 2023年用电环比+42% → 超过30%阈值，需核实
  · 2022年天然气月度数据全为0 → 可能漏录

📁 数据持久化位置: ~/projects/energy-audit
```

---

## Error Handling

### PG 连接失败

```
PG连接失败 → psycopg2 异常向上抛出（当前代码无降级逻辑）
```

> 当前实现：`collect_from_pg` 用 try/finally 保证连接释放，但**不捕获连接异常**。若需"PG 失败继续走 Excel"，调用方应自行 try/except 降级（当前 `data_collection_cli` 未做）。

### Excel 格式异常

- 模糊匹配字段（contain / levenshtein）
- 无法识别的字段跳过并输出提示列表

---

## Pitfalls

- **数据覆盖关系**：PG > Excel > User > Default，高优先级字段不可被低优先级覆盖
- **月度数据同步**：`EnergyYearly.monthly_electricity_kwh` 等必须在 `EnergyYearly`、`config_xxx.json`、`agent-caliber` 的 dict 三处同步
- **面积冲突**：建筑列表面积之和 ≠ 总建筑面积时，以各建筑面积之和为准并提示（统一用 `project_data.total_building_area()` 计算）
- **图片路径**：附件由 `file_resolver.enrich_energy_saving_images` 下载到 `reports/attachments/`，`file.base_url` 未配置时静默跳过，不阻塞采集
- **构建副作用**：`build_and_save_project` 会持久化 + 下载附件 + 调用 LLM，非纯内存构建，避免重复调用

---

## Rules Summary

必须：

- ✅ 数据真实，不编造、不修改原始数据
- ✅ 来源明确，字段来源写入 `data_sources`（PG / Excel / default）
- ✅ 缺失标记【待补充】并主动反馈
- ✅ 结构统一，输出标准 AuditProject
- ✅ **采集必须走 repo 工具链**（`tools/energy_audit/` 的 `pg_collector`/`pg_query`/`data_collection_cli`/`excel_processor`/`file_resolver`），PG 连接配置走 `db_config.get_pg_config()`，不得硬编码密码

禁止：

- ❌ 编造数据
- ❌ 静默留空或自动填充
- ❌ 输出专业诊断结论（COP/节能潜力/设备诊断）
- ❌ **手写 psycopg2 直连脚本或现场探测表结构**（历史事故：worker 因工具链不可用自建 collect*.py，导致版本不过滤、图片不采集、人员不落地，最终报告 20 处【待补充】）。工具链不可用时（import 失败），**停下来报告断链原因**，不得自行造轮子
- ❌ 对版本冲突数据做多数投票静默消解（必须告警）