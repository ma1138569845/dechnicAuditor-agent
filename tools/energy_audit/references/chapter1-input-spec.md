# 第一章 能源审计执行概要 —— 输入内容规范

> 本文档定义「第一章内容生成」所需的输入结构，字段全部对齐当前代码中的最新数据模型：
> - `tools/energy_audit/project_data.py` — `AuditProject` / `ProjectBase` / `BuildingInfo` / `EnergyYearly`（v2.0.0）
> - `tools/energy_audit/report_generator.py` — `build_chapter1()`、`load_from_project()`
> - `tools/energy_audit/data_check.py` — 第一章完整性校验
>
> **RAG 参考模式已过期**：`search_for_chapter()` 仍是库函数，但 `build_chapter1()` **不消费** `rag_reference[]`。
> 1.1–1.5 为固定模板填空；1.6 用 `province_regulations.get_provincial_regulations()` + 固定国标清单。

---

## 一、修改后的 ## 输入内容

保留原有三组输入（`base` / `project_context` / `building_data[]`），
将每组内容按第一章实际消费点细化，并补充来源字段与章节映射：

| 输入 | 内容（第一章所需） | 数据模型来源 | 第一章消费点 |
| ---- | ---- | ---- | ---- |
| `base` | 项目基本信息（审计主体与周期）：审计类型 `unit_type`（公共机构/公共建筑/工业企业）、审计机构 `auditor`、审计项目负责人 `project_manager`、审计起止时间 `audit_start`/`audit_end`、数据统计周期 `data_start`/`data_end`、省份 `province`、报告日期 `report_date`、客户ID `customer_id` | `AuditProject.base`（`ProjectBase`） | 1.1 审计目的（委托机构）；1.3 审计周期（`audit_time`/`audit_cycle`）；1.6 审计依据（省份 → 地方规章检索） |
| `project_context` | 被审计单位概况：单位全称 `unit_name`、简称 `unit_short`、行政归属 `admin_affiliation`、地址 `address`、内设机构/科室 `department_count`、用能人数 `people_count`、床位数 `beds_count`、机构类别 `institution_category`（医疗/教育/党政机关/场馆…）、具体类型 `specific_type`、单位基本情况 `basic_situation`、总建筑面积 `building_area`、建筑数量 `building_count` | `AuditProject.base` + `AuditProject.buildings` 汇总 | 1.1 审计目的（单位简称）；1.2 审计范围（地址、N 栋建筑）；tags → 1.6 审计依据的机构类型 |
| `building_data[]` | 建筑列表（每栋）：`name` 建筑名称、`address` 地址、`year` 竣工年份、`function` 建筑功能、`floors` 层数（地上X层/地下Y层）、`height` 高度、`structure` 结构形式、`area` 建筑面积、`use_area` 使用面积、`function_zoning` 功能分区 | `AuditProject.buildings`（`BuildingInfo`） | 1.2 审计范围（"位于…的 N 栋建筑"）；派生汇总：`building_count = len(building_data)`、`total_area = Σ area` |
| `rag_reference[]`（未接入） | 同类报告写作参考；检索键 `search_for_chapter('第1章', tags, '能源审计执行概要')` | `rag.rag_search.search_for_chapter()` 仍可用，**`build_chapter1()` 不读取此字段** | 历史「参考模式」遗留；不得当作第一章输入 |

补充一行（可自动推导，非人工必填）：

| 输入 | 内容 | 数据模型来源 | 第一章消费点 |
| ---- | ---- | ---- | ---- |
| `energy_types` | 审计周期内实际使用的能源类型（电/水/天然气/热/汽油/柴油）；由 `energy_yearly` 年度数据中非零项自动识别，未采集到时由 `base` 预填 | `AuditProject.energy_yearly` → `report_data.chapter1.energy_types` | 1.2 审计范围（"…等能源账单及能耗统计数据"） |

---

## 二、与 `report_data.chapter1` 的字段映射

`build_rd_from_project()` 已按以下规则从 `AuditProject` 组装 `chapter1`，输入模板应使用同名字段：

