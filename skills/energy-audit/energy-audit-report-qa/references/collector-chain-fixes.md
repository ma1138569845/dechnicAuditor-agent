# 取数/计算链路缺陷清单（法院 D3 端到端验收实证 2026-09）

修复 DB + skill 口径后跑 `data_collection_cli.py` 复验，又暴露 10 个 repo 工具链 bug。
每个条目 = 现象（data.json 里的异常）→ 根因 → 修复点。未来对照核查时直接拿现象查 data.json。

## 能耗解析（pg_collector._collect_from_pg_impl 能耗段）

1. **费用全 0**：费用记录（data_type=2）的 `real_value` 恒为 0（只有 `total_value` 有值），
   但解析用 `unit_total_value`（=real_value）→ 全部 0。实物量（dt=1）恰好 real=total 所以对。
   → 费用取 `building_total_value`（=total_value），/10000 转万元。
2. **气费缺键**：cost_map 只有 电/水/热力/柴油/汽油，缺 `天然气`/code `25` → 气费 0。
   → cost_map 补 `'天然气': 'natural_gas_cost_wan', '25': 'natural_gas_cost_wan'`。
3. **热费/油费未解析**：供热费用 data_type=7、交通费用 data_type=8，原代码只有 dt==1/2 分支 → 0。
   → 加 `elif dt == 7 and field=='heating_energy_heat_gj': cost=building_total_value/10000`（同 dt=8 汽油）。
4. **汽油 t→kg 未换算**：dt=5 汽油 DB 单位是 t，petrol_kg 直接取 → 差 1000 倍。
   → `* 1000`。

## 结构/装配（pg_collector 装配段）

5. **energy_monthly 空**：逐月数据只在 energy_yearly[year]['monthly_electricity_kwh']，
   AuditProject 顶层 energy_monthly 未生成。→ `_expand_energy_monthly()` 从 merged energy_yearly 展开 36 行。
6. **auditor 测试值**：PG ts_institution_project.audit_dept_name='同方德诚测试公司-1' 直接落入 base。
   → `_resolve_auditor()`：含"测试"→ 默认'同方德诚（山东）科技股份公司'。
7. **人数 300（默认值）**：people_count 只 resolve Excel/default，未接 PG scene。
   → impl 把 `scene.work_staff` 放 found['people_count']，build 时加入 resolve 链（351）。
8. **BuildingInfo 拒收 build_img**：采图时把 build_img 传给 BuildingInfo（无此字段）→ TypeError。
   → build_img 单独放 found['building_images']，图片段从这里读。

## 设备/指标/渲染

9. **设备功率单位默认 kW**（"40kW 面板灯"的 repo 侧根因）：`_fmt_device` 无 power_unit 列/值时默认 'kW'，
   但 DB 照明/办公表 power 存 W 数值。→ `_default_power_unit(category)`：照明/办公→'W'，
   空调/动力/热水器→'kW'；表有 power_unit 列时优先读列。
10. **indicators.py 内置定额值错**：government 内置 12.8/8.8/6.0、45/35/25、800/600/400（
    与交付报告 20.0/11.9/6.5、67.4/39.5/20、1197.8/781.0/453.7 完全不同）。
    → 改 _DEFAULT_BENCHMARKS['government'] 为互证口径，注明来源。
11. **format_collection_report 渲染 dict 异常**：能耗异常是 str 列表、功率异常是 dict 列表，
    渲染只适配前者 → 输出 "…年 {能源}"。→ 渲染按 `a.get('说明')` 兜底。

## 功率校验分档规则（data_collection_cli.detect_equipment_power_unit_issue）

