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
| `chapter5-writing-guide.md` | 第5章生成逻辑（结构/各节规则/图号表号） |
| `chapter5-agent-guide.md` | 第5章 Agent 指南（5.1–5.4 + 图表函数） |
| `chapter5-52-final-spec.md` | ★5.2 节规范【结构权威单点】（2026-09-05 定） |
| `chapter5-52-writing-lessons.md` | ★5.2 写作教训【细节权威单点】（踩坑记录，16KB 最详） |
| `chapter5-52-spec.md` | ⚠️已废弃（v3.4，并入 final-spec） |
| `chapter5-52-writing-spec.md` | ⚠️已废弃（并入 writing-lessons） |
| `chapter5-52-reference-style.md` | ⚠️已废弃（参考样式，图号/费用节为旧口径） |
| `chapter5-53-templates.md` | 5.3 指标模板（5.3.1 模板唯一权威） |
| `chapter5-structured-tables.md` | 第5章结构化表格 |
| `energy-flow-diagram-spec.md` | 能流图规范（graphviz 动态，非 matplotlib） |
| `reports-vector-db.md` | 报告向量库 |

> 写作章节时以 `references/` 为权威细节源，SKILL.md 只给流程与公式骨架。

---

## Execution Workflow

```
1. 加载数据（data.json + validation.json）
   ↓
2. 构建 YearlyEnergyData（提取 building_area/people_count；bed_count 由 calc_water_indicator 另行传参，YearlyEnergyData 无此字段）
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
- 采暖建筑面积（2026-09-05 定，三级兜底）：①caliber 从建筑表 heat_area 聚合 → config.heating_area → data 顶层；②缺失/全 0 → generate_chapter5_md 用建筑总面积兜底；③直调 generate_chapter5_md 且 data 无顶层 heating_area 时用 data['buildings'] 聚合级（生产路径 data 无 buildings 键，实际不经过）
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

- 供暖电耗：从 `EnergyYearly.heating_energy_kwh` 读取，经 caliber 组装的 `config.heating_energy_kwh_map`（逐年 dict，data 顶层）传入；`sub_items` 为 dt=3 供冷等分项的历史容器，生产路径传空 `{}`，**不得**从 sub_items 找供暖电耗。缺失时供暖电耗=0（即非供暖电耗=总电耗，DataVA V2 会标 HEATING_NOT_SPLIT）
- 机构类型解析：`institution_category` → medical / government / education / venue / service（2026-09-05 默认 medical=医院泛化基线）

---

## Capability 2: 五项核心指标计算

| # | 指标 | 函数 | 说明 |
|---|------|------|------|
| 1 | 单位建筑面积非供暖能耗 | `calc_unit_area_non_heating_energy()` | Ejrcn=(综合−供暖−交通)/面积，全口径 |
| 2 | 常规用能系统单位建筑面积电耗 | `calc_unit_area_electricity()` | (总电−供暖电)/面积 |
| 3 | 人均综合能耗 | `calc_per_capita_energy()` | 用能人数 = 在岗 + 编外 + 门诊折算 + 床位折算 |
| 4 | 取水指标（医院=单位开放床日用水量 / 机关教育=人均取水量 / 场馆·政务=单位建筑面积年取水量） | `calc_water_indicator(data, institution_type, user_benchmark, bed_count, building_area)` | 按机构类型分派口径；旧名 calc_per_capita_water 已弃用；医院缺 bed_count 返回 error 占位（不降级人均） |
| 5 | 单位采暖建筑面积供暖能耗 | `calc_unit_area_heating_energy()` | **有供暖能耗的项目必算**（2026-09-02 新增，DB37/T 2672 表2 定额，详见上节） |

另：`calc_baseline(yearly_data)` 计算 5.4 节建筑能耗基准（用量基准 + 费用基准，多年区间/趋势）。

### 关键公式

```
非供暖能耗:  Ejrcn = (E − Egn − Ejt) / M                  kgce/(m²·a)（E综合、Egn供暖、Ejt交通）
常规电耗:    Eja   = (总电 − 供暖电) / 面积             kWh/(m²·a)
人均能耗:    Er    = 综合能耗 × 1000 / 用能人数          kgce/(人·a)
取水指标（DB37/T 4452-2021，按机构类型）:
  机关:      Vuc   = 年机关取水量 / 机关人数              m³/(人·a)（式7）
  高校:      Vu    = 年用水量 / 标准人数 Nu               m³/(人·a)（式3；Nu=统招生+留学生+0.5×教职工）
  中小学/幼儿园: Vs = 年用水量 / 标准人数 Ns              m³/(人·a)（式4；Ns=非住宿生+2×住宿生+教职工）
  医院:      Vz    = 住院部年用水 × 10³ / Σ实际开放床日    L/(床·日)（式5；ΣNi 缺失时按 床位×365 近似）
  政务/场馆: Vui   = 年取水量 × 1000 / 建筑面积           L/(m²·a)（式6）
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

| 能源 | 默认系数 (kgce/单位) | 合理性范围（超出跳过 Layer 1，防 DB 旧错值） |
|------|---------------------|-----------|
| 电 | 0.31 | 0.2 ~ 0.5（0.1229 当量旧值拒收） |
| 水 | —（不折标） | — |
| 天然气 | 1.2143 | 1.15 ~ 1.30（1.33 当量旧错值拒收） |
| 热 | 0.03412 | 0.01 ~ 0.05 |
| 汽油 | 1.4714 | 1.0 ~ 2.0 |
| 柴油 | 1.4571 | 1.0 ~ 2.0 |

