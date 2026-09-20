---
name: energy-audit-pg-data
description: Query Dechnic energy-audit PG tables, codes, traps.
version: 0.1.0
author: matianyuan, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [energy-audit, postgres, data-query, pg]
    category: productivity
    related_skills: [energy-audit-imitate, energy-audit-report]
---

# Energy Audit PG Data Query Skill

从同方德诚能源审计 PG 库（dc_energy_audit2）获取项目/建筑/能耗/设备/计量/场景
数据的查询方法。覆盖活表结构、能源代码映射与旧表陷阱。适用于任何需要取数
的能源审计任务（仿写报告、数据导出、指标计算）。

## When to Use

- 需要查询某个被审计单位/项目的能耗、建筑、设备、计量数据。
- `energy_audit_get_*` 工具不可用或报错时，改用本技能方法直连。
- 用户问"为什么查了某张表"或数据对不上时，用本技能的表结构核对。

Don't use for: 撰写报告正文（`energy-audit-imitate`），整库导出为 md（`references/data-export.md`，本技能自带）。

## Prerequisites

- PostgreSQL 10.10.1.165:5432，库 dc_energy_audit2，用户 postgres。
- `psycopg2`（`import psycopg2` 验证）；优先复用仓库
  `tools/energy_audit/pg_query.py` 的 `PgDataQuery`（已封装连接与常用查询）。

## How to Run

优先工具链，失败再直连：

```python
import sys; sys.path.insert(0, r"<repo根>")
from tools.energy_audit.pg_query import PgDataQuery
with PgDataQuery() as db:
    proj = db.find_project_by_name("省立医院东院")      # 定位项目
    rows = db.get_institution_energy(customer_id=proj["customer_id"])  # 能耗
```

直连兜底（工具/封装均不可用时）：

```python
import psycopg2
conn = psycopg2.connect(host="10.10.1.165", dbname="dc_energy_audit2",
                        user="postgres", password="1qaz@WSX")
conn.autocommit = True  # 必须！否则单条查询报错会 abort 整个事务
```

## 活表速查（ts_institution_* 为真实业务表）

| 域 | 表 | 关联键 |
|---|---|---|
| 客户 | ts_customer_info（含 basic_situation 长文概况） | id |
| 审计项目 | ts_institution_project（audited_name/audit_year/customer_id） | customer_id |
| 审计组人员 | ts_project_audit_user（position=组内职务/degree=学历/qualifications=资质/major=专业） | project_id |
| 配合人员 | ts_project_audited_user（group_position=组内职务/position=职务/sex=性别/department=部门） | project_id |
| 注册信息（审计机构） | ts_register_dept（注册单位表：名称 dept_name/地址 address/负责人 contact/电话 mobile；非 ts_register_info） | dept_name / credit_code |
| 项目级审计机构信息 | ts_project_dept（审计机构信息id表：机构名称 dept_name/地址 address/负责人 contact/联系方式 mobile/project_id；**机构信息表首选来源，按 project_id 查**；负责人/联系方式仅此一源，无值则空不查别的表） | project_id |
| 建筑 | ts_institution_build（build_name/build_area/围护结构/冷热源） | customer_id |
| 能耗年度 | ts_institution_energy（value1..12 月度；data_type 1=实物 2=费用） | customer_id |
| 能耗主数据 | ts_institution_energy_main（折标系数/is_alone/总量；data_type：1=实物量 2=费用 3=供冷 4=供热能耗 5=交通能耗 7=供热费用 8=交通费用） | customer_id |
| 计量表具 | ts_institution_energy_meter（电/水表数量、分项计量、计量深度） | customer_id |
| 节能管理 | ts_institution_energy_saving（制度/奖项/改造记录） | customer_id |
| 场景/人数 | ts_institution_scene（work_staff 用能人数/heat_price 热价；⚠️ heat_area/heat_day 常为 NULL） | customer_id |
| 供热面积 | **权威源 ts_institution_build.heat_area（每栋建筑供热面积，法院=24300 有值）**，非 scene.heat_area；指标计算供暖能耗定额时聚合 build.heat_area，缺失/全 0 时用建筑面积兑底（2026-09-02 用户确认） | customer_id |
| 设备分类 | ts_institution_device_{air,light,office,power,hygiene,hotwater,steam,special,other,td} | customer_id |
| 图片/附件 | **单位整体外观=ts_institution_scene.scene_img_id（2.1 段落后图2.1）**；建筑外观=ts_institution_build.build_img（2.2 每栋照可选）；电水表照片=ts_institution_energy_meter.device_img；**设备照片=设备分表 _img 列（device_img/system_img/tower_img/pump_img 等）**；**发票照片=ts_institution_energy_invoice（主表）+ ts_institution_energy_invoice_image（明细，record_id 关联，file_id→ts_attachment.group_id）**；计量台账=meter.ledger_files/year_files/month_files；管理制度/奖项=ts_institution_energy_saving.management_files/award_certificate | 均为 ts_attachment.group_id |

