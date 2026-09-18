# conventions
> 本文由 5 个文件合并而成（2026-09-18 瘦身合并第 2 组，原文件已归档至 `_archive/2026-09-18/energy-audit-core/references/`）：`project-granularity.md`、`three-layer-fallback.md`、`config-schema.md`、`audit-info-tables.md`、`iso-date-to-cn.md`；内容逐字保留，仅统一标题层级，引用请一律指向本文件对应小节。

---

## 项目粒度：一个机构 = 一个项目 = 一份报告（原 project-granularity）

### 核心规则

**一个公共机构 = 一个项目 = 一份能源审计报告。**

一个项目可能包含多栋建筑（如省立医院东院有7栋楼），但只生成一份涵盖所有建筑的完整报告。

### 错误 vs 正确

| 错误（建筑级） | 正确（项目级） |
|---------------|---------------|
| 每栋楼4步Kanban任务 | 每个项目4步Kanban任务 |
| 每栋楼一份独立报告 | 每个项目一份完整报告 |
| 100栋楼 = 400个任务 | 100个项目 = 400个任务 |
| config.json 只含一栋楼 | config.json 含全部建筑 |

### Kanban 任务图

```
Director (汇总审查)
  ├─ 项目A: 采集→验证→计算→报告 ──┐
  ├─ 项目B: 采集→验证→计算→报告 ──┤
  └─ 项目C: 采集→验证→计算→报告 ──┘
     ↑ 纵向串行     ↑ 横向并行
```

- 同一项目内4步严格串行（父子依赖）
- 不同项目之间完全并行（互不依赖）
- Director 等待全部项目报告完成后汇总

### 常见误解

- "7栋楼需要7份报告" → 错。7栋楼是1个公共机构的组成部分，1份报告即可。
- "每栋楼配置不同要分开" → 错。config.json 应包含全部建筑数据，采集步骤一次处理。
- "建筑级别更细粒度，更灵活" → 错。审计报告的法律主体是公共机构，不是单体建筑。

---

## 兜底原则（原 three-layer-fallback；层数以 ea-calculation/SKILL.md 的四级为准）

所有指标计算遵循 Layer 1→2→3 降级策略。

### 折标系数 (`resolve_coefficient`)

```
Layer 1: DB (ts_institution_energy_main.standard_coal_coefficient)
         ↓ 合理性检查（超出范围跳过）
Layer 2: 用户显式提供
         ↓
Layer 3: 内置默认值（GB/T 2589-2020）
```

合理性范围：
| 能源 | 范围 | 默认值 |
|------|------|--------|
| 电 | 0.1~1.0 kgce/kWh | 0.31 |
| 水 | — | 不折标（DB37 附录B） |
| 天然气 | 0.5~2.5 kgce/m³ | 1.2143 |
| 热 | 0.01~0.05 tce/GJ | 0.03412 |
| 柴油 | 1.0~2.0 tce/t | 1.4571 |
| 汽油 | 1.0~2.0 tce/t | 1.4714 |

> 山东公共机构审计口径统一 DB37/T 附录B（权威见 coefficient-caliber.md）；GB/T 2589 当量值仅作背景参考。非供暖能耗计算使用等效电系数 0.31（非 0.1229）。

### 定额对标 (`resolve_benchmark`)

```
Layer 1: DB (ts_limit_config, field_type + limit_type + climate_type)
         ↓
Layer 2: 用户提供 (约束值, 基准值, 引导值)
         ↓
Layer 3: 内置默认值 (_DEFAULT_BENCHMARKS)
```

DB37/T 2673-2019 医疗机构（二级，A区）：
| 指标 | 约束值 | 基准值 | 引导值 |
|------|--------|--------|--------|
| 单位面积非供暖能耗 | 22.6 | 15.3 | 9.4 |
| 常规用能系统面积电耗 | 73.1 | 53.0 | 34.9 |
| 人均综合能耗 | 907.4 | 556.9 | 428.3 |

DB37/T 4452-2021 用水定额：
| 二级医院 | 先进值 340 | 通用值 540 | L/(床·d) |
| 机关 | 先进值 10 | 通用值 25 | m³/(人·a) |

### 实现位置

`tools/energy_audit/indicators.py`
- `resolve_coefficient()` — 折标系数三级兜底
- `resolve_benchmark()` — 定额对标三级兜底
- `lookup_coefficient_from_db()` — Layer1 查询 ts_institution_energy_main
- `lookup_benchmark_from_db()` — Layer1 查询 ts_limit_config

---

## config JSON 结构（原 config-schema；仅 kanban 轨初始 config 使用）

### 文件名

`config_<项目简称>.json`

### 必填字段

```json
{
  "unit_name": "莘县县政府",
  "institution_category": "党政机关",
  "building_area": 4190,
  "people_count": 300,
  "audit_start": "2025年6月",
  "audit_end": "2025年7月"
}
```

### 完整模板

