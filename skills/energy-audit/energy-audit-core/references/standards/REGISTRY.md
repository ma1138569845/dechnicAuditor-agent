# 标准包注册表（地区 × 报告族）

> 建：2026-10-20
> 用途：回答"这份报告该用哪套标准"，避免跨省、跨报告族借用定额值。
> 规则：每个"地区 × 报告族"只有一个标准包；数值只写在标准包内，SKILL/SOUL 不内嵌。

## 一、注册表

| 地区 | 报告族 | 标准包 | 状态 | 备注 |
|---|---|---|---|---|
| 山东 | 公共机构 | `energy-audit-core/references/standards-values.md` + `coefficient-caliber.md` | **在用** | DB37/T 2672/2671/2673/3780/3781/4452；电力 0.31（等价值） |
| 浙江 | 公共建筑 | `energy-audit-core/references/standards/zhejiang/` | **v0.1 已核验（2026-10-20）** | DB33/T 736-2021、DB33/T 760-2023、浙江省用（取）水定额（2019）；电力 0.1229（当量值）；原文逐表核对 |
| 山东 | 公共建筑 | `energy-audit-core/references/standards/shandong/public_building/` | **已核验并接入（2026-10-23）** | DB37/T 5076/5078/5079-2024；商务办公、宾馆酒店、医院；只有约束值/先进值；DB37/T 5077-2016 已废止 |
| 浙江 | 公共机构 | `energy-audit-core/references/standards/zhejiang/public_institution/` | **已核验并接入（2026-10-23）** | DB33/T 736/737/738-2021；行政机关、场馆、普通高校、二级及以上医疗机构；约束值/基准值/引导值三档 |

## 二、选择键

```
province（山东 / 浙江 / …）
  × unit_type（公共机构 / 公共建筑 / 工业企业）
  × building_subtype（商务办公 / 场馆 / 宾馆酒店 / 医院 / 普通高校等）
```

规则：

1. `unit_type` 优先于"建筑功能"：医院、学校既可能是公共机构，也可能是公共建筑，按项目登记的 `unit_type` 选包。
2. 标准包未核验时，报告中的定额值必须标【待核验】，不得写成正式依据。
3. 不得把山东 `standards-values.md` 的数值复制到浙江包，也不得把浙江值写回山东表。
4. 新增标准包时必须在本表登记；未登记的标准包视为草稿。

## 三、与现有权威索引的关系

- 山东公共机构的"定额三档值"权威仍是 `standards-values.md`，本表不改变它。
- 浙江公共建筑的定额值权威是 `standards/zhejiang/quota-values.md`（核验后）。
- 山东公共建筑的定额值权威是 `standards/shandong/public_building/quota-values.md`，代码只读同目录 JSON。
- 浙江公共机构的 736 数值共用 `standards/zhejiang/quota-values.json`，737/738 数值在 `standards/zhejiang/public_institution/quota-values.json`；不得复制成第三份。
- 折标系数的地区差异见各标准包的 `coefficients.md`；`coefficient-caliber.md` 继续只服务山东公共机构。

## 四、核验状态

| 标准 | 原文是否入库 | 核验状态 | 下一步 |
|---|---|---|---|
| DB37/T 5076-2024 | 是（山东公共建筑包 `sources/`） | 已核验表7.0.2-1～3、16 市二档值、第8章修正 | 已录入 `quota-values.md/json` |
| DB37/T 5078-2024 | 是（山东公共建筑包 `sources/`） | 已核验表7.0.2、16 市二档值、第8章修正 | 已录入 `quota-values.md/json` |
| DB37/T 5079-2024 | 是（山东公共建筑包 `sources/`） | 已核验表7.0.2-1～4、eA/eB/eC、第8章修正 | 已录入 `quota-values.md/json` |
| DB33/T 736-2021 | 是（`E:\工作目录\长三院\审计报告\`） | 已核验表1~表4、第5章统计范围、6.3 修正、附录A | 已录入 `quota-values.md` |
| DB33/T 760-2023 | 是（同上） | 已核验表1、5.1~5.3、附录A | 已录入 `quota-values.md` |
| DB33/T 737-2021 | 是（浙江公共机构包 `sources/`） | 已核验表1、表2、适用范围与附录A | 已录入 `public_institution/quota-values.md/json` |
| DB33/T 738-2021 | 是（浙江公共机构包 `sources/`） | 已核验表1、表2、第6.3条修正、附录A | 已录入 `public_institution/quota-values.md/json` |
| 浙江省用（取）水定额（2019） | 是（同上） | 已核验表47、表57 | 已录入 `quota-values.md` |
