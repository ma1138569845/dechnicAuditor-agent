# 第4章：能源资源计量及统计状况 — 生成指南

> 字段路径见 `references/data-model-reference.md`。4.2 / 4.3 的独立计量判定**必须**先 `load_project()`，用 `proj.metering` + `proj.equipment`，如果均没有获得相关信息，再向用户询问索要已采集的独立计量信息。


## 生成模式

**半自动**：4.1 为固定文字（GB/T29149-2012 标准原文，不嵌入单位定制段）；

4.2-4.3 先按下方算法用采集数据判定，再按写作逻辑成文；仅缺专职人员/台账/统计频率等**未采集项**时才向用户补问。

4.4 问题段优先用 4.2/4.3 已算出的「未独立计量」清单；成效仍可向用户补。

## 4.1 能源资源计量体系

**固定文字**（GB/T 29149-2012 标准原文，2026-09-03 对照正式报告确认，不按机构类型改动、不嵌入单位定制段）：

根据《公共机构能源资源计量器具配备和管理要求》（GB/T 29149-2012）要求，公共机构能源资源计量器具的配备原则应满足公共机构实现电力、煤、天然气等不同种类的能源和水实现分类计量的要求：

（1）应满足公共机构各类能源资源实现分类计量的要求。

（2）应满足不同公共机构能源资源实现分户计量的要求。

（3）应满足公共机构所属能源资源消耗超过规定数量及具有特定功能的区域实现分区计量的要求。

（4）应满足公共机构的主要用能设备单独进行计量的要求。

（5）应满足公共机构实现能源资源数据统计分析和评价用能水平的要求。

（6）有条件的公共机构宜配备智能化、具有远程传输及在线校准功能的能源资源计量器具。

公共机构能源资源计量器具配备要求具体包括：

1、分户计量

进出公共机构的各类能源和水应加装计量器具。两个或两个以上在同一栋建筑或同一个区域不同建筑内的公共机构，其各类能源和水应分别计量。

对于拥有多栋建筑的公共机构，其每栋建筑的电力、热力、水消耗量应单独计量。

2、分区计量

对于公共机构，应满足公共机构所属能源资源消耗超过规定数量及具有特定功能的区域实现分区计量的要求。

主要分区包括：

（1）行政区

固定用电设备额定功率之和超过10kW的行政区，如会议室、资料室、办公室等，其电力消耗量应单独计量。

注：固定用电设备是指除照明系统外，在固定位置使用的用电设备，如分体空调、计算机、打印机、投影仪、音响设备、实验检测仪器等。

（2）业务区

固定用电设备额定功率之和超过10kW的一般业务区，如办事大厅、门诊部、住院部、场馆教室等，其电力消耗量应单独计量。

大型和中型公共机构的特殊业务区，如数据中心（或信息机房）、调度中心、指挥及控制中心。监控中心、实验室、手术室、重症监护室等，其电力和水消耗量应单独计量。

（3）后勤服务区

大型和中型公共机构的用餐场所，其电力、水、炊用燃料消耗量应单独计量。

大型和中型公共机构所属公共浴室的电力、热力、水消耗量应单独计量。

公共机构所属公寓的各类能源和水消耗量应单独计量。

公共机构所属游泳馆的电力、热力、水消耗量应单独计量。

（4）其他区域

有条件的公共机构，其绿化用水宜单独计量。

公共机构对外服务及外包场所的电力和水消耗量应单独计量。

3、主要用能设备计量

大型和中型公共机构的主要用能设备，如中央空调、照明和插座、电梯、供热锅炉、电热水炉等其各类能源和水消耗量应单独计量。

## 4.2 计量器具配备及管理

### 数据来源（先加载，后补问）

从 `load_project()` 取值，**获取不到的时候再向用户询问**：

