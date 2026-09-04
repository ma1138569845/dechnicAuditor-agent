---
name: ea-calculation
description: 能源审计指标计算与第5章生成能力（caliber 专属）。计算单位面积非供暖能耗/常规电耗/人均综合能耗/人均取水/单位采暖建筑面积供暖能耗 5 项指标、定额对标（DB37）、生成第5章 Markdown+图表时使用。折标系数优先用 data.json 中 EnergyYearly.coefficients 持久化值，缺失四级兜底（data.json→DB→用户→默认）；定额对标三级兜底（DB→用户→core/standards-values 默认）。
version: 1.3.0
---

# Indicator Calculation Skill

## Overview

该 Skill 提供能源审计流水线的指标计算与第5章生成能力，是数据验证（datava V1）后的计算工序。

流程位置：

```
datacollection 采集 → datava V1 验证
    ↓
caliber 指标计算 + 第5章生成（本 Skill）
    ↓
datava V2 INDICATOR_REVIEW 复核 → author装配报告
```

职责边界：本 Skill 只做**指标计算、定额对标、用能情况和用能规律的详细表述、第5章 Markdown + 图表**。不采集数据、不做数据验证、不生成其他章节、不修改原始项目数据。

---

## 核心参考文档

深度写作规范与细节沉淀在 `references/`（自 ea-calculation 并入）：

| 文件 | 内容 |
|------|------|
| `indicators-guide.md` | 5 项指标计算指南 + DB37 定额默认值（含验证示例：日照市人民医院） |
| `chapter5-writing-logic.md` | 第5章写作逻辑（四段式5.2/五要素5.3/三档评价规则/供暖电耗剔除·口径统一·交叉校验三铁律） |
| `chapter5-writing-guide.md` | 第5章生成逻辑（结构/各节规则/动态表号） |
| `chapter5-agent-guide.md` | 第5章 Agent 指南（5.1–5.4 + 图表函数） |
| `chapter5-52-spec.md` / `chapter5-52-final-spec.md` | 5.2 节规范与最终版 |
| `chapter5-52-writing-spec.md` | 5.2 写作规范（分节结构/趋势判断/±30% 异常标注） |
| `chapter5-52-writing-lessons.md` | 5.2 写作教训（踩坑记录，16KB 最详） |
| `chapter5-52-reference-style.md` | 5.2 参考样式 |
| `chapter5-53-templates.md` | 5.3 指标模板 |
| `chapter5-structured-tables.md` | 第5章结构化表格 |
| `energy-flow-diagram-spec.md` | 能流图规范（graphviz 动态，非 matplotlib） |
| `reports-vector-db.md` | 报告向量库 |

> 写作章节时以 `references/` 为权威细节源，SKILL.md 只给流程与公式骨架。

---

## Execution Workflow

```
1. 加载数据（data.json + validation.json）
   ↓
2. 构建 YearlyEnergyData（提取 building_area/people_count/beds_count）
   ↓
3. 计算 5 项核心指标（折标系数四级兜底：data.json → DB → 用户 → 默认）：
   单位面积非供暖能耗 / 常规电耗 / 人均综合能耗 / 人均取水 / **单位采暖建筑面积供暖能耗**（DB37/T 2672 表2 定额，有供暖能耗的项目必算）
   ↓
4. 定额对标 resolve_benchmark（三级兜底 + DB 查询规则）
   ↓
5. 生成第5章 Markdown + charts/*.png
   ↓
6. 持久化 indicators.json / chapter5.md / indicators_report.txt
```

### 供暖能耗指标（2026-09-02 新增，第 5 项）

- 公式：单位采暖建筑面积供暖能耗 kgce/(m²·a) = 供暖能耗 kgce ÷ 采暖建筑面积
- 供暖能耗 = 供暖电耗×0.31 + 供热量(GJ)×34.12 + 供暖燃气×1.2143（口径见 energy-audit-core/references/coefficient-caliber.md）
- 采暖建筑面积：建筑表 heat_area 合计，缺失/全 0 时用建筑面积兜底（用户 2026-09-02 确认）
- 定额（DB37/T 2672-2019 表2，按供暖类型，不分机构等级）：市政集中供暖(按热计量) 12.7/11.1/8.3；空调供暖 12.4/8.9/6.4；燃气(油)供暖 12.3/8.4/4.8
- 代码：tools/energy_audit/indicators.py::calc_unit_area_heating_energy；预计算值在 data.json indicators[].unit_area_heating
- 定额矩阵权威：energy-audit-core/references/standards-values.md（勿在本 skill 复制数值）