- TINY_CATS={照明,办公}、TINY_NAMES=(灯,电脑,台式机,云桌面,打印机,复印机,电开水器)：spec 含 kW 且功率>5 → 报警
- MID_NAMES=(电梯)：>100 kW 报警
- 首版统一 100kW 阈值误判（40kW×224 面板灯不触发），必须分档。
- 电梯 120kW：两层根因——(a) 设备分类表也有版本机制，原 _get_device_by_table 无归一 → 设备清单 3 条重复电梯（草稿+PL0401/0402），已修（device_name+power+power_unit 分组，草稿优先）；
  (b) 用户在平台把电梯改 12kW，**只落在草稿版本**（is_draft=1），正式版本 PL0401/0402 仍是 120。
  → 2026-09-04 起版本归一改**草稿优先**：归一后取草稿 12kW（正确新值）；正式版本仍 120 属旧快照，
     需提示用户发布/同步正式版本，避免后续指定版本号取数时回退旧值。
- pg_query.connect() 必须 autocommit=True（否则异常回退查询因事务 aborted 再报 InFailedSqlTransaction，回退分支失效）。

## 供暖电耗数据链路（已闭环，2026-09-02）

- 指标公式已含剔除逻辑（`(electricity_kwh - heating_energy_kwh) × 0.31`）。
- **DB 挂法（用户已录入法院三年值）**：energy_main `data_type=4 + energy_code=45（电）
  + energy_unit=kWh` = 供暖电耗（与 dt=4 热力 GJ 按 code 区分）。2023/2024/2025 =
  159,682.5 / 120,075 / 78,210 kWh。
- **取数链路已打通**（原缺陷：DB 无记录 + pg_collector 从不传 heating_energy_kwh →
  恒 0，预计算偏高 13.27 vs 正确 12.27）：pg_collector 能耗段加
  `dt==4 and field=='electricity_kwh' → yearly_map[year]['heating_energy_kwh']`；
  project_data.EnergyYearly 加 `heating_energy_kwh: float = 0` 字段（_merge_energy
  的 `EnergyYearly(**merged)` 自动带入）；indicators.py
  energy_yearly_to_yearly_energy_data 补传 `heating_energy_kwh=`。
- 验收：data.json 三年 heating_energy_kwh 与正式版一致，2025 非供暖能耗
  = (1040085−78210)×0.31/24300 = 12.27 ✓。
- 注意：用户平台录入的供暖电耗是草稿（is_draft=1）；该业务键组内无正式版本时
  草稿优先可被取到；该业务键无草稿时取 version_code 大者正式版。QA 时
  对比草稿与正式版本值（不一致以账单为准并告警）。

## 供暖电耗缺失检测与提示（2026-09-02 追加）

- `detect_heating_electricity_missing(pg_result)`（data_collection_cli.py，已接入 anomalies）：
  项目有供暖（热力 GJ/供暖费/heat_pay_type/heat_price 任一存在）但逐年
  heating_energy_kwh 全 0 时输出"提示"级告警——指标计算前须由用户提供或按循环泵
  测算，禁止用 0 代入。法院已录数据 → 不触发（"无数据异常"）。
- 供暖信息缺失提示原为捆绑条件 `if not scene.heat_day` → 报"供热面积/供热天数/热价
  未记录"（heat_price=89.61 有值时也误报热价缺失）→ 改为逐项检查拼 missing 项。
- （已并入）ea-calculation/references/chapter5-writing-logic.md 口径铁律追加：预计算 indicators 的 heating_energy_kwh 缺失时
  按 0 计入属"未剔除口径"，author 写 5.3 不得直接引用预计算值。
- **审计机构取数口径变更（2026-09-02 用户确认"DB 数据为准"）**：audit_org_contact/phone
  从 project.audit_dept_person/audit_dept_tel 直接采用（不再强制向用户提问）；
  get_institution_project 的 SELECT 需含这两列（历史上未查 → 空）。机构名称含"测试"
  时过滤，取 ts_register_dept（注册单位表，勿用 ts_register_info）同品牌（德诚）
  不含"测试"的最新记录。ts_register_dept 现有正式记录（2026-09-02 用户录入）：
  同方德诚（山东）科技股份公司 / 山东省济南市历下区鲁商国奥城5号楼23楼 /
  吕晓晗 / 15628998185——机构名称/地址/负责人/联系方式均可从 DB 直接取到，
  不再出现地址为空。
