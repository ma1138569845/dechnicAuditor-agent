# 第2章：公共机构概况 — 生成指南

> **职责边界**：本指南只定义第2章的**专业规则**与**结构化输出**，不包含任何 Word 排版/表格绘制细节。文档渲染（标题、正文、表格、图片、样式）统一交给 office_editor 工具集（officecli 只是 editor_sdk 缺失时的受限回退），报告格式规范见 `references/report-format-spec.md`。

## 1. 职责范围

**负责：**
- 分析被审计单位基础数据（`load_project(unit_name)` → `AuditProject` 的 base / buildings / equipment / energy_yearly / images）
- 生成 2.1 公共机构基本情况、2.2 建筑物概况、2.3 能源资源利用情况
- 判断需要生成哪些建筑参数表（`table_type: building_basic_info`）
- 判断需要插入哪些建筑图片（`type: building_exterior`）
- 输出结构化章节结果（Chapter 2 Result JSON，字段对齐 `report_generator.build_chapter2()` 消费的 `report_data['chapter2']`）

**不负责（office_editor 工具集相关职责）：**

- 创建/保存 Word 文档
- 创建表格、设置行高/列宽/垂直对齐
- 设置字体、字号、加粗、缩进
- 插入图片、设置图片宽度、图注排版
- 表题/图题编号与排版

## 2. 输入

| 输入 | 内容 |
|---|---|
| `proj.base` | 单位全称/简称、行政归属、地址、内设机构、人员、建筑数量、建筑面积、基本情况等 |
| `proj.buildings[]` | 每栋建筑的 `BuildingInfo` 字段（见 §7 field_mapping） |
| `proj.equipment[]` | 用能设备（category: 空调/照明/办公/厨房…） |
| `proj.energy_yearly[]` | 各能源字段（electricity_kwh/water_m3/…）>0 判定用能类型 |
| `proj.images[]` | 照片（`ImageItem`，category 为 `建筑外观`/`各建筑外观` 的照片进入第2章） |
| rag_reference[] | 同类报告写作参考 |

数据缺失时按 ea-authoring 主 SKILL.md「输入内容」回退流程处理，禁止编造。

## 3. 生成流程

```
load_project(unit_name) → AuditProject dataclass
    ↓
数据理解与校验（仅使用已确认数据）
    ↓
Chapter 2 SKILL 规则（本指南）
    ↓
LLM 生成结构化章节结果
    ↓
Chapter 2 Result JSON（对齐 report_data['chapter2']）
    ↓
office_editor 工具集渲染（标题/正文/表格/图片/样式）
    ↓
DOCX
```

LLM 只产出「需要什么内容 / 什么表 / 什么图」，不产出「怎么画」。

## 4.  2.1 公共机构基本情况 — 生成规则

**正文直取 `proj.base.basic_situation`**（数据采集阶段已从 ts_customer_info 解析，溯源 PG → Excel）；为空时由 author agent 依据以下字段补全（LLM 自然生成，非模板填充），一段式，覆盖：

- 全称 `unit_name` → 简称 `unit_short` → 行政归属 `admin_affiliation` → 地址 `address`
- 内设机构 `department_count` → 人员编制 `people_count`（医院另取床位数 `beds_count`）→ 建筑数量 `len(proj.buildings)`
- 主体建筑描述 → 建筑面积 `building_area`

**要求：**
- 文本必须是完整自然句子，禁止模板变量、禁止编造数据、禁止引入未提供事实
- JSON 字符串中的中文引号必须用 `“` / `”` 转义
- 图片：2.1 只放建筑外观照片（1~2 张），不放设备照片

示例（莘县县政府）：

> 莘县县政府（以下简称"莘县政府"）是莘县人民政府直属国家机关，位于莘县政府街003号。院内共设有办公室、发改局、财政局等20余个内设机构，现有在职职工约300人。总建筑面积4190平方米，主要建筑物包括南楼和北楼2栋：其中南楼建成于1989年，地上5层；北楼建成于2019年，地上2层。两栋建筑均采用框架结构，设有外墙保温。

## 5. 2.2 建筑物概况 — 生成规则

**两段式 + 面积汇总 + 收口：**

段1（总览 + 共性特征）：

> XX院内主要建筑物包括A、B等N栋建筑。各建筑均采用框架结构，设有外墙保温，外窗采用中空双层玻璃窗；全部2栋建筑设有屋面保温，2栋建筑配备能耗在线监测系统。

