# 第5章 结构化表格渲染（chapter5_agent 渲染 + author 装配）

## 改造原因

历史（v1.7.0 前）：第5章只有纯文字，没有独立的指标表、对标表、基准表，与正式审计报告格式严重不符。

现行（2026-09-04 定）：`chapter5_agent.py` 直接从结构化数据渲染完整章节表格（总述+5.1概况+5.3五项指标（含供暖）+5.4基准），全部以 Markdown 表格方式输出，author 装配进 docx 时按 office_editor 转 Word 表格。

## 输入格式

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
            'heating_cost_wan': 13.70,         # 热费(万元)，可选
        },
        # ... 每年一条
    ],
    'unit_name': '莘县政府',                    # 使用简称
    'building_area': 4190,                      # fallback from chapter2
    'people_count': 300,                        # fallback from chapter2
    'institution_type': 'government',           # medical/government/education
}
```

## 生成的表格与图表（v2.8）

### 5.1 完整内容
| 序号 | 内容 | 说明 |
|------|------|------|
| 概述 | LLM自然文本 | 描述各能源品种用途、流向、系统归属。**非**简单"主要用能类型包括XX" |
| 图5.1 | 能源流向图 | `energy_flow_chart.py` 自动生成，三层结构：能源输入(圆角矩形)→用能系统→终端。实线=主能源流，虚线=辅助 |
| 表5.1 | 能源消费结构表 | 6列含**占比**。Bug修复：用 `type_tce[et]` 非 `type_tce.get(row[0])`（中文名≠英文key） |
| 图5.2 | 饼图 | 能源消费结构可视化 |
| 图5.3 | 逐年趋势 | 条形图 |

### 所有表格

| 表号 | 内容 | 列数 | 行数 |
|------|------|------|------|
| 表5.1 | 各项能源费用统计表（5.2 费用节，费用类型×年份） | 2~7 | 4 |
| 表5.2 | 单位建筑面积非供暖能耗（转置） | 4 | 9 |
| 表5.3 | 常规用能系统单位建筑面积电耗（转置） | 4 | 7 |
| 表5.4 | 人均综合能耗（转置） | 4 | 7 |
| 表5.5 | 取水指标（转置；标题按机构类型自适应，对标为通用值/先进值） | 4 | 6 |
| 表5.6 | 单位采暖建筑面积供暖能耗（转置；有供暖能耗才生成） | 4 | 7 |

指标表（表5.2~表5.6）为**行列转换（转置）样式**：首列为指标项（基础数据行 + 指标值行 + 对标值行 + 评价行），
其后每个统计年份一列（2022年/2023年/2024年）；对标值行三年相同仍逐年填充。
行数 = 指标项行数（含表头不计），列数 = 项目列 + 年份数（3年 → 4列）。
> 表5.1 之前无表：5.2 能源类型小节不编号表（数据参考行，author 转文字），
> 能源消费结构/逐年能耗对比为写作参考表（不占正式表号）。
| 表5.7 | 能源资源用量基准（顺延；法院口径） | 4 | 2~4 |
| 表5.8 | 能源资源费用基准（顺延；法院口径） | 3 | 2~4 |

## 对标机制

调用 `indicators.py` 的 `resolve_benchmark(institution_type, metric)`，三级兜底：
- Layer 1: ts_limit_config (DB)
- Layer 2: 用户提供
- Layer 3: 内置 DB37/T 默认值

## 与 chapter5_agent.py 的关系

`chapter5_agent.py` 是第5章表格/图表的唯一渲染器（DB 有数据的场景），author 不重复造表。

## 与 load_from_project() 的配合

`load_from_project(AuditProject)` 自动将 `project.energy_yearly` 字段转为上述结构，填到 `report_data['chapter5']['energy_data']` 中。用户无需手动构造 energy_data 列表。
