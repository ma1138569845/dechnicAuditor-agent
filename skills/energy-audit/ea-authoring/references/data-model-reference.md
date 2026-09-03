# load_project 返回格式与字段速查

## 返回格式（必读）

```python
from tools.energy_audit.project_data import load_project, list_projects

proj = load_project(unit_name)   # → AuditProject dataclass；找不到返回 None
if proj is None:
    # 项目不存在，用 list_projects() 列出可用项目名，交用户确认，禁止编造
    raise SystemExit(f"未找到项目，可用：{[p['name'] for p in list_projects()]}")
```

**访问规则（写正文前必须记住）：**

1. `load_project` 返回**嵌套 dataclass**，一律用 `.` 属性访问，**不是 dict**：
   - ✅ `proj.base.unit_name`
   - ❌ `proj['base']['unit_name']`（会 TypeError）
2. 以下字段是**列表**，多栋建筑/多年数据要遍历或按索引取：
   `buildings` / `energy_yearly` / `energy_monthly` / `equipment` / `energy_saving` / `images` / `shared_offices`
3. `indicators` 和 `data_sources` 是 **dict**，用 `proj.indicators.get(...)` 或 `proj.indicators['...']`。
4. `energy_saving` 通常取最新一条：
   `es = max((e for e in proj.energy_saving if e), key=lambda e: e.statistical_year or 0, default=None)`
5. 空值：字段为 `""`/`0`/`None`/空列表时，正文写「数据缺失」或跳过该句，禁止编造。

## 章节 → 字段映射

| 章节/段落 | 需要表述的「审计数据」 | 取值表达式 |
|---|---|---|
| 1.1 审计目的 | 省份 / 审计单位 / 被审计单位 | `proj.base.province` / `proj.base.auditor` / `proj.base.unit_name` |
| 1.2 审计范围 | 地址 / 建筑列表 | `proj.base.address` / `proj.buildings` |
| 1.2 工作范围 | 数据起止年 | `proj.base.data_start` / `proj.base.data_end` |
| 1.3 审计周期 | 审计时间=`proj.base.audit_start`（create_time）/`audit_end`（生成时间）；审计期=`proj.base.audit_period`（audit_year）；基准期=`proj.base.base_period`（reference_year） |
| 1.5 审计过程 | 单位简称 | `proj.base.unit_short` |
| 2.1 基本情况 | 全称/简称/行政归属/地址/内设机构/人数/建筑面积 | `proj.base.unit_name` / `unit_short` / `admin_affiliation` / `address` / `department_count` / `people_count` / `building_area`；整段概述可直接用 `proj.base.basic_situation` |
| 2.2 建筑物概况 | 每栋建筑全部参数 | 遍历 `proj.buildings`，字段见 `BuildingInfo`（完整清单见 `chapter2-guide.md` §7） |
| 2.3 用能系统 | 设备名称/数量/能源类型 | `proj.equipment[]`（name/category/quantity），能源类型由 `proj.energy_yearly[]` 各能耗字段是否 >0 判定 |
| 3.1 机构职责 | 管理机构职责正文 | **优先** `proj.management.management_org`（采集阶段已由制度文件 LLM 提炼）；为空则按 `proj.base.institution_category` 选模板 |
| 3.2 目标方针 | 目标/方针正文 | **优先** `proj.management.management_policy` / `proj.management.management_goals`；为空则**仿写同类报告 3.2**（run_imitate），仿写不可用再走通用兜底句 |
| 3.3 成效问题 | 荣誉/痛点 | `proj.management.honors` / `proj.energy_saving[].has_awards` / `award_name` / `energy_pain_points` |
| 第4章 表数/监测 | 电/水/气/热表数量、监测系统、分户、独立计量电表 | `proj.metering.electric_meters` / `water_meters` / `gas_meters` / `heat_meters` / `has_monitoring_system` / `has_household_metering` / `has_household_payment` / `has_separate_metering` |
| 第4章 分类独立计量 | 场景表：空调用电/照明插座/特殊用电/动力/施工用水电 | `proj.metering.independent_aircon` / `independent_light_socket` / `independent_special` / `independent_power` / `independent_construction_elec` / `independent_construction_water` / `independent_other_special` |
| 第4章 设备独立计量 | 单台是否单独计量 | 遍历 `proj.equipment[]`：`eq.independent_metering`（`"有"` / `"无"` / `""`）/ `eq.independent_metering_desc` / `eq.independent_metering_ratio` / `eq.independent_metering_time`；`""` 表示该表无此列或未填，**不得当成「无」** |
| 第4章 合署办公 | 是否合署、各合署单位及是否独立计量 | `proj.metering.has_shared_office`（现场表 `mode`，1是/2否）。**否不写合署句**；**是不回显「合署办公：是」**，改用 `shared_office_metering_sentence`：列表有一个独立计量为是 →「有合署办公且实现了合办公单位独立计量」；全部否 →「有合署办公，但未实现各办公单位独立计量」。明细：`proj.shared_offices[]` |
| 第5章 能耗 | 逐年/逐月能耗、指标 | `proj.energy_yearly[]`（electricity_kwh/water_m3/...）、`proj.energy_monthly[]`、`proj.indicators`（预计算指标） |
| 第6章 设备 | 分系统设备 | `proj.equipment[]`（category/name/spec/quantity/energy_rating/location/independent_metering） |
| 第6章 室内环境 | 检测数据 | `proj.indoor_env.rooms[]` |
| 第7章 问题 | 从实际字段推断 | 基于 `proj.metering` / `proj.equipment` / `proj.buildings` 推断，禁止写通用问题 |

## 写段落时的表述模板

在 chapter 指南的每个小节末尾，统一用「取值」标注填充来源，例如：

> 2.1 基本情况：全称取 `proj.base.unit_name`，简称取 `proj.base.unit_short`，
> 建筑面积取 `proj.base.building_area` m²，用能人数取 `proj.base.people_count` 人。

这样作者 Agent 看到的不是模糊的「xxx 审计数据」，而是精确到字段的取值路径。

## 顶层 dataclass 结构

```
AuditProject
├─ project_id / created_at / updated_at / _version
├─ base: ProjectBase                 # 单位基本信息
├─ buildings: List[BuildingInfo]     # 建筑列表
├─ energy_yearly: List[EnergyYearly] # 年度能耗列表
├─ energy_monthly: List[EnergyMonthly]
├─ equipment: List[Equipment]        # 设备列表
├─ metering: MeteringInfo            # 计量器具
├─ management: ManagementInfo        # 能源管理（第3章，含 LLM 提炼结果）
├─ energy_saving: List[EnergySaving] # 节能管理信息（按统计年）
├─ indoor_env: IndoorEnv
├─ images: List[str]                 # 图片路径列表
├─ data_sources: Dict[str,str]       # 字段→来源追溯
└─ indicators: Dict[str,Any]         # 预计算能耗指标
```