> 图片 file id 落在 **ts_attachment（列名 group_id，无 id 列**，按 id 查报 UndefinedColumn）；attach_url 为相对路径（/日期目录/xxx.png），拼 `db_config.get_file_base_url()` 得完整 URL（config.yaml energy_audit 段需配 file.base_url）。⚠️ 验证 base_url 时用**本项目实际 attach_url**（法院是 /20260731、/20260801 目录）——全库样例里常见的 /20260207 目录是**别租户旧文件**，拿它测 404 会误判 base_url 失效。

## 人员/审计机构表语义（勿按列名直译，2026-09 用户确认）

**ts_project_audit_user → 报告"能源审计组人员名单"**（组内职务|姓名|学历|所获资质|专业）：
position(职务，存"审计负责人/审计联络人/成员")→role ｜ name→name ｜
degree(学历)→education ｜ qualifications(资质)→certification ｜ major→major

**ts_project_audited_user → 报告"能源审计配合人员名单"**（组内职务|部门|姓名|性别|职务）：
group_position(组内职务，存"组长/联系人")→role ｜ department(部门)→dept ｜
name→name ｜ sex(性别)→gender ｜ position(职务，存"主任/科长")→position

审计组成员取值键已对齐（role/name/education/certification/major 与
role/dept/name/gender/position），`pg_collector` 按上表映射组装即可。

**审计机构信息（报告"能源审计机构信息表"：机构名称/地址/负责人/联系方式）**：
- 名称/地址：ts_register_dept（dept_name/address），按 audit_dept_name 或
  credit_code 匹配；取不到 → 向用户提问，勿静默【待补充】。名称含"测试"字样时
  过滤：取 register_info 同品牌（"德诚"）不含"测试"的最新记录（如"同方德诚(山东)"），
  且报告封面机构名走 _resolve_auditor 过滤"测试"回退正式名，勿原样输出测试名。
- 负责人/联系方式：**2026-09-02 起按用户确认"DB 数据为准"**——直接采用
  ts_institution_project.audit_dept_person / audit_dept_tel（pg_query 已把这两列
  加入 get_institution_project 的 SELECT）；register_info.contact/mobile 仅作
  提问预填参考（audit_org_contact_hint/audit_org_phone_hint），不覆盖 DB 项目值。
- ts_institution_project.audit_dept_name 常为测试值（如"同方德诚测试公司-1"），
  audit_dept_person/tel 则可能是真实人员（吕晓晗/15628998185）——两者处理不同，
  勿一律当测试数据丢弃。
- ts_register_dept 正式记录实例（2026-09-02 用户录入，验证取数用）：
  同方德诚（山东）科技股份公司 / 913701007620260211 / 吕晓晗 / 15628998185 /
  山东省济南市历下区鲁商国奥城5号楼23楼（按 update_time 最新一条即正式值）。

## 供暖电耗的 DB 挂法（2026-09-02 用户录入实证）

供暖电耗（供暖循环泵/供暖风机电耗，须从总电量剔除再算非供暖能耗/常规电耗）
在 energy_main 的挂法：**data_type=4 + energy_code=45（电）+ energy_unit=kWh**。
与 dt=4 热力(50)（供暖热量 GJ）并存于同一 data_type 下，按 energy_code 区分。
烟台法院三年值：2023=159,682.5 / 2024=120,075 / 2025=78,210 kWh（用户平台录入，
录入时为草稿 is_draft=1；该业务键无正式版本时草稿兜底生效）。取数链路已打通：
pg_collector 能耗段 `dt==4 and field=='electricity_kwh'` →
`EnergyYearly.heating_energy_kwh`（project_data 字段）→ indicators.py
`energy_yearly_to_yearly_energy_data` 传入 → `(总电 − heating_energy_kwh) × 0.31`。
验证：2025 非供暖能耗 = (1040085−78210)×0.31/24300 = 12.27 kgce/(m²·a) ✓。