共性特征判定规则（对齐 `build_chapter2()`）：
- `structure` / `insulation` / `window_type`：**全部建筑相同**才写"均…"；structure 字段已含"结构"二字时不再重复拼接后缀；insulation 提示"其它"时描述为有保温即可；window_type 含"—"/"无"时跳过
- `roof_insulation == '有'` → "全部{N}栋建筑设有屋面保温"；部分建筑用"{N}栋（{X}%）建筑设有屋面保温"
- `monitoring == '有'` → "全部{N}栋/N栋（X%）建筑配备能耗在线监测系统"
- `storey_metrology == '是'` → "全部{N}栋/N栋（X%）建筑实现楼层单独计量"
- `sunshade_type` → "遮阳形式为{'、'.join(sunshades)}"
- 上述维度无数据时，不输出对应句

面积汇总（供冷 / 供热 / 地下车库，对应面积 >0 才写）：

> 全院合计：供冷面积Xm²、供热面积Ym²、地下车库面积Zm²。

段2（逐栋详情，按建筑面积从大到小排列）：

> A，1990年竣工，地上5层，建筑面积5000m²，框架结构，朝南，屋面保温（挤塑板）；B，2019年竣工，地上2层，建筑面积3000m²，框架结构。

逐栋字段顺序（对齐代码，空值跳过）：`name` → `{year}年竣工` → `floors` → `建筑面积{area}m²` → `structure` → 可选：`朝{orientation}` → `供冷面积{m²}` → `供热面积{m²}` → `屋面保温（{roof_insulation_material}）`（当 `roof_insulation=='有'`）→ `采用{sunshade_type}` → `运行时间为{run_time}` → `配备能耗在线监测系统`（当 `monitoring=='有'`）

收口句（必须）：

> 各建筑详细参数见表2-1至表2-N。

**注意事项：**
- 段1和段2之间空行分隔
- 每栋建筑对应一张 `building_basic_info` 参数表（LLM 只声明表类型，不绘制表格）

## 6. 2.3 能源资源利用情况 — 生成规则

**按用能类型分系统描述**，各系统之间用`；`分割。用能类型由 `energy_types`（或 `proj.energy_yearly[]` 对应字段 >0）判定，有则写该系统的描述，没有则跳过：

```
用电系统: XX用电系统主要包括[空调设备]、[照明设备]、[办公设备]；用水系统: XX用水系统主要为生活用水、卫生清洁用水等，由市政自来水供水；燃气系统: XX用气系统主要为厨房设备([具体设备名])；用油系统: XX用油系统主要为公务用车燃油消耗；供暖: XX供暖采用市政集中供热，按面积缴费。（仅当有heating数据时）
```

**设备名称和数量（按 category，对齐 `build_chapter2()`）：**

| category | 表述 | 示例 |
|---|---|---|
| 空调 | `{名称1}、{名称2}等共{N}台` | 冷水机组、多联机等共6台 |
| 照明 | `{名称1}、{名称2}共{N}套` | LED灯具、射灯共40套 |
| 办公/其他 | `{名称}{数量}台` | 电脑30台、打印机5台 |
| 厨房 | `厨房设备({名称1}、{名称2})` | 厨房设备(燃气灶具、消毒柜) |

- 供暖系统：仅当 `heating_energy_heat_gj` > 0 或 `heating_cost_wan` > 0（供热数据存在）时写"XX供暖采用市政集中供热，按面积缴费"
- 无设备数据时兜底：用电写"照明、空调、办公设备等"，天然气写"厨房炊事用气"

## 7. 建筑基本信息表定义（结构化）

每栋建筑一张 `building_basic_info` 表。**LLM 输出 building 字段数据，不输出表格行/列宽/字体**；4 列键值对布局（16 行）、标签加粗、内容居中、表题在表格上方等由 office_editor 工具集按统一样式绘制（对齐 `report_generator._add_building_param_table()`，格式见 `references/report-format-spec.md`）。