---

## Capability 4: 定额对标（三级兜底 + DB 查询规则）

```python
resolve_benchmark(institution_type, metric, user_values, children_func, climate_type)
# → {约束值, 基准值, 引导值, 标准, 来源}
```

### 机构类型 → DB field_types 码（代码实际，`indicators.py::_STANDARD_SCOPE` 附近）

| 机构类型 | field_types 值 |
|----------|---------------|
| 机关 government | 10 |
| 医疗 medical | 20 |
| 教育 education | 30 |
| 政务/场馆 | 无专用码，走 Layer 2/3 兜底（政务用机关定额、场馆用其默认定额） |

### 指标 → DB 查询维度（代码实际）

DB 查询按「机构类型 field_types 码 × 标准表 std_category」过滤，取 ORDER BY 最新一条；
不设 limit_type 编码体系。医疗 children_func 传医院等级（A/B/C）、climate_type 传气候区域。

### DB 查询规则

- DB 返回标准名与机构类型不匹配时，忽略 DB 走 Layer 2/3
- `children_func`（二级分类，如医院等级 A/B/C）与 `climate_type`（气候区域 A/B）按项目属性传入
- 取不到/不匹配 → Layer 2 用户值 → Layer 3 内置默认

### 标准名透传

返回结果的 `标准` 字段（如 `DB37/T 2673-2019《医疗机构能源消耗定额标准》`）必须透传到 indicators.json，供第 1 章 1.6 节引用。

---

## Capability 5: 第5章数据渲染 + 图表（混合模式，2026-09-04 定）

**第5章 = 脚本渲染表格/图表 + author LLM 写叙述段**：

```python
from tools.energy_audit.chapter5_agent import generate, generate_charts

md = generate(config, str(out_dir / 'chapter5.md'))   # 输出 5.1~5.4 的表格/数据参考行 + 图表引用（数值零差错）
generate_charts(data, config, str(out_dir / 'charts'))
```

脚本只渲染数据驱动的概括句/表格/图表（数字最密集章零差错）；**分析性叙述**（逐月趋势归因、评价结论、同比解读）由 author 按 chapter5-writing-guide.md 撰写后装配。

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
| charts/*.png | 能源流向图 / 总量柱状图 / 逐月分组柱状图 / 费用饼图 |

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

1. 单位建筑面积非供暖能耗: 21.50 kgce/(m²·a)（2 位小数）
   对标: 低于基准值（合理水平）
   标准: DB37/T 2673-2019《医疗机构能源消耗定额标准》 | 来源: DB
2. 常规用能系统单位面积电耗: 69.40 kWh/(m²·a)
3. 人均综合能耗: 1435.00 kgce/(人·a)
4. 取水指标: 486.00 L/(床·d)（医院床日口径；缺床位 → 【待补充】占位）
5. 单位采暖建筑面积供暖能耗: 8.20 kgce/(m²·a)（有供暖项目）
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
- **医院用水用 bed_count** — 算床日用水量，不用人均；缺 bed_count 返回 error 占位（【待补充】标注，不降级人均取水量，防与 md 层/正式报告打架）
- **定额来源标注** — Default/User 来源的定额在报告中必须注明（DataVA V2 记 `SOURCE_FALLBACK` P2）
- **用水定额字段语义** — 内置默认表用水三元组为（通用值, 先进值, 0)，与能耗（约束/基准/引导）口径不同，报告表述按通用值/先进值
- **5.2 分节** — 按用能类型动态 H3，只有有数据的类型才生成；表号固定：表5.1 费用统计表 / 5.2 无表 / 5.3 从表5.2 起，图号 5.1 起动态连号
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

> ⚠️ 备用路径（load_from_db，仅 --db 模式）；生产路径为 caliber_agent.py 读 data.json。dt 旧分类（1=能耗/2=费用/3=供冷/4=供热/5=交通）为历史代码口径，生产数据不在其中。

- `ts_institution_energy_main` + `ts_institution_energy_data`: 关联键 customer_id；明细按 period_code 展开（granularity: 1=月/2=双月/3=季度/4=半年）
- `ts_institution_project`: institution_project_id → customer_id
- `ts_institution_build`: 关联键 project_id（非 customer_id），数据经常缺失

---

## 职责

| 职责 | 说明 | 依赖工具 |
| ---- | ---- | ---- |
| 📥 数据加载 | 从 data.json 或 PG 加载能耗数据 | `project_data.py` / `pg_query.py` |
| 🧮 指标计算 | 5项核心指标 + 三级兜底系数/定额 | `indicators.py` |
| 📊 定额对标 | DB37/T 2673-2019（医疗）/ DB37/T 2672-2019（机关） | `indicators.py` → `resolve_benchmark` |
| 📝 第5章渲染 | 5.1~5.4 表格+图表引用 Markdown（叙述段由 author 写） | `chapter5_agent.py` |
| 📈 图表生成 | 能源流向图（graphviz）+ 逐年/逐月趋势（matplotlib） | `energy_flow_chart.py` / `matplotlib` |
| 📋 基准计算 | 5.4 节用量基准+费用基准 | `indicators.py` → `calc_baseline` |