| 要写的内容 | 取值 |
|---|---|
| 电/水/气/热表数量 | `proj.metering.electric_meters`（meter 表 data_type=1 的 meter_count 回填）/ `water_meters`（data_type=2）/ `gas_meters` / `heat_meters`（后两者 meter 表无列，0 写「数量未记录」，禁止虚构） |
| 分项计量 | `proj.energy_meter[]` 的 `sub_metering`（分项计量描述，非空写入） |
| 计量深度 | `proj.energy_meter[]` 的 `measured_depth`（计量深度） |
| 逐月/年度计量 | `proj.energy_meter[]` 的 `month_measured` / `year_measured`（1是/0否） |
| 厨房用水单独计量 | `proj.energy_meter[]` 的 `kitchen_water`（1是/0否） |
| 分户计量 | `proj.metering.has_household_metering`（`split_measure`，1是/2否） |
| 分户缴费 | `proj.metering.has_household_payment` |
| 独立计量电表 | `proj.metering.has_separate_metering` |
| 合署办公 | `proj.metering.has_shared_office`（`mode`，1是/2否） |
| 合署单位独立计量 | `proj.shared_offices[]`：`dept_name` / `building` / `independent_metering` |
| 冷热源分项计量 | `proj.metering.independent_aircon` |
| 照明分项计量 | `proj.metering.independent_light_socket` |
| 特殊用能分项计量 | `proj.metering.independent_special` |
| 动力用电分项计量 | `proj.metering.independent_power` |
| 单台独立计量 | `eq.independent_metering`：`"有"` / `"无"`；`""` = 无此列或未填，**跳过，不当「无」** |
| 独立计量说明 | `eq.independent_metering_desc`（非空才写入） |
| 器具安装位置 | `proj.metering.install_position`（1按要求/2未按要求；0未记录） |
| 位置合理性 | `proj.metering.position_reasonable`（1合理/2不合理；0未记录） |
| 计量规范性 | `proj.metering.metering_standard`（1非常规范/2一般规范/3不规范；0未记录） |
| 分区缴费 | `proj.metering.partition_payment`（partition_payment 1是/2否） |
| 电费收费方式 | `proj.metering.electric_pay_type` |
| 第三方服务人员 | `proj.metering.service_staff`（非空写「由第三方服务人员 X 负责…」） |
| 专职人员（运维人员判定） | `proj.metering.aircon_staff_num` / `light_staff_num` / `power_room_staff_num`（scene 表运维人数） |
| 现场描述 | `proj.metering.scene_desc`（非空可作现状段补充句） |

**专职人员**（2026-09-03 起不再问用户）：由 scene 表运维人员字段判定——`aircon_staff_num` / `light_staff_num` / `power_room_staff_num` / `service_staff` 任一非空 → 4.2 写「设有 X 名运维人员负责能源计量管理」；全为 0/空 → 不写人员句。**合署办公不要问用户**，用 `has_shared_office` + `shared_offices`。

> 生活用水与消防用水是否分计：**已从 4.2 移除**（2026-09-03 用户确认，不再写、不再问）。

**计量器具台账**（2026-09-03 起不再问用户）：`ts_institution_energy_meter.ledger_files` 台账附件由采集段 `enrich_meter_ledger` 下载并提取文字回填 `proj.metering.ledger_text`——表4.1 台账清单直接从此文字取数（器具名称/计量范围/数量/安装位置）；`ledger_text` 为空才允许写「台账未记录」或向用户补。

### 判定算法（写正文前必须算）

场景级三个布尔 = 冷热源 / 照明 / 特殊是否「具备分项计量」；设备级 `"有"`/`"无"` = 其余设备是否过 6 成。

```python
CORE_CATS = ("空调", "照明", "特殊设备")
eqs = [e for e in proj.equipment if e.independent_metering in ("有", "无")]
core_ok = (
    bool(proj.metering.independent_aircon)
    and bool(proj.metering.independent_light_socket)
    and bool(proj.metering.independent_special)
)
rest = [e for e in eqs if (e.category or "") not in CORE_CATS]
rest_ratio = (sum(1 for e in rest if e.independent_metering == "有") / len(rest)) if rest else 0.0
has_ok = [e.name for e in eqs if e.independent_metering == "有"]
has_no = [e.name for e in eqs if e.independent_metering == "无"]
good_42 = core_ok and (rest_ratio >= 0.6 if rest else True)
# 计量规范性入判定：3 不规范 直接视为不良；2 一般规范 降级为"需提升"
std_ok = proj.metering.metering_standard in (1, 2)
good_42 = good_42 and std_ok
```