```yaml
table_type: building_basic_info
layout:
  columns: 4
  arrangement: key_value_pair   # 键值对：标签 | 值 | 标签 | 值
  caption: "表2-N {building.name}基本信息"   # 表题在表格上方，由 office_editor 编号
field_mapping:  # 行顺序 = 表格行顺序；字段缺失/为空时跳过该行（值列单位 m² 由渲染层处理）
  name: 建筑物名称
  address: 建筑地址
  year: 建造年代
  function: 建筑功能
  floors: 建筑层数
  area: 建筑面积
  structure: 建筑结构形式
  window_type: 建筑外窗类型
  insulation: 建筑外墙保温
  orientation: 建筑朝向
  function_zoning: 建筑功能分区
  height: 建筑高度
  cooling_source: 夏季空调冷源
  heating_source: 冬季供暖热源
  cooling_terminal: 夏季空调末端
  heating_terminal: 冬季供暖末端
  water_system: 建筑给水系统
  fire_system: 建筑消防给水系统
  hot_water: 生活热水系统
  monitoring: 能耗在线监测系统
  use_area: 使用面积
  cooling_area: 供冷面积
  heating_area: 供热面积
  wall_body_material: 外墙主体材料
  roof_insulation: 屋面保温
  roof_insulation_material: 屋面保温材料
  sunshade_type: 遮阳形式
  sunshade_material: 遮阳材料
  run_time: 建筑运行时间
  storey_metrology: 楼层单独计量
  garage: 地下车库
  garage_area: 地下车库面积
```

> field_mapping 须与 `tools/energy_audit/project_data.py` 的 `BuildingInfo` 字段保持一致（此处即 `_add_building_param_table()` 的 16 行渲染契约，字段缺失/为空时该行留空）；后续第3~6章表格（energy_consumption / equipment_parameter / monthly_energy / energy_balance / saving_measure / investment_analysis）沿用同一机制。

## 8. 图片规则

| type | 用途 | 数量 | 数据来源 |
|---|---|---|---|
| building_exterior | 2.1 建筑外观照片 | 1~2 张 | `proj.images[]` 中 category ∈ {`建筑外观`, `各建筑外观`}，未分类照片兜底 |

- 图片路径取自 `proj.images[].path`（`ImageItem`，带分类），禁止虚构
- 图片宽度（12cm）、居中、图注（10pt 宋体居中）由 office_editor 工具集统一处理

## 9. 输出 — Chapter 2 Result JSON

字段对齐 `build_chapter2()` 消费的 `report_data['chapter2']`：

```json
{
  "chapter": "2",
  "title": "公共机构概况",
  "unit_name": "莘县县政府",
  "building_area": 4190,
  "people_count": 300,
  "beds_count": 0,
  "section_2_1": "莘县县政府（以下简称...）",
  "section_2_2": "莘县县政府院内主要建筑物包括南楼、北楼等2栋建筑。各建筑均采用框架结构...",
  "section_2_3": "莘县县政府用电系统主要包括...；用水系统...",
  "buildings": [
    {"table_type": "building_basic_info", "building": {"name": "南楼", "year": 1989, "floors": "地上5层", "area": 4190, "structure": "框架结构"}},
    {"table_type": "building_basic_info", "building": {"name": "北楼", "year": 2019, "floors": "地上2层", "area": 3000, "structure": "框架结构"}}
  ],
  "images": [
    {"type": "building_exterior", "path": "xxx.jpg", "caption": "图2-1 莘县县政府建筑外观"}
  ]
}
```

**输出规则：**
- `section_2_1` / `section_2_2` / `section_2_3` 为完整正文段落（段间空行由渲染层处理；为空时 `build_chapter2()` 走自动生成兜底）
- 表格只声明 `table_type` + 原始 `building` 字段（`BuildingInfo`，见 §7），**禁止**输出行内容、列宽、字体等排版信息
- 图片只声明 `type` / `path` / `caption`，**禁止**输出宽度、对齐等排版信息
- 表号/图号（表2-1、图2-1）由 office_editor 按出现顺序统一编号；正文"见表2-1至表2-N"由 LLM 按建筑数量 N 生成

## 10. 校验（Reviewer）

| 检查项 | 规则 |
|---|---|
| 事实 | 所有名称/数字必须来自输入数据（`proj.*` 字段），禁止编造；数据缺失走回退流程 |
| 结构 | 2.1/2.2/2.3 齐全；2.2 含总览段、共性特征、面积汇总、逐栋段、收口句 |
| 表格 | 每栋建筑对应一张 building_basic_info；building 字段与 field_mapping（BuildingInfo）一致，关键字段无缺失 |
| 图片 | 仅 building_exterior，1~2 张，取自 images[]（建筑外观/各建筑外观/未分类），路径真实存在 |
| 逻辑 | 用能系统段与 energy_types 一一对应，无多余/遗漏系统；设备数量表述符合 §6 category 规则 |
| 格式 | 不属于本章职责，由 office_editor 与报告格式规范保证 |