| `chapter1` 字段 | 来源字段（当前数据模型） | 生成规则 |
| ---- | ---- | ---- |
| `audited_unit_short` | `base.unit_short` | 空则回退 `base.unit_name` |
| `address` | `base.address` | 直接引用 |
| `buildings` | `building_data[]` | `f"{len(buildings)}栋建筑"` |
| `audit_time` | `base.audit_start` / `base.audit_end` | `f"{audit_start}—{audit_end}"` |
| `audit_cycle` | `base.data_start` / `base.data_end` | ISO 转中文后拼接 |
| `energy_types` | `energy_yearly` 非零能源项 | `['electricity_kwh','water_m3',…]` 自动识别 |
| `province` | `base.province` | 默认 `山东` |
| `audit_org` | `base.auditor` | 封面 `audit_organization` 兜底 |
| `provincial_regulations` | `base.province` + `institution_category` | `province_regulations.get_provincial_regulations()` |

---

## 三、第一章生成所需最小字段（与 `data_check.py` 校验一致）

必填（4 项，缺失则 `check_completeness()` 报错）：

1. `audited_unit_short` — 1.1 被审计单位简称
2. `address` — 1.2 地址
3. `audit_cycle` — 1.3 审计周期
4. `energy_types` — 1.2 能源类型（电/水/气/…）

建议补齐（否则正文出现【审计单位】/【地址】等占位符）：

- `audit_org`（审计机构）
- `audit_time`（审计时间）
- `province`（省份，参与 1.6 地方规章）
- `buildings`（建筑数量描述，1.2 审计范围）
- `tags.institution_category`（机构类型，参与 1.6 地方规章映射）

---

## 四、JSON 输入示例（对齐 `~/projects/energy-audit/<unit>/data.json`）

```json
{
  "base": {
    "unit_type": "公共机构",
    "unit_name": "XX县人民医院",
    "unit_short": "县医院",
    "institution_category": "医疗",
    "specific_type": "医院",
    "address": "XX省XX市XX县XX路1号",
    "admin_affiliation": "XX县卫生健康局",
    "department_count": "23个临床科室、7个医技科室",
    "people_count": 860,
    "beds_count": 600,
    "building_area": 51200,
    "auditor": "同方德诚（山东）科技股份公司",
    "project_manager": "XXX",
    "audit_start": "2025年6月",
    "audit_end": "2025年7月",
    "data_start": "2022-01-01",
    "data_end": "2024-12-31",
    "province": "山东",
    "report_date": "2026年6月",
    "customer_id": 12345
  },
  "buildings": [
    {
      "name": "门诊综合楼",
      "address": "XX省XX市XX县XX路1号",
      "year": 2012,
      "function": "医疗",
      "floors": "地上12层、地下1层",
      "height": "48.5",
      "structure": "框架剪力墙",
      "area": 38200,
      "use_area": 28600,
      "function_zoning": "门诊、住院、医技"
    }
  ],
  "energy_yearly": [
    {
      "year": 2024,
      "electricity_kwh": 4200000,
      "water_m3": 96000,
      "natural_gas_m3": 180000,
      "heating_energy_heat_gj": 21000
    }
  ]
}
```

---

## 五、第一章各小节字段依赖速查

| 小节 | 标题 | 依赖输入 |
| ---- | ---- | ---- |
| 1.1 | 审计目的 | `project_context.unit_short`、`base.auditor`、`base.province` |
| 1.2 | 审计范围 | `project_context.address`、`building_data[]`、`base.data_start/data_end`、`energy_types` |
| 1.3 | 审计周期 | `base.audit_start/audit_end`、`base.data_start/data_end` |
| 1.4 | 审计内容 | 固定模板（无需输入） |
| 1.5 | 审计过程 | `project_context.unit_short`（其余为固定模板） |
| 1.6 | 审计依据 | `base.province`、`project_context.institution_category`（映射后查 `province_regulations`；**不使用** `rag_reference[]`） |
