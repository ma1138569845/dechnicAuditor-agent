# 第5章 结构化表格渲染（chapter5_agent 渲染 + author 装配）

## 现状（2026-09-05 定）

第5章 = 脚本渲染数据驱动的表格/图表引用 + author LLM 写叙述段（混合模式）。
`chapter5_agent.py` 渲染 5.1~5.4 的表格/数据参考行 + 图表引用（数值零差错）；分析性叙述由 author 按 `chapter5-writing-guide.md` 撰写后装配。

生产路径：`caliber_agent.py` 读 data.json → config（manual dict）→ `generate_chapter5_md`。
备用路径：`load_from_db`（仅 --db 模式，读 PG）。

## 生成的表格与图表（当前口径）

### 5.1 概况（极简）

| 序号 | 内容 | 说明 |
|------|------|------|
| 概述 | 一句话概述 | 各能源品种用途一句话带过，**非**"主要用能类型包括XX"展开 |
| 图5.1 | 能源流向图 | graphviz 自动生成，三层结构：能源输入(圆角矩形)→用能系统→终端。实线=主能源流，虚线=辅助 |

5.1 不列综合能耗数值（综合能耗只在 5.3.3 给出）；无饼图、无趋势柱状图、无能源结构表（已移除）。

### 5.2 各节图表（图号 5.2 起动态连号）

- 各能源类型 H3：总量柱状图（主要能源无条件画）→ 逐月分组柱状图（仅该类型有月度数据才画）
- 费用节（最后一节，仅当至少一项费用 > 0 且 ≥1 年有数据才生成）：
  - 表5.1 各项能源费用统计表：年份行 ×（电费/供暖费/水费/油费/燃气费/合计）列，单位元（万元×10000）；
    油费=汽油费+柴油费合并；任一年 >0 的列才显示（无 0 值列）；热费名=供暖费、天然气费名=燃气费
  - 每年一张费用占比饼图（cost_pie_{year}.png），动态连号
- 5.2 能源类型小节**不编号表**（数据参考行，author 转文字）

### 5.3 五项指标表（表5.2~表5.6，固定表号）

| 表号 | 内容 | 说明 |
|------|------|------|
| 表5.2 | 单位建筑面积非供暖能耗 | 转置：首列指标项，其后每个统计年份一列 |
| 表5.3 | 常规用能系统单位建筑面积电耗 | 同上 |
| 表5.4 | 人均综合能耗 | 同上 |
| 表5.5 | 取水指标 | 标题按机构类型自适应（医院=单位开放床日用水量/机关教育=人均取水量/场馆·政务=单位建筑面积年取水量）；对标为通用值/先进值 |
| 表5.6 | 单位采暖建筑面积供暖能耗 | 有供暖能耗才生成 |

指标表为**行列转换（转置）样式**：首列为指标项行（基础数据行 + 指标值行 + 对标值行 + 评价行），
其后每个统计年份一列（2022年/2023年/2024年）；对标值行三年相同仍逐年填充。

### 5.4 基准表（表5.7~表5.8，顺延固定）

| 表号 | 内容 |
|------|------|
| 表5.7 | 能源资源用量基准（法院口径） |
| 表5.8 | 能源资源费用基准（法院口径） |

## 对标机制

调用 `indicators.py` 的 `resolve_benchmark(institution_type, metric)`，三级兜底：
- Layer 1: DB（ts_limit_config 系列表）
- Layer 2: 用户提供
- Layer 3: 内置 DB37/T 默认值（权威矩阵见 energy-audit-core/references/standards-values.md）

## 与 chapter5_agent.py 的关系

`chapter5_agent.py` 是第5章表格/图表的唯一渲染器，author 不重复造表。

## 输入格式（直调 generate_chapter5_md 时）

```python
report_data['chapter5'] = {
    'energy_data': [
        {
            'year': 2022,
            'electricity_kwh': 495180,
            'water_m3': 3980,
            'natural_gas_m3': 3000,
            'heating_energy_heat_gj': 0,     # 供暖热量(GJ)，可选
            'petrol_kg': 0,                    # 汽油，可选
            'diesel_kg': 0,                    # 柴油，可选
            'electricity_cost_wan': 34.04,     # 电费(万元)，可选
            'water_cost_wan': 1.17,            # 水费(万元)，可选
            'heating_cost_wan': 13.70,         # 供暖费(万元)，可选
        },
        # ... 每年一条
    ],
    'unit_name': '莘县政府',                    # 使用简称
    'building_area': 4190,                      # fallback from chapter2
    'people_count': 300,                        # fallback from chapter2
    'institution_type': 'government',           # medical/government/education/venue/service
}
```
