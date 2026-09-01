# 代码分析：`tools/energy_audit/indicators.py`

> 分析对象：能源审计工具包指标计算核心模块（959 行，v2.0.0，作者马天远）
> 分析日期：2026-08-28

## 一、文件定位与角色

这是能源审计工具包的**指标计算核心模块**。它不负责 IO、不负责报告排版，只做**纯计算 + 标准对标**。上游消费方已确认：

| 消费文件 | 调用方式 | 用途 |
|---|---|---|
| `pg_collector.py:681` | `proj.indicators = compute_project_indicators(proj)` | 数据收集阶段**预计算**项目指标 |
| `chapter5_agent.py:20-27,367,418` | `from tools.energy_audit.indicators import (YearlyEnergyData, ..., institution_category_to_type, compare_with_benchmark, calc_baseline)` | 报告第 5 章"能源消费指标分析"直接复用 |
| `excel_processor.py:596-597` | `compute_audit_indicators()` → 委托本模块 | 通用指标入口 |
| `report_generator.py` | 引用（指标数据写入报告） | 渲染 |

结论：它是**单一事实来源（single source of truth）**，被数据收集和报告生成两侧共享，改动会影响两条链路。

## 二、结构拆解

```
indicators.py
├── 常量层
│   ├── COEFFICIENTS (L35)            各能源折标煤系数 kgce/kWh 等
│   ├── ELEC_COEFF_NON_HEATING=0.31  非供暖能耗等效电系数
│   └── _DEFAULT_BENCHMARKS (L48)     三级兜底默认定额（medical/government/education）
├── 三级兜底查询层（Layer 1 DB → 2 用户 → 3 默认）
│   ├── lookup_coefficient_from_db()  查 ts_institution_energy_main
│   ├── lookup_benchmark_from_db()    查 ts_limit_config
│   ├── resolve_coefficient()         带合理性范围校验
│   └── resolve_benchmark()          带机构类型标准名匹配校验
├── institution_category_to_type()   机构类别中文→medical/government/education
├── 数据模型 YearlyEnergyData (L264)   @dataclass，含 6 个 @property 计算字段
├── 指标计算函数
│   ├── calc_unit_area_non_heating_energy()   单位面积非供暖能耗
│   ├── compare_with_benchmark()              对标评价（约束/基准/引导）
│   ├── calc_unit_area_electricity()          单位面积电耗
│   ├── calc_per_capita_energy()              人均综合能耗
│   ├── calc_per_capita_water()               人均取水/床日用水
│   └── calc_baseline()                       建筑能耗基准（三年趋势判断）
└── 统一入口
    ├── energy_yearly_to_yearly_energy_data()  EnergyYearly→YearlyEnergyData 转换器
    └── compute_project_indicators()          项目级聚合入口（返回 ok/pending）
```

## 三、核心设计亮点

1. **三级兜底查询（文件头 L4-8 文档）**：系数和定额都走 `DB → 用户 → 内置默认`，且 DB 值有**合理性范围校验**（如电 0.1~1.0）。`resolve_coefficient` 里 DB 越界会 fall through 而非硬用（L176-177），设计上是稳健的。

2. **安全降级**：所有除零/面积无效场景返回同结构全 0 + `error` 字段（L373-376, L486-488, L579-582），`compute_project_indicators` 在缺参数时返回 `status='pending'` 而非抛异常（L824-826）——对 LLM 驱动的报告生成很友好。

3. **非供暖能耗口径正确**：`non_heating_energy_kgce` 用等效电系数 0.31 且只算电（L311-319），符合 GB/T 31342-2014，天然气/水/汽油不计入。

4. **延迟导入避免循环依赖**：`energy_yearly_to_yearly_energy_data` 用 `sys.modules.get` 优先取已加载模块（L733-736）。

## 四、值得注意的问题 / 风险点

1. **`energy_code` 映射硬编码且疑似不全**（L169-170）：
   ```python
   code_map = {'electricity':'45','water':'01','natural_gas':'25','heat':'50','diesel':'300302','gasoline':'300301'}
   ```
   如果 DB 里 `energy_code` 用的是别的编码（如 `10`/`02`），`lookup_coefficient_from_db` 永远查不到 → 静默 fall through 到默认值。这是"为什么有时系数不对"的潜在来源。

2. **`resolve_benchmark` 的 DB 标准名校验是"软"的**（L214-217）：不匹配只忽略 DB 值，但**没有日志告警**，排查时不易发现"本该用 DB 定额却用了默认"。

3. **`calc_per_capita_energy` 的供暖热量单位换算存疑**（L495）：
   ```python
   data.heating_energy_heat * 1000 * data.get_coefficient('heat')
   ```
   `YearlyEnergyData` 里 `heating_energy_heat` 单位是 **GJ**，`get_coefficient('heat')` = 0.03412 tce/GJ = 34.12 kgce/GJ，但乘了 `1000` 把它当成 kgce 加进了"kgce_total"。而 `total_energy_tce` 属性（L305）里 `heating_energy_heat * coeff` 没乘 1000（输出 tce）。**两处口径不一致**：一个把 GJ→kgce 乘了 1000，一个直接 tce。**这可能是人均能耗算错的 bug**——需要确认 `heating_energy_heat` 实际单位与期望输出单位。

4. **`institution_category_to_type` 用子串匹配**（L252-257）：包含"卫生"就判 medical，但"卫生"也可能出现在"爱国卫生运动委员会"这类机关名里，会误判。优先级顺序（医疗→教育→党政）也意味着"大学"里的"医学院附属"可能先命中 medical，需确认是否符合业务。

5. **`compare_with_benchmark` 默认 `institution_type='medical'`**（L392）：`compute_project_indicators` 调用时传了正确类型，但独立调用（如 `_test()` L914）默认 medical，若政府项目误用会拿错定额。

6. **DB 连接每次 `psycopg2.connect` 无连接池**（L95, L126）：高频调用会反复建连，预计算阶段可接受，但若 chapter5 逐条调用会慢。

7. **`heat` 系数注释单位混乱**：L39 注释 `tce/GJ = 34.12 kgce/GJ`，值 `0.03412` 是 tce/GJ；但 `COEFFICIENTS` 其余都是 kgce 系，只有 heat 是 tce 系——这解释了 L495 为何要 ×1000，但 `total_energy_tce`（L305）直接 ×0.03412 得出 tce，逻辑自洽，**只是 kgce 路径（L495）的 ×1000 究竟是修正还是重复修正需要核对**。

## 五、结论

这是一个**设计清晰、容错良好、面向 LLM 报告生成**的审计指标库。主要风险在：
- (a) `energy_code` 映射硬编码
- (b) L495 的供暖热量 ×1000 与 L305 口径不一致（疑似人均能耗计算 bug）
- (c) 子串机构分类可能误判

建议优先核查 L495 的单位换算。

---

### 后续可深挖项

- L495 是否真为 bug（需确认 `heating_energy_heat` 实际单位与期望输出单位）
- `energy_code` 映射在 DB 里的实际取值，验证是否覆盖不全
- 机构分类子串匹配在真实数据上的误判率