`category` 对照：冷热源 → `"空调"`，照明 → `"照明"`，特殊设备 → `"特殊设备"`。办公/厨房/生活热水/蒸汽/输配设备/动力计入「其余」。

### 三句核心话术数据驱动（scene 表字段，禁止固定好话）

模板中"安装位置 / 位置合理性 / 计量规范性"三句必须按字段如实写：

| 字段 | 取值 → 话术 |
|---|---|
| `install_position` | 1 → "计量器具均按照设计要求安装在相应位置"；2 → "部分计量器具未按要求安装"（同时入 4.4 问题段）；0 → 不写安装位置句 |
| `position_reasonable` | 1 → "位置设置合理"；2 → "部分器具安装位置不合理"（入 4.4）；0 → 不写 |
| `metering_standard` | 1 → "计量比较规范"；2 → "计量规范程度一般"；3 → "计量不够规范"（入 4.4）；0 → 不写 |

### 段落写作逻辑

- `good_42` 为真 → 认定计量管理情况良好，列举 `has_ok`（可带 `independent_metering_desc`）。
- 否则用兜底段，**必须点名**哪些有、哪些没有（用 `has_ok` / `has_no`，禁止编造设备名）：

> XX能源计量器具均按照设计要求安装在相应位置，位置设置合理，计量比较规范，满足分户计量要求，达到能源利用管理的最低基本要求；但未实现分区计量和主要用能设备单独计量（已独立计量：…；未独立计量：…）。

（上句三处加粗部分按上表数据驱动替换，0 时整小句删去。）

- **合署办公**（现场表 `mode`）：为**否**时整句不写，不要回显「合署办公：否」。为**是**时也不要写「合署办公：是」，只按 `proj.shared_offices` 的独立计量出下面两句之一（用 `shared_office_metering_sentence`）：
  - 列表里**只要有一个** `independent_metering` 为「有/是」→ `有合署办公且实现了合办公单位独立计量`
  - **全部为否/无**（含无明细行）→ `有合署办公，但未实现各办公单位独立计量`



## 4.3 能源资源统计情况

### 数据来源

| 要写的内容 | 取值 |
|---|---|
| 能耗监测系统 | `proj.metering.has_monitoring_system`：真 → 自动采集；假 → 人工抄表。4.2～4.4 凡有监测系统都必须写到（4.1 固定文字不含） |
| 独立计量覆盖率 | 复用 4.2 的 `eqs` / `has_ok` / `has_no` |
| 特殊用能是否单独计量 | `proj.metering.independent_special` 为假，或 `category=="特殊设备"` 且 `independent_metering=="无"` → 必须写指标偏差句 |
| 办公 / 餐厅未独立计量 | `category` 为 `"办公"` / `"厨房"` 且 `independent_metering=="无"` 时点名 |
| 合署单位独立计量 | `proj.shared_offices[]`；`pay_type` 可写缴费方式（不必再问天然气谁缴费，有值就用） |

无采集字段、缺了才问用户：数据统计频率/统计周期（日/月/季度/半年/年份区间；"日/实时"视为精细，4.3 末段不写统计粒度不足句）、内部公示/成本分摊/复核机制、天然气由谁缴费计量。

覆盖率（与 4.2 的 `rest_ratio` 不同，4.3 看**全部已填独立计量的设备**）：

```python
cover_ratio = (len(has_ok) / len(eqs)) if eqs else 0.0
special_gap = (not proj.metering.independent_special) or any(
    e.category == "特殊设备" and e.independent_metering == "无" for e in eqs
)
office_or_kitchen_gap = [
    e.name for e in eqs
    if e.category in ("办公", "厨房") and e.independent_metering == "无"
]
```

### 判定式（写正文前先算）

```python
cover_ok  = cover_ratio >= 0.6                            # 60% 以上设备已独立计量
cat_count = sum(1 for v in (proj.metering.independent_aircon,
                            proj.metering.independent_light_socket,
                            proj.metering.independent_special) if bool(v))
good_43   = bool(eqs) and cover_ok and cat_count >= 2     # 核心三类（冷热源/照明/特殊）至少满足 2 个
all_ok    = bool(eqs) and not has_no                      # 100% 独立计量（eqs 全部"有"）
```

