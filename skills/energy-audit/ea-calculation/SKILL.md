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
| `chapter5-spec.md` | ★第5章【结构与细节权威】：结构规范（原 5.2 final-spec）+ 写作逻辑与计算三铁律（原 writing-logic）+ 5.2 踩坑细节（原 writing-lessons）+ 结构化表格 |
| `chapter5-templates.md` | ★第5章【模板与生成逻辑】：5.3 指标模板（5.3.1 权威）+ 第5章生成逻辑 + Agent 指南 + 图表函数 |
| `ea-calculation-support.md` | 辅助说明：能源流向图规范（graphviz）+ KG 可视化与置信度反馈 + 报告参考库与 RAG 检索 |
| ~~其余 8 个 5.x 文件~~ | 已于 2026-09-18 瘦身合并（第 1 组）：4+3+3 个文件合并为上述 3 个；`indicators-guide.md` 内容已被 `standards-values.md` 与本 SKILL 覆盖 → 全部归档至 `_archive/2026-09-18/ea-calculation/references/` |

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
# 计算完成后，把第5章"就位"为装配稿（消灭手工搬运断点；不覆盖作者已并入的装配稿）
python <skill>/scripts/prepare_chapter_md.py <项目名> [--force]
# 定额取值溯源自检（标准号 + 表号锚点；exit 1 = 有缺项 → 第5章标【待核验】）
python <skill>/scripts/verify_benchmark_sources.py <项目名>
```

`prepare_chapter_md.py` 退出码：`0` 已就位/已有更新装配稿 · `1` 缺 `chapter5.md`（先跑 caliber）· `2` 装配稿早于计算产物（人工确认后 `--force`）。

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

## Capability 4: 定额对标（取值链 = 用户值 > 内置默认；DB 仅交叉校验）

> ★2026-09-20 口径变更（用户确认"以 Layer 3 内置默认为准"）：**DB `ts_limit_config` 退出取值链**。
> 取值只来自两处，DB 改由 `audit_db_benchmark()` 旁路比对、不一致只打 warning（提示平台修数据），
> **不影响报告取值**。好处：已交付项目重跑时定额值不会因"接通 DB"而变，可做逐值回归断言。

```python
resolve_benchmark(institution_type, metric, user_values=None, sub_type=None, db_audit=True)
# → {约束值, 基准值, 引导值, 标准, 来源}；给了 sub_type 时额外带 '分档'
# 来源 ∈ {User, Default}（不再出现 'DB'）
```

### sub_type：二级维度查询串（`'·'` 分隔，**可只给一部分**，子集匹配）

| 机构 | 表1/表3/表4（+用水） | 表2（供暖能耗） |
|---|---|---|
| 医疗 medical | `'二级·A'`（等级 · 气候区） | `'二级·空调供暖'` |
| 党政 government | `'市级以下·A'`（等级 · 气候区） | `'市级以下·市政集中供暖（按热计量）'` |
| 教育 education | `'本科及以上'`（8 分档，不分气候区） | `'本科及以上·燃气（油）供暖'` |
| 场馆 venue | `'博物馆·市级'`（场馆类型 · 省/市/区县档） | `'博物馆·空调供暖'` |
| 政务 service | `'市级以下'` | — |

> 场馆**取水指标**另有一维：`'图书馆'` / `'博物馆'`（4452 面积口径定额，2026-09-20 启用）；
> 剧院/体育馆/科技馆在 4452 中无定额 → 不对标。该维度**不设默认键**，避免"无定额的场馆套用图书馆定额"。

拼装由 `indicators.project_sub_type(base, institution_type, metric)` 完成——它读
`base.unit_func` / `base.children_func`（平台字典码，见 `dept_dict.py`）＋ 内置气候区表
（`climate_zone.py`）。**调用方只需把 base 传进去**，不要自己拼字符串。

### 维度取值来源（唯一权威）

| 维度 | 来源 | 说明 |
|---|---|---|
| 一级单位类型（机构族） | `ts_customer_info.customer_func`（字典 `client_dept_type`） | 缺值才回退单位名分类器 |
| 二级分档/等级/场馆类型 | `ts_customer_info.children_func`（字典 `client_dept_type_<一级码>`） | 教育 8 档、医疗一~三级、党政省~市级以下、场馆 5 类 |
| 气候区（医疗/党政） | **内置表** `climate_zone.py`（DB37/5026-2022 表3.0.1） | **不取** DB `climate_type`；地市优先按 `district_id` 行政区划码判 |
| 供暖类型（表2） | 项目供暖方式；缺省"市政集中供暖（按热计量）" | 标准注1：按面积收费的市政供暖、燃煤自供暖均按此口径 |
| 场馆省市档 | 单位名推断，缺省"市级" | 待补：纳入项目数据后可直接读 |

### DB 交叉校验规则

- 按真实维度查 `ts_limit_config`：`field_type`(恒 10) × `group_func`(一级码) × `limit_type`(表号
  A表1/B表2/C表3/D表4/E表5/F用水) × `children_func`(二级码) × `climate_type` × `heat_type` × `area_code`
- 与内置默认不一致 → `logger.warning`（**不取值**），文案含 DB 值与内置值，提示"以 standards-values.md 为准"
- DB 不可用（离线/无权限）只记 debug，绝不阻断计算

### 内置默认的守门人

内置默认 = `energy-audit-core/references/standards-values.md` 的代码镜像。
**改任何一侧都必须跑**`ea-calculation/scripts/verify_default_benchmarks.py`
（逐值比对代码表与权威文件，退出码 0 = 一致），否则两边会漂移。

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

脚本只渲染数据驱动的概括句/表格/图表（数字最密集章零差错）；**分析性叙述**（逐月趋势归因、评价结论、同比解读）由 author 按 `references/chapter5-templates.md` 撰写后装配。

章节结构（细节见 `references/chapter5-templates.md` 与 `references/chapter5-spec.md`）：

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

### 第5章产物权威说明（2026-09-17 定）

| 文件 | 定位 | 处置 |
|---|---|---|
| `<项目>/chapter5.md` | **计算产物（权威数据源）** | 只读；由 caliber 生成，作者与脚本都不得改写数值 |
| `<项目>/chapter_md/ch5_import.md` | **装配唯一输入** | 由 `prepare_chapter_md.py` 就位；作者可并入分析性叙述段，但数值必须与 chapter5.md 一致 |
| `<项目>/chapter_md/ch5.md`、`ch5_segA/B/C.md` | 中间物（历史分段/合并稿） | 可删；不作为装配输入，也不作为数值来源 |

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
   对标: 低于基准值
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
- ✅ 第5章写作遵循 `references/chapter5-spec.md`（结构/表号/细节）与 `references/chapter5-templates.md`（模板/生成逻辑）

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