### CLI 调用

```bash
python <skill>/scripts/caliber_agent.py <项目名> [--skip-charts] [--output-dir <目录>]
```

环境变量 `HERMES_AGENT_HOME` 指定含 `tools/energy_audit` 的项目根（缺省按 `_paths.py` 三级降级自动解析）。

---

## Capability 1: 数据加载与 YearlyEnergyData 构建

```python
from tools.energy_audit.project_data import load_project
from tools.energy_audit.indicators import YearlyEnergyData

proj = load_project(unit_name)
# energy_yearly → YearlyEnergyData(year, electricity_kwh, water_m3,
#   natural_gas_m3, heating_energy_heat, heating_energy_kwh,
#   transportation_petrol_kg, transportation_diesel_kg,
#   building_area, people_count, coefficients)
#
# 注意：caliber 必须将 ey.coefficients 传入 YearlyEnergyData，
# 确保指标计算优先使用 data.json 中持久化的折标煤系数。
```

要点：

- `heating_energy_kwh` 需从 sub_items 拆分，缺失时默认为 0（即非供暖电耗 = 总电耗）
- 机构类型解析：`institution_category` → medical / government / education / venue / service_center

---

## Capability 2: 五项核心指标计算

| # | 指标 | 函数 | 说明 |
|---|------|------|------|
| 1 | 单位建筑面积非供暖能耗 | `calc_unit_area_non_heating_energy()` | (总电 − 供暖电) / 面积 |
| 2 | 常规用能系统单位建筑面积电耗 | `calc_unit_area_electricity()` | 电量总和/面积 |
| 3 | 人均综合能耗 | `calc_per_capita_energy()` | 用能人数 = 在岗 + 编外 + 门诊折算 + 床位折算 |
| 4 | 取水指标（医院=单位开放床日用水量 / 机关教育=人均取水量 / 场馆=单位建筑面积年取水量） | `calc_water_indicator(bed_count=N, building_area=A)` | 按机构类型分派口径；旧名 calc_per_capita_water 已弃用 |
| 5 | 单位采暖建筑面积供暖能耗 | `calc_unit_area_heating_energy()` | **有供暖能耗的项目必算**（2026-09-02 新增，DB37/T 2672 表2 定额，详见上节） |

另：`calc_baseline(yearly_data)` 计算 5.4 节建筑能耗基准（用量基准 + 费用基准，多年区间/趋势）。

### 关键公式

```
非供暖能耗:  Ejfgn = (总电 − 供暖电) × 折标煤系数/ 面积      kgce/(m²·a)
常规电耗:    Ed    = (总电 − 供暖电) / 面积             kWh/(m²·a)
人均能耗:    Er    = 综合能耗 × 1000 / 用能人数          kgce/(人·a)
床日用水量:  Vz    = 住院部用水 × 1000 / (床位 × 365)    L/(床·d)
人均取水量   Vuc   = 年机关取水量/机关人数                m3/（p·a）
```

---

## Capability 3: 折标系数四级兜底

指标计算优先使用 `EnergyYearly.coefficients` 中持久化的折标煤系数；缺失时调用 `resolve_coefficient(energy_type, user_value)`：

```
Layer 0: data.json 中 EnergyYearly.coefficients（由 DataCollection 从 PG 采集并持久化）
Layer 1: DB（ts_institution_energy_main.standard_coal_coefficient，合理性过滤）
Layer 2: 用户提供
Layer 3: 内置默认（DB37/T 2672-2019 附录B 山东口径，权威见 energy-audit-core/references/coefficient-caliber.md）
```

### 内置默认值与合理性范围（超出范围跳过 Layer 1）