罗列规则（设备名只取真实名，禁止编造）：
- `has_ok` 罗列：至少 2 个；`len(has_ok) >= 3` 只罗列 3 个；不足 2 个按实际数量罗列。
- `has_no` 罗列：固定 2 个 + "等"；不足 2 个按实际数量罗列。

### 写作逻辑（2026-09 评审口径）

1. 先写盖帽句（固定模版，可按单位名替换）。
2. **`all_ok`（100% 独立计量）**：配置了较完善的计量体系，能够对所有的 **罗列 `has_ok`（同罗列规则）** 等主要设备实现了独立计量。**不加**"但目前仍未能实现……"句。
3. **`good_43`（60% 以上 + 三类至少满足 2 个）**：配置了较完善的计量体系，能够对 **罗列 `has_ok`（同罗列规则）** 设备实现了独立计量，但目前仍未能实现对 **罗列 2 个 `has_no` + "等"** 设备的独立计量，导致仍有部分系统或设备用能数据无法精确分析，需进一步细化计量体系。
4. **特殊设备补充句**（非 100% 且 `special_gap` 为真，接在 2/3 句后）：同时 **`eqs` 中 `category=="特殊设备"` 且 `independent_metering=="无"` 的设备名（有则点名；无名单时写"特殊用能设备"）** 未满足独立计量，导致能耗指标分析时出现指标偏差。
5. **`good_43` 为假（且 `eqs` 非空）**：不满足固定句：[被审计机构]虽配置部分用水用电计量表具，但无法做到各类用能数据分区域分设备等计量。
6. **最后一段·统计粒度句**：统计周期非"日/实时"（月/季度/半年/年份区间）时追加：以 **[月/季度/半年/XX年XX月-XX年XX月]** 为统计周期，管理精细度不足，导致在分析用能情况时，无法精准挖掘用能不合理的原因以及节能潜力点。统计周期为"日/实时"（含监测系统自动日采集）视为精细，**不写该句**。
7. `eqs` 为空：只写监测系统与场景级分项是否具备，不要编设备名单，不要用 6 成/判定句结论（盖帽句与粒度句可正常写）。
8. 合署办公：`shared_office_metering_sentence(proj.metering.has_shared_office, proj.shared_offices)`。否 → 不写；是 → 只用两句固定表述，不点名「合署办公：是」。有 `pay_type` 可另写缴费方式。



## 4.4 能源资源统计成效及问题

- **问题（优先采集）**：未独立计量设备用 4.2/4.3 的 `has_no`；分类缺口用 `independent_aircon` / `independent_light_socket` / `independent_special` / `independent_power` 为假的项；合署单位缺口用 `shared_offices` 中 `independent_metering=="无"` 的 `dept_name`；**现场三状态**：`install_position==2`（器具未按要求安装）、`position_reasonable==2`（位置不合理）、`metering_standard==3`（计量不规范）均须入问题段。禁止另编一套「常见未计量设备」。
- **成效（无字段）**：监测系统效果、人力成本节省、分类统计能力等，缺了再问用户；有 `has_monitoring_system` 则成效段必须提到监测系统。

## 必须提供照片

计量器具现场照片（电表箱、水表、监测系统界面等），嵌入方式同第2/3章（`_add_image_with_caption`）。



## 县级政府适配要点

- 管理机构通常为"机关事务服务中心"，非"厅机关"
- 计量器具数量较省级机构少，但描述格式一致
- 引用的国标（GB/T29149-2012、GB17167-2016）不变

## 关键要点

1. **有监测系统的必须提到**：`has_monitoring_system` 为真时，4.2~4.4 都必须涉及（4.1 为固定文字，不含监测系统）。
2. **没有的数据不要编造**：表数为 0 只说「数量未记录」；`independent_metering == ""` 不得写成未计量。
3. **独立计量已采集则禁止再问**：4.2/4.3 的有/无清单只来自 `proj.metering` 与 `proj.equipment`，不要让用户口头确认替代 `data.json`。
