# 三级兜底查询模式

所有指标计算遵循 Layer 1→2→3 降级策略。

## 折标系数 (`resolve_coefficient`)

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
| 电 | 0.1~1.0 kgce/kWh | 0.1229 |
| 水 | 0.01~1.0 kgce/t | 0.2571 |
| 天然气 | 0.5~2.5 kgce/m³ | 1.3300 |
| 热 | 0.01~0.05 tce/GJ | 0.03412 |
| 柴油 | 1.0~2.0 tce/t | 1.4571 |
| 汽油 | 1.0~2.0 tce/t | 1.4714 |

非供暖能耗计算使用等效电系数 0.31（非 0.1229）。

## 定额对标 (`resolve_benchmark`)

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

## 实现位置

`tools/energy_audit/indicators.py`
- `resolve_coefficient()` — 折标系数三级兜底
- `resolve_benchmark()` — 定额对标三级兜底
- `lookup_coefficient_from_db()` — Layer1 查询 ts_institution_energy_main
- `lookup_benchmark_from_db()` — Layer1 查询 ts_limit_config