| 能源 | 默认系数 (kgce/单位) | 合理性范围 |
|------|---------------------|-----------|
| 电 | 0.31 | 0.1 ~ 1.0 |
| 水 | —（不折标） | — |
| 天然气 | 1.2143 | 0.5 ~ 2.5 |
| 热 | 0.03412 | 0.01 ~ 0.05 |
| 汽油 | 1.4714 | 1.0 ~ 2.0 |
| 柴油 | 1.4571 | 1.0 ~ 2.0 |

---

## Capability 4: 定额对标（三级兜底 + DB 查询规则）

```python
resolve_benchmark(institution_type, metric, user_values, children_func, climate_type)
# → {约束值, 基准值, 引导值, 标准, 来源}
```

### 机构类型 → DB group_func 码

| 机构类型 | group_func |
|----------|-----------|
| 政务服务中心 service_center | A |
| 场馆 venue | B |
| 医疗 medical | C |
| 机关 government | D |
| 教育 education | E |

### 指标 → DB limit_type 码

| 指标 | limit_type |
|------|-----------|
| 单位建筑面积非供暖能耗 | A |
| 单位采暖建筑面积供暖能耗 | B |
| 人均综合能耗 | C |
| 常规用能系统单位建筑面积电耗 | D |
| 数据中心 PUE | E |
| 人均用水量 / 单位开放床日用水量 | F（床日靠 children_func 区分） |

### DB 查询规则

- **标准类型优先级：地方(3) > 国家(1) > 行业(4) > 国际(2)** — ORDER BY 按此取第一条，确保山东项目优先匹配 DB37/T 地标
- `children_func`（二级分类，如医院等级 A/B/C）与 `climate_type`（气候区域 A/B）按项目属性传入
- DB 返回标准名与机构类型不匹配时，忽略 DB 走 Layer 2/3

### 标准名透传

返回结果的 `标准` 字段（如 `DB37/T 2673-2019《医疗机构能源消耗定额标准》`）必须透传到 indicators.json，供第 1 章 1.6 节引用。

---

## Capability 5: 第5章生成 + 图表

```python
from tools.energy_audit.chapter5_agent import generate, generate_charts

md = generate(config, str(out_dir / 'chapter5.md'))
generate_charts(data, config, str(out_dir / 'charts'))
```

章节结构（细节见 `references/chapter5-writing-guide.md` 与 `chapter5-agent-guide.md`）：

- 5.1 能耗概况 + 能源流向图（**graphviz 动态**，`draw_energy_flow_diagram()`；非 matplotlib 饼图）
- 5.2 逐类型逐月数据分析（按用能类型**动态分节**，无数据不生成）+ 逐年柱状图 + 逐月趋势图
- 5.3 五项指标对标表（公式 + 动态表号 + DB37 对标；供暖能耗项按 DB37/T 2672 表2）
- 5.4 能耗基准（calc_baseline）

图表规范：能源流向图用 graphviz（系统需装 dot 二进制），其余 matplotlib SimHei 字体（中文无乱码），输出 PNG 到 `charts/`；目录不存在自动创建。

---

## Capability 6: 输出持久化

输出到 `~/projects/energy-audit/<单位名>/`（或 `--output-dir` 指定）：