## 单位类型字典与 ts_limit_config 维度（2026-09-20 建）

平台把"机构类型"拆成**一级 + 二级**两列存在 `ts_customer_info`，取值是**字典码**不是中文
（历史代码没读这两列，机构类型靠单位名分类器猜，教育类因此无法定档——见 lessons-learned S8）。

| 列 | 含义 | 字典 |
|---|---|---|
| `customer_func` | 一级单位类型 | `client_dept_type`：A 政务服务中心 / B 场馆机构 / C 医疗机构 / D 党政机关 / **E 教育机构** |
| `children_func` | 二级类型 | `client_dept_type_<一级码>`（见下表） |
| `climate_type` | 气候区 A/B | ⚠️ **实测大面积误填为 A**（济南、聊城在内陆却记 A）→ **不作为取值依据**，气候区一律走内置表 `tools/energy_audit/climate_zone.py`（DB37/5026-2022 表3.0.1），该列只做交叉校验告警 |
| `district_id` | 行政区划代码 | 如 370611；**气候区判定的首选依据**（地址常不含城市名、`ProjectBase.city` 常为空） |
| `field_type` | 所属领域 | 全库 `10`（公共机构）；`20` 公共建筑、`30` 工业企业 |

二级字典取值：

| 一级 | 字典 | 取值 |
|---|---|---|
| A 政务 | `client_dept_type_A` | A 市级及以上 / B 市级以下 |
| B 场馆 | `client_dept_type_B` | A 图书馆 / B 博物馆 / C 剧院 / D 体育馆 / E 科技馆 |
| C 医疗 | `client_dept_type_C` | A 一级 / B 二级 / C 三级 |
| D 党政 | `client_dept_type_D` | A 省级 / B 市级 / C 市级以下 |
| E 教育 | `client_dept_type_E` | A 本科及以上 / B 专科 / C 普通非寄宿制 / D 普通寄宿制 / E 职业学校 / F 初等教育 / G 学前教育 / H 其他教育 |

> 代码侧镜像在 `tools/energy_audit/dept_dict.py`（单点）。平台改字典后跑
> `python -m tools.energy_audit.dept_dict --check-db` 复核（0 = 一致）。
> 采集侧 `pg_collector` 已把 `customer_func` / `children_func` 写入
> `ProjectBase.unit_func` / `children_func`，供定额对标定档（见 ea-calculation SKILL Capability 4）。

### `ts_limit_config`（限额库）维度语义 —— 由库内数据反推确认

| 列 | 语义 |
|---|---|
| `field_type` | 领域（全库 `10`） |
| `group_func` | **一级单位类型码**（= `customer_func`） |
| `children_func` | **二级类型码**（= `customer_func` 对应字典的键） |
| `limit_type` | **指标 / 表号码**：A 表1非供暖 / B 表2供暖 / C 表3人均 / D 表4电耗 / E 表5 EUE / F 用水 / G 室内空气质量 / H 建筑照明 |
| `climate_type` | 气候区 A/B（党政机关、医疗机构用；**教育类为空串**） |
| `heat_type` | 供暖类型 A 市政 / B 空调 / C 燃气油（仅 `limit_type='B'`） |
| `area_code` | **场馆的省市档** A 省级 / B 市级 / C 区县级（注意不在 `climate_type`） |
| `value1/2/3` | 约束值 / 基准值 / 引导值（**用水为 先进值 / 通用值 / 空**） |
| `standard_name` | 引用标准名（注意历史笔误：教育用水写成 `DB37/T 4522-2021`，正确为 `DB37/T 4452-2021`） |