```json
{
  "unit_name": "", "unit_short": "",
  "address": "", "unit_type": "公共机构",
  "institution_category": "", "specific_type": "",
  "contact_person": "", "contact_phone": "",
  "auditor": "同方德诚（山东）科技股份公司",
  "report_date": "2026年6月", "province": "山东",
  "audit_start": "", "audit_end": "",
  "data_start": "2022-01-01", "data_end": "2024-12-31",
  "building_area": 0, "people_count": 0,

  "buildings": [
    {"name":"","year":0,"function":"","floors":"","area":0,
     "structure":"","insulation":"","window_type":""}
  ],

  "energy_yearly": [
    {"year":2022,"electricity_kwh":0,"water_m3":0,"natural_gas_m3":0,
     "heating_energy_heat_gj":0,"heating_cost_wan":0,
     "petrol_kg":0,"diesel_kg":0,
     "electricity_cost_wan":0,"water_cost_wan":0}
  ],

  "equipment": [
    {"name":"","category":"","spec":"","quantity":0,"remark":""}
  ],

  "metering": {
    "has_monitoring_system": false,
    "has_household_metering": false
  },

  "management": {},
  "images": [],
  "_note_images": "images 必须是纯路径字符串数组 List[str]（例: [\"E:/图片/建筑.jpg\"]），不可传 dict 对象。上限 5 张。"
}

### 校验

> ⚠️ 原 `config_validator.py` 已删除（当前代码无独立 config 校验模块）。
> 采集/构建入口（`data_collection_cli.py` / Hermes 工具）负责校验关键字段；
> 数据完整性检查见 `data_check.py::check_completeness`。

---

## 审计基本信息三张表的表结构（原 audit-info-tables，已归档；来源链路以 energy-audit-report-qa/references/fixes.md 为准）

位置：封面后、目录前。

### 能源审计机构信息表

4行 × 2列，键值对格式。第一列加粗居中。

| 项目 | 数据来源（权威链路，2026-09-03 用户确认） |
|------|----------|
| 机构名称 | ① `ts_project_dept.dept_name`（按 project_id 查，审计机构信息id表）；② 兜底：按 project 的 `audit_dept_name` 查 `ts_register_dept.dept_name`（**勿用 ts_register_info**；名称含"测试"字样时过滤，取同品牌"德诚"不含"测试"的最新记录） |
| 地址 | ① `ts_project_dept.address`；② 兜底：`ts_register_dept.address`（同上） |
| 负责人 | **仅** `ts_project_dept.contact`；无值则空，**不查其他表** |
| 联系方式 | **仅** `ts_project_dept.mobile`；无值则空，**不查其他表** |

### 能源审计组人员名单

N行 × 5列。表头行自动生成。数据源 `ts_project_audit_user`。

| 列 | 数据来源 |
|----|----------|
| 组内职务 | `position` |
| 姓名 | `name` |
| 学历 | `degree` |
| 所获资质 | `qualifications` |
| 专业 | `major` |

### 能源审计配合人员名单

N行 × 5列。表头行自动生成。数据源 `ts_project_audited_user`。

| 列 | 数据来源 |
|----|----------|
| 组内职务 | `group_position` |
| 部门 | `department` |
| 姓名 | `name` |
| 性别 | `sex` |
| 职务 | `position` |

### 生成方式

```python
（历史示例，正文生成已退役）gen.set_report_data({
    'audit_info_tables': {
        'institution': {'name': '...', 'address': '...', 'contact': '...', 'phone': '...'},
        'team_members': [{'role': '组长', 'name': '...', 'education': '...', 'certification': '...', 'major': '...'}, ...],
        'cooperation': [{'role': '...', 'dept': '...', 'name': '...', 'gender': '...', 'position': '...'}, ...],
    },
    ...
})
```

缺失字段标 `【待补充】`，不捏造数据。审计组/配合人员缺失时记 P1 问题，V3 审查与 report_qa 扫表格占位。

---

## ISO 日期转中文（原 iso-date-to-cn）

### 问题

Config中使用ISO格式日期 `"2022-01-01"` 直接写在Word中显示为 `2022-01-01`，不符合中文报告规范。需转为 `2022年1月1日`。

### 转换函数

```python
def _iso_to_cn(date_str: str) -> str:
    """2022-01-01 → 2022年1月1日"""
    if not date_str or '年' in date_str:
        return date_str  # 已是中文格式，跳过
    parts = date_str.split('-')
    if len(parts) >= 3:
        y, m, d = parts[0], str(int(parts[1])), str(int(parts[2]))
        return f"{y}年{m}月{d}日"
    return date_str
```

### 使用位置

- `load_from_project()`: `'audit_period': b.audit_period`、`'base_period': b.base_period`（项目表审计期/基准期，YYYY年M月—YYYY年M月）
- audit_start/end 同理（如果使用了ISO格式）

### Pitfall

- `int(parts[1])` 去掉前导零——`"01"→1→"1"` 而非 `"01"`
- 已含中文"年"的跳过（幂等性）
- 空字符串直接返回，不抛异常