| 文件 | 内容 |
|------|------|
| indicators.json | 5 项指标 + 定额对标（含标准名/来源）+ 能耗基准 |
| chapter5.md | 第5章完整 Markdown |
| indicators_report.txt | 可读指标报告 |
| charts/*.png | 能耗结构图 / 逐年柱状图 / 逐月趋势图 |

indicators.json 是下游契约：**DataVA V2 INDICATOR_REVIEW 复核它**，author装配报告时引用它。

---

## Output Template

```
════════════════════════════════════════════
📊 Caliber — 能耗指标计算结果
════════════════════════════════════════════
项目: 山东省立医院东院
年度: 2024 | 类型: medical
面积: 67,636 m² | 人数: 3,200

1. 单位建筑面积非供暖能耗: 21.5 kgce/(m²·a)
   对标: 低于基准值（合理水平）
   标准: DB37/T 2673-2019《医疗机构能源消耗定额标准》 | 来源: DB
2. 常规用能系统单位面积电耗: 69.4 kWh/(m²·a)
3. 人均综合能耗: 1,435 kgce/(人·a)
4. 取水指标: 486 L/(床·d)（医院床日口径）
5. 单位采暖建筑面积供暖能耗: 8.2 kgce/(m²·a)（有供暖项目）
6. 建筑能耗基准 (2022、2023、2024年): ...
```

---

## Error Handling

- **数据不存在**：`load_project` 返回 None → 报错退出（exit 1），提示先运行 DataCollection
- **无年度能耗数据**：标记 `⚠️无数据`，不崩溃
- **DB 连接超时**：折标系数/定额自动降级到 Layer 2/3，不中断计算
- **图表生成失败**：警告并继续，chapter5.md 与 indicators.json 照常产出
- **月度数据缺失**：逐月图表跳过，不报错

---

## Pitfalls

- **供暖电与非供暖电分离** — 依赖 `heating_energy_kwh`，缺失时假设为 0（非供暖指标会被高估，DataVA V2 会标 `HEATING_NOT_SPLIT`）
- **医院用水用 bed_count** — 算床日用水量，不用人均；缺床位数时降级人均取水量
- **定额来源标注** — Default/User 来源的定额在报告中必须注明（DataVA V2 记 `SOURCE_FALLBACK` P2）
- **用水定额字段语义** — 内置默认表用水三元组为（先进值, 通用值, 0)，与能耗（约束/基准/引导）口径不同，报告表述按先进值/通用值
- **5.2 分节** — 按用能类型动态 H3，只有有数据的类型才生成；5.2/5.3/5.4 共用动态表号，不可硬编码表号
- **5.1 极简** — 只有一句话概述 + 能源流向图，不要饼图/趋势柱状图/能源结构表（已移除）
- **graphviz 依赖** — 系统需安装 graphviz 二进制（pip 包只是 wrapper），否则流向图失败
- **占比计算** — `type_tce` key 是英文，用中文 `row[0]` 去 `.get()` 会返回 0 导致占比崩
- **charts/ 目录** — 不存在时自动创建

---

## Rules Summary

必须：

- ✅ 折标系数严格遵循四级兜底（data.json 持久化值 → DB → 用户 → 内置默认）
- ✅ 非供暖能耗固定等效电系数 0.31
- ✅ 标准名透传到 indicators.json（供 1.6 节引用）
- ✅ 数据缺失标注【待补充】，不编造
- ✅ 第5章写作遵循 `references/chapter5-writing-guide.md` 的分节/表号/趋势判断规则

禁止：

- ❌ 采集数据 / 数据验证 / 生成其他章节
- ❌ 修改原始项目数据
- ❌ 绕过三级兜底直接硬编码系数或定额
- ❌ 使用与机构类型不匹配的定额标准

---

## 关键数据库表

- `ts_institution_energy_main` + `ts_institution_energy_data`: data_type=1能耗/2费用/3供冷/4供热/5交通，关联键 customer_id；明细按 period_code 展开（granularity: 1=月/2=双月/3=季度/4=半年）
- `ts_institution_project`: institution_project_id → customer_id
- `ts_institution_build`: 关联键 project_id（非 customer_id），数据经常缺失

---

## 职责

| 职责 | 说明 | 依赖工具 |
| ---- | ---- | ---- |
| 📥 数据加载 | 从 data.json 或 PG 加载能耗数据 | `project_data.py` / `pg_query.py` |
| 🧮 指标计算 | 5项核心指标 + 三级兜底系数/定额 | `indicators.py` |
| 📊 定额对标 | DB37/T 2673-2019（医疗）/ DB37/T 2672-2019（机关） | `indicators.py` → `resolve_benchmark` |
| 📝 第5章生成 | 完整Markdown (5.1~5.4 含表格图表) | `chapter5_agent.py` |
| 📈 图表生成 | 能源流向图（graphviz）+ 逐年/逐月趋势（matplotlib） | `energy_flow_chart.py` / `matplotlib` |
| 📋 基准计算 | 5.4 节用量基准+费用基准 | `indicators.py` → `calc_baseline` |