> ⚠️ **该库不参与报告取值**（2026-09-20 用户确认"以内置默认为准"）。
> 取值=`standards-values.md` 的代码镜像；DB 仅由 `indicators.audit_db_benchmark()` 交叉校验并告警。
> 已知数据质量问题（待平台修）：场馆表1 博物馆市档引导值 `80.00`（应 8.0）、场馆表2 图书馆燃气档
> 基准值 `80.00`（应 8.0）、教育用水仅 1 行且标准号/数值均需重录。

## 能源代码映射（勿信 energy_name 列！）

| 代码 | 真实能源 | 判别方法 |
|---|---|---|
| 01 | **自来水**（表头常误标"天然气"） | 数值量级≈用水量（m³），费用≈水费 |
| 25 | **天然气**（真实） | 数值 m³ 量级；标准系数 1.2143（DB 现值 1.33 为错值，遇则修） |
| 45 | 电 | kWh 或万元，折标系数 0.1229/0.31（DB 双存；**报告口径用 0.31 等价，0.1229 为历史当量值，不得用于报告**） |
| 50 | 热能/热力 | GJ；市政集中供热按面积缴费 |
| 02/03 | 汽油/柴油 | 吨/元 |

判别铁律：用 total_value 与年度账单交叉核对数值量级，不要信 energy_name。

## Procedure

1. **定位项目**：`find_project_by_name(关键词)` 模糊匹配；区分
   `audit_dept_name`（审计机构名，会误命中）与 `audited_name`（被审计单位）。
   同一单位可能有多个审计年度项目记录，选数据年度最新且完整的。
2. **取数**：按 customer_id 逐表拉取；主表→子表用 id 列表 IN(...) 二次查询，
   勿跨表 JOIN（表多且字段名不统一）。**所有 ts_institution_* 业务表都带版本机制**——
   一律复用 `pg_query.py` 已内置归一的方法（规则条文见
   `energy-audit-core/references/version-normalization.md`），禁自写多版本查询、禁按业务属性去重。
3. **核对**：能耗实物量↔费用交叉验证（如电价≈0.78 元/kWh、水价≈4.2 元/m³
   可作合理性检查）；场景表若有同一年的两套记录，选与供热费自洽的一套
   （例：年热费 120 万 → 22 元/㎡ × 54523.3㎡ = 119.95 万 ✓）。
4. **口径标注**：建筑面积以建筑表各楼之和为准；用能人数取场景表 work_staff；
   指标计算时注明口径（如"仅按台账单栋建筑面积核算"）。

## Pitfalls

- **版本机制（取数第一铁律）**：规则条文（草稿优先 → version_code 大者 → id 大者；指定
  version_code 只取正式快照；**禁多数投票**）以
  `energy-audit-core/references/version-normalization.md` 为唯一权威，本文件不重复。下面只记 PG 侧事实与坑：
  - **适用表与业务键**（`pg_query.py` 已内置归一，勿自写）：energy_main=(year, data_type, energy_code)、
    build=(build_name, build_func)、scene=(year)、energy_meter=(data_type, statistical_year)、
    energy_saving=(statistical_year)、device_*=(device_name, power, power_unit)。
  - **三副本是版本机制，不是重复导入**：ver=None + PL2026080401 + PL2026080402 各存一份；
    **禁止按 (build_name, build_area) 等业务属性去重**（会误合并同名建筑）——建筑表 3 条"相同"
    记录 = 3 个版本，不是 3 栋楼（2026-09 用户明确纠正）。
  - **冲突处置**：不一致时输出告警清单人工核实，不静默取多数——错误被复制进多个正式版后
    2:1 必然选错（烟台法院 2025 电量、2024/2025 热力颠倒事故）。
- **能耗交叉校验**：年度总量=逐月加总；费用÷单价=用量（如热费 320355.75÷89.61=3575GJ）。
  2023/2024 用水实物量、2025 电量等曾出现 DB 版本与账单不符，采信前必须校验。
- **旧表陷阱**：`ts_energy_audit_project` / `ts_energy_audit_report` 是旧版
  空/历史表（coder/author profile 的旧 skill 仍引用），真实数据在
  `ts_institution_*` 表。查项目/报告内容勿按旧表名直查。溯源证据链见
  `references/legacy-table-trace.md`。
- **必须 autocommit=True**：直连不设置时，一条字段错误会 abort 整个事务，
  后续所有查询返回"当前事务被终止"。
- **版本归一 SQL 陷阱（DISTINCT ON + LEFT JOIN 丢明细行）**：
  `SELECT DISTINCT ON (year,dt,code) ... FROM main m LEFT JOIN data d`
  会把每个 (year,dt,code) 组只保留一行 → 月度 period 明细全部丢失。
  正确写法：先子查询选目标 main.id（DISTINCT ON 只作用于单表），
  外层再 JOIN 明细：`... AND m.id IN (SELECT DISTINCT ON (yy,dt,code) id
  FROM main WHERE ... ORDER BY yy,dt,code, COALESCE(is_draft,0) ASC,
  version_code DESC NULLS LAST, id DESC) ORDER BY m.year, ..., d.period_code`。
  pg_query.py 的 get_institution_energy 已按此实现，勿再写简化版。
- `ts_customer_users` 无 customer_id 字段（按 id 查）；
  `ts_institution_equipment_replacement` 无 customer_id（按 record_id 关联）。
- `ts_annual_energy_user` / `ts_institution_solar` / `ts_institution_energy_invoice`
  常为空表——导出说明里注明"表中无记录"，不是漏查。
- `ts_institution_device` 总表可能为 0 条，设备数据全在分类表中。
- `energy_audit_*` 工具 handler 签名须保持 `(args: dict, **kwargs)`（注册层会
  传 task_id 等 kwargs）；改动工具时勿退回单参数签名。
- **正式版可能在版本升级时被改错/丢数据**（实测：烟台法院 2025 电量正式版 1,011,885
  vs 草稿正确 1,040,085；热力 2024/2025 颠倒；2023/2024 水实物量正式版缺失）→
  取数时与草稿交叉核对，不一致**以账单为准并告警**；无法判断谁对时用下面的
  "热价/单价交叉验证法"判定。
- **热价/单价交叉验证法（判定草稿 vs 正式版谁对，烟台法院实证）**：用
  热力费 ÷ 热力实物量 = 热价，与 `ts_institution_scene.heat_price`（如
  89.61 元/GJ）比：三年一致的那套版本即正确。烟台法院草稿 2024=3575 GJ、
  2025=3246 GJ → 320355.76/3575=89.61 ✓、290874.06/3246=89.61 ✓；正式版
  颠倒后热价变 98.7/81.4 ✗。水价同理（水费÷水量 5.02 元/m³ 三年一致）。
- **费用字段取数（2026-09-05 实测修正，推翻 09-02 旧断言）**：energy_main 费用记录
  （data_type=2 电/水/气费、7=供热费、8=交通费）的 real_value 在草稿与最新正式版本
  已补齐（=total_value），旧版 PL2026080401/0402 的 real_value=0 是历史错值。
  pg_query 映射：building_total_value=total_value、unit_total_value=real_value。
  **取费用用 unit_total_value/10000（元→万元）**，与 pg_collector.py 代码一致
  （法院实测：2023 电费 801503.54 元 → 80.15 万元 ✓）。"real_value 恒 0 必须用
  building_total_value"是 2026-09-02 修复前的旧数据状态，现版本归一（草稿优先）取到
  的最新记录 real_value 有值，旧断言失效。
  实物量（dt=1/4/5）则 real_value=total_value，两者皆可用。
- **费用单位陷阱**：`ts_institution_energy_main` 费用行（data_type=2/7/8）
  energy_unit 标签不可信（烟台法院 2023 标"元"、2024/2025 标"万元"，但值全部实为
  "元"，如 2024 电 752860.98"万元"实为 75.29 万元）。判别：实物量×合理单价≈费用
  （电价≈0.7 元/kWh、水价≈5 元/m³、气价≈4~4.6 元/m³），量级对不上即单位标错。
- **平台修改可能只落草稿版本**（2026-09-02 电梯实证：功率 120→12 只改了草稿，PL0401/0402 仍是旧值）。
  用户声称"DB 已改"时按版本逐条核对；发现只改草稿 → 提示用户在平台发布/同步正式版本，
  或经其同意后事务化同步。
- **设备功率单位按类别推断（_fmt_device 默认 kW 是历史根因）**：设备分类表
  power 列无统一单位——照明/办公类存 W 数值（40W 灯具、150W 台式机、20W
  云桌面），空调/动力/热水器类存 kW 数值（多联机 13.74kW、电开水器 5kW、
  电梯 12kW）；power_unit 列仅部分表有。pg_query.py 已按类别推断默认单位
  （照明/办公→W，其他→kW，有 power_unit 列值则用之）。判别法：类别+数值
  量级（"40kW 面板灯"即 W 误标 kW）；数据质检 detect_equipment_power_unit_issue
  会标记小功率设备被标 kW（真阳性，提示 DB 人工核实）。
- **逐月自洽验证**：`ts_institution_energy_data` 草稿月度合计应=主表
  total_value；若某版本月度合计≠其主表值（烟台法院 PL0402 月度合计 932580
  ≠ 主表 1,011,885），该版本主表值与月度明细自相矛盾，整版不可信，弃用。
  注意半年/季度粒度均摊（period_code 含 '~'）会引入舍入差，用主表 total
  为准。
- **定额值不在 DB**：`ts_energy_standard` 仅存折标系数（电 0.1229/0.31、天然气
  1.2143/1.33、热力 34.12 kgce/GJ 等；**DB 为双值并存，报告口径一律取 0.31 / 1.2143 那一档**），
  无定额标准三档值。报告标注"来源：DB"
  的定额值可能不实——`ts_report_block` 存各项目已生成的报告块（含 deleted=1
  残留），其他项目（如医院）的块可能被生成流程当作参考（实测医院项目 5.3.2
  块含 45.90/6.90），不得作为党政机关对标依据。
- **供热面积不在 scene 表**：scene.heat_area/heat_day 常为 NULL（法院三年均 NULL），
  采集报告“供暖信息未记录”提示即因此。供热面积权威源是
  `ts_institution_build.heat_area`（每栋建筑一列，法院审判综合楼 24300 有值）；
  compute_project_indicators 已改为聚合 buildings[].heating_area，缺失时用
  建筑面积兑底。勘误：CLI 的“供暖信息（供热面积/供热天数/热价未记录）”提示
  已改为逐项检查（heat_price 有值时不再误报）。
- **折标系数口径铁律（2026-09-02 实证）**：水不折算标准煤（附录B 无水），
  综合能耗 = 电0.31 + 热34.12kgce/GJ + 气1.2143 + 油1.4714；DB 气系数 1.33
  是错值；heat 系数 DB 存 kgce/GJ（34.12）须归一为 tce/GJ（0.03412）；
  indicators.py 系数 Layer1 全局查询会跨项目污染。全口径与修复链路见
  `energy-audit-core/references/coefficient-caliber.md`（权威单点）。
- `ts_project_audit_user` / `ts_project_audited_user` **常为空**（项目未挂人员）
  ——报告三张表【待补充】的首查位置；全库可能只有测试数据（如"张三/李四"
  挂在其他项目上），查不到不代表漏查，是业务未录入。
- `system_users` 有审计员档案（degree/qualifications/major/is_audit），仅作
  学历/资质参考，**不是**审计组名单数据源。
- author 写作层曾硬编码 team_members/cooperation 为
  【待补充】占位、institution 取被审计单位字段（语义错位，应取审计机构
  信息）——生成报告前核对 audit_info_tables 装配，勿依赖其兜底。
- **冲突消解禁止多数投票**：错误被复制进多个正式版本后（如 PL0401/0402 均错、
  仅草稿对），多数投票 2:1 必然选中错误值（烟台法院热力 2024/2025 两年均因此
  选反）。取数/采集脚本须"草稿优先 + 不一致输出告警"，不静默消解。
  DB 数据修复全流程（权威源确认→备份→事务改→补版本记录→版本归一 SQL→
  验证清单）见 `references/data-repair-procedure.md`。

## Verification

- [ ] 项目定位成功：返回 audited_name 与预期一致（非 audit_dept_name 误命中）。
- [ ] 能耗实物量与费用量级自洽（用电量×电价≈电费）。
- [ ] 建筑总面积 = 建筑表各楼面积之和，且与报告口径一致。
- [ ] 引用旧表 `ts_energy_audit_*` 时已改用 `ts_institution_*` 对应表。
