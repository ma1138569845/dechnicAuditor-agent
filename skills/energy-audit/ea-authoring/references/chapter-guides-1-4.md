# chapter-guides-1-4
> 本文并入 `chapter1-templates.md`、`chapter2-guide.md`、`chapter3-guide.md`、`chapter4-guide.md`（2026-09-18 章节指南合并，原文件已归档至 `_archive/2026-09-18/ea-authoring/references/`）；内容逐字保留，仅统一标题层级。
> 适用：**写章批1（封面 + 第1~4章）**（见 `SKILL.md` 分卡/分批表与 `energy-audit-routing` 阶段 2）。

> **图表规范（强制，2026-09-20 定）**：每张表**必须有表题行** `表X.Y 标题`（章内连续编号、独占一行、紧邻表格上方）；
> 每张图**必须有图注行** `图X.Y 说明（单位：xx）`，且与 `report_images.json` 的 caption **逐字一致**。
> 装配时表题渲染为居中 12pt 加粗、图注为居中 12pt；**缺表题的表格会被 V3 记 P2**。

## 章节索引（跳转用）
| 章 | 本文章节 | 一句话要点 ||---|---|---|| 第1章 | 《第1章 能源审计执行概要》 | 1.1~1.6 模板替换式写作；1.6 省规须 web_search 验证 || 第2章 | 《第2章 公共机构概况》 | 2.1 直取 basic_situation；2.2 每栋一张建筑参数表（表定义在本节末）；建筑地址口径取 base.address || 第3章 | 《第3章 能源资源管理状况》 | 3.1~3.4；字段驱动，禁止用模板句凑满一节 || 第4章 | 《第4章 能源资源计量及统计状况》 | 4.1 固定条文；4.2/4.3 先算 has_ok/has_no 再写 |
---

## 第1章 能源审计执行概要（原 chapter1-templates）

### 输入内容

数据来源：`load_project(unit_name)` 返回的 `AuditProject`（dataclass，一律用 `.` 属性访问，如 `proj.base.unit_name`）。
字段缺失/为空时按 ea-authoring 主 SKILL.md「输入内容」回退流程处理（datacollection → 终止提示），禁止编造数据。

| 输入 | 内容（第一章所需） | 数据模型来源（取值表达式） | 第一章消费点 |
| ---- | ---- | ---- | ---- |
| `base` | 项目基本信息（审计主体与周期）：审计类型 `unit_type`、审计机构 `auditor`、审计项目负责人 `project_manager`、审计起止时间 `audit_start`/`audit_end`、数据统计周期 `data_start`/`data_end`、省份 `province`、报告日期 `report_date`、客户ID `customer_id` | `proj.base`（ProjectBase） | 1.1 审计目的（委托机构）；1.3 审计周期；1.6 审计依据（省份→地方规章检索） |
| `project_context` | 被审计单位概况：单位全称 `unit_name`、简称 `unit_short`、行政归属 `admin_affiliation`、地址 `address`、内设机构/科室 `department_count`、用能人数 `people_count`、床位数 `beds_count`、机构类别 `institution_category`（医疗/教育/党政机关/场馆…）、具体类型 `specific_type`、单位基本情况 `basic_situation`、总建筑面积 `building_area`、建筑数量 `building_count` | `proj.base` + `len(proj.buildings)` | 1.1 审计目的（单位简称）；1.2 审计范围（地址、N 栋建筑）；tags → 1.6 机构类型 |
| `building_data[]` | 建筑列表（每栋）：`name` 建筑名称、`address` 地址、`year` 竣工年份、`function` 建筑功能、`floors` 层数（地上X层/地下Y层）、`height` 高度、`structure` 结构形式、`area` 建筑面积、`use_area` 使用面积、`function_zoning` 功能分区 | `proj.buildings`（List[BuildingInfo]） | 1.2 审计范围（“位于…的 N 栋建筑”）；派生汇总：`building_count = len(proj.buildings)`、`total_area = Σ b.area` |
| `rag_reference[]` | 同类报告第一章写作参考：报告名称、机构类型标签（tags）、章节=第1章、小节（1.1–1.6）、参考正文；检索键 `search_for_chapter('第1章', tags, '能源审计执行概要')` | `rag.rag_search.search_for_chapter()` | 1.1–1.6 的措辞、结构、审计依据清单参考；**不得**覆盖 `base`/`project_context` 中的本项目事实数据 |

补充一行（可自动推导，非人工必填）：

| 输入 | 内容 | 数据模型来源（取值表达式） | 第一章消费点 |
| ---- | ---- | ---- | ---- |
| `energy_types` | 审计周期内实际使用的能源类型（电/水/天然气/热/汽油/柴油）；由 `energy_yearly` 年度数据中非零项自动识别，未采集到时由 `base` 预填 | `proj.energy_yearly[]`（各能耗字段 >0） | 1.2 审计范围（“…等能源账单及能耗统计数据”） |



### 模版

### 1.1 审计目的

固定两段式结构：

```
公共机构能源审计是指依据有关法律、法规、规章和标准，对公共机构的用能系统、设备的运行、管理及能源资源利用状况进行检验、核查和技术、经济分析评价，提出改进用能方式或提高用能效率建议和意见的行为。

为了准确了解部分省级公共机构的用能情况，{省份}省机关事务管理局委托{审计单位}对{被审计单位}进行能源审计。
```

> **取值**：{省份} → `proj.base.province`；{审计单位} → `proj.base.auditor`；{被审计单位} → 正文用简称 `proj.base.unit_short`（空则回退 `proj.base.unit_name`）。

### 1.2 审计范围

两段式结构：段1=物理范围，段2=工作范围。

```
本次能源审计范围包含位于{地址}的{被审计单位}内{建筑列表}。

本次能源审计工作基于{起始年}-{结束年}整年及每月的{能源类型}等能源账单及能耗统计数据，同时结合现场勘察所收集的各建筑围护结构、各类用能设备资料、日常用能习惯等实际数据信息，对{被审计单位}年总能耗、单位建筑面积非供暖能耗、常规用能系统单位建筑面积电耗、人均综合能耗、{取水指标名}等进行分析计算（{取水指标名}按机构类型自适应：医疗→单位开放床日用水量；政务服务中心/场馆→单位建筑面积年取水量；教育→标准人数年均取水量；党政机关→人均机关取水量），依据国家或地方能耗定额标准，对建筑用能现状进行总体评价。
```

> **取值**：{地址} → `proj.base.address`；{被审计单位} → `proj.base.unit_short`（空则 `proj.base.unit_name`）；{建筑列表} → `len(proj.buildings)` 栋建筑，多栋时列出各建筑名称（`b.name`）；{起始年}/{结束年} → `proj.base.data_start` / `proj.base.data_end` 取年份；{能源类型} → `proj.energy_yearly[]` 非零能耗字段推导（electricity_kwh→电、water_m3→水、natural_gas_m3→天然气、heating_energy_heat_gj→热、petrol_kg→汽油、diesel_kg→柴油）。

### 1.3 审计周期

固定格式（三段式，2026-09-05 用户确认）：
```
审计时间
{YYYY年M月—YYYY年M月}

审计期
{YYYY年M月—YYYY年M月}

基准期
{YYYY年M月—YYYY年M月}
```

> **取值**：审计时间 → `proj.base.audit_start`（project.create_time）— `proj.base.audit_end`（报告生成时间），YYYY年M月；审计期 → `proj.base.audit_period`（audit_year）；基准期 → `proj.base.base_period`（reference_year），格式 YYYY年M月—YYYY年M月。

### 1.4 审计内容

完全固定：
```
依据国家有关的节能法规和标准，对公共机构能源资源利用状况进行检验、核查和分析评价，主要包括以下内容：
1.能源资源管理情况；
2.能耗分析评价；
3.节能潜力分析及建议。
```

> **取值**：无输入，固定文本，不替换占位符。

### 1.5 审计过程

三段式（前期/中期/后期），只替换单位简称：

```
审计前期，审计组对{单位简称}发送能源审计调研表，根据反馈调研表梳理分析能耗数据、用能设备情况等，围绕单位用能水平、节能潜力点、能源管理等方面进行分析并形成初步评估意见。

审计中期，审计组开展项目现场调研，根据前期评估内容进行现场沟通核实，确认前期资料与现场数据的一致性。主要调研包括能耗数据异常情况确认、现场用能设备与系统确认、能源管理情况确认等。同时现场重点查看节能管理责任和日常节能措施落实情况、用能系统运维管理情况、能源资源计量器具配备情况等。

审计后期，审计组对现场调研数据及各类资料进行整理汇总，包含但不限于各单位能耗数据、用能系统、异常数据等，分析各单位用能结构和用能规律，进一步全面分析各单位能源应用情况，形成并提交能源审计报告。
```

> **取值**：{单位简称} → `proj.base.unit_short`（空则 `proj.base.unit_name`）。

### 1.6 审计依据

国标固定+省级规章+地方标准，每条用 ● 无序列表。

**省级规章处理原则**：

- 山东项目：直接用参考报告验证过的精确规章（鲁事管发〔2020〕32号、DB37系列）
- 其他省份：必须经 web_search 搜索确认某省真实存在的规章
- 禁止简单字符串替换省份名

> **取值**：{省份}/{机构类型} → `proj.base.province` / `proj.base.institution_category`（决定省级规章与机构类型映射）；国标清单固定；地方规章/同类报告参考 → `rag_reference[]`（检索键 `search_for_chapter('第1章', tags, '能源审计执行概要')`），山东项目可直接用 `province_regulations.get_provincial_regulations(province, inst_type)`。

**标准清单模板（固定，按机构类型微调）**：

法律法规：
- 《中华人民共和国节约能源法》（2016年）；
- 《公共机构节能条例》（2008年）；
- 《公共机构能源审计技术导则》（GB/T 31342-2014）；
- 《公共建筑节能改造技术规范》（JGJ 176-2009）；
- 《公共机构能源审计管理暂行办法》（国家发展改革委、国管局令第32号）；
- 《山东省公共机构节能管理办法》（2009年4月17日山东省人民政府令第210号）；
- 《山东省公共机构能源审计管理办法》（鲁事管发〔2020〕32号）。

技术标准：
- 《公共建筑能源审计技术导则》（2016年）；
- 《公共机构能源管理体系实施指南》（GB/T 32019-2015）；
- 《建筑节能与可再生能源利用通用规范》（GB 55015-2021）；
- 《公共建筑节能监测系统技术标准》（DB37/T 5197-2021）；
- 《民用建筑电气设计标准》（GB 51348-2019）；
- 《空调通风系统运行管理规程》（GB 50365-2019）；
- 《民用建筑供暖通风与空气调节设计规范》（GB 50736-2016）；
- 《建筑给水排水设计标准》（GB 50015-2019）；
- 《供配电系统设计规范》（GB 50052-2009）；
- 《综合能耗计算通则》（GB/T 2589-2020）；
- 《公共机构能源资源计量器具配备和管理要求》（GB/T 29149-2012）；
- 《建筑照明设计标准》（GB/T 50034-2024）；
- 《热泵和冷水机组能效限定值及能效等级》（GB 19577-2024）；
- 《城镇供热管网设计规范》（CJJ/T 34-2022）；
- 《室内空气质量标准》（GB/T 18883-2022）；
- 《党政机关能源消耗定额标准》（DB37/T 2672-2019）；【机构类型非党政机关时替换为对应定额标准】
- 《山东省教育、卫生等服务业用水定额》（DB37/T 4452-2021）；
- 调研资料及其他相关资料。

## 第2章 公共机构概况（原 chapter2-guide）

> 本文并入 `building-param-table-spec.md`（2026-09-18 瘦身合并第 3 组，原文件已归档至 `_archive/2026-09-18/ea-authoring/references/`）；内容逐字保留，仅统一标题层级，引用请指向本文件对应小节。

---

### 第2章生成规则（原 chapter2-guide）

> **职责边界**：本指南只定义第2章的**专业规则**与**结构化输出**，不包含任何 Word 排版/表格绘制细节。文档渲染（标题、正文、表格、图片、样式）统一由装配链落实（装配脚本链为主、office_editor 备用），报告格式规范见 `energy-audit-core/references/report-format-spec.md`。

#### 1. 职责范围

**负责：**
- 分析被审计单位基础数据（`load_project(unit_name)` → `AuditProject` 的 base / buildings / equipment / energy_yearly / images）
- 生成 2.1 公共机构基本情况、2.2 建筑物概况、2.3 能源资源利用情况
- 判断需要生成哪些建筑参数表（`table_type: building_basic_info`）
- 判断需要插入哪些建筑图片（`type: building_exterior`）
- 输出第2章正文与建筑参数表数据（字段口径见「数据来源」节）

**不负责（装配链相关职责）：**

- 创建/保存 Word 文档
- 创建表格、设置行高/列宽/垂直对齐
- 设置字体、字号、加粗、缩进
- 插入图片、设置图片宽度、图注排版
- 表题/图题编号与排版

#### 2. 输入

| 输入 | 内容 |
|---|---|
| `proj.base` | 单位全称/简称、行政归属、地址、内设机构、人员、建筑数量、建筑面积、基本情况等 |
| `proj.buildings[]` | 每栋建筑的 `BuildingInfo` 字段（见 §7 field_mapping） |
| `proj.equipment[]` | 用能设备（category: 空调/照明/办公/厨房…） |
| `proj.energy_yearly[]` | 各能源字段（electricity_kwh/water_m3/…）>0 判定用能类型 |
| `proj.images[]` | 照片（`ImageItem`，category `单位整体外观`（scene_img_id）→ 2.1 段落后图2.1；`建筑外观`/`各建筑外观` → 2.2 每栋照（可选）） |
| rag_reference[] | 同类报告写作参考 |

数据缺失时按 ea-authoring 主 SKILL.md「输入内容」回退流程处理，禁止编造。

#### 3. 生成流程

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
装配链渲染（标题/正文/表格/图片/样式）
    ↓
DOCX
```

LLM 只产出「需要什么内容 / 什么表 / 什么图」，不产出「怎么画」。

#### 4.  2.1 公共机构基本情况 — 生成规则

> **优先级（2026-09-05 用户确认）**：①`proj.base.basic_situation` 完整时直接采用；②为空或不完整时按要素序列兜底补全；③要素字段缺失时可用 `web_search` 查询该机构公开信息（性质定位/职能/隶属/荣誉称号等）辅助 LLM 自然生成，查询结果须与已有数据一致，仍不得编造数字。

**要素序列（一段式，按序覆盖）**：全称 → 简称 → 行政归属 → 地址 → **性质** → 内设机构 → 人员（医院另取床位数 `beds_count`）→ 建筑数量 → 主体建筑 → 建筑面积。

[机构]（以下简称[简称]）[行政归属+地址，如：是XX直属国家机关，位于XX]。院内共设有[内设机构]X个部室，现有干部职工[人数]人。总建筑面积[面积]平方米，主要建筑物包括[建筑列举]。

（插图：图2.1 [机构]单位整体外观，紧跟本段之后、位于 2.2 之前）

**正文直取 `proj.base.basic_situation`**（数据采集阶段已从 ts_customer_info 解析，溯源 PG → Excel）；为空或不完整时由 author agent 依据以下字段补全（LLM 自然生成，非模板填充），一段式，覆盖：

- 全称 `unit_name` → 简称 `unit_short` → 行政归属 `admin_affiliation` → 地址 `address` → 性质 `specific_type`/`institution_category`（机构性质与职能定位）
- 内设机构 `department_count` → 人员编制 `people_count`（医院另取床位数 `beds_count`）→ 建筑数量 `len(proj.buildings)`
- 主体建筑描述 → 建筑面积 `building_area`

**要求：**
- 文本必须是完整自然句子，禁止模板变量、禁止编造数据
- 字段缺失时可 `web_search` 查询公开资料补充性质/职能/隶属/荣誉称号等文字事实，但能耗数据、人数、面积等数字必须来自项目数据，禁止查询结果覆盖或编造
- JSON 字符串中的中文引号必须用 `“` / `”` 转义
- 图片：2.1 段落之后紧跟单位整体外观照片（图2.1，来源 `ts_institution_scene.scene_img_id`，category=`单位整体外观`，1 张；无 scene_img_id 时兜底用 `建筑外观`），位于 2.2 之前；不放设备照片

示例（莘县县政府）：

> 莘县县政府（以下简称"莘县政府"）是莘县人民政府直属国家机关，位于莘县政府街003号。院内共设有办公室、发改局、财政局等20余个内设机构，现有在职职工约300人。总建筑面积4190平方米，主要建筑物包括南楼和北楼2栋：其中南楼建成于1989年，地上5层；北楼建成于2019年，地上2层。两栋建筑均采用框架结构，设有外墙保温。

#### 5. 2.2 建筑物概况 — 生成规则

> **建筑地址口径（2026-09-18 新增）**：建筑参数表的"建筑地址"列一律以 `proj.base.address`（项目地址）为准；
> 若 `buildings[].address` 与项目地址互相矛盾（真实事故：某项目建筑地址写成了另一个区的地址），
> 取项目地址，并在正文注明"建筑表地址与项目地址不一致，已按项目地址填写，待核实"。
> 禁止原样抄录互相矛盾的地址——那会让第 2 章与 1.2 节自相矛盾（采集侧已同步告警）。

**两段式 + 面积汇总 + 收口：**

段1（总览 + 共性特征）：

> XX院内主要建筑物包括A、B等N栋建筑。各建筑均采用框架结构，设有外墙保温，外窗采用中空双层玻璃窗；全部2栋建筑设有屋面保温，2栋建筑配备能耗在线监测系统。

共性特征判定规则：
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

图片（可选，不硬性要求——正式报告 2.2 通常无图）：
- 每栋建筑单独外观照（`proj.images[]` 中 category=`建筑外观`/`各建筑外观`）可插在收口句前，按建筑逐一配图（caption 写建筑名），图号接续图2.1（图2.2、图2.3…）
- 无法判断照片归属哪栋建筑、或无每栋照时，不插图，仅保留文字 + 表

**注意事项：**
- 段1和段2之间空行分隔
- 每栋建筑对应一张 `building_basic_info` 参数表（LLM 只声明表类型，不绘制表格）

#### 6. 2.3 能源资源利用情况 — 生成规则

**按用能类型分系统描述**，各系统之间用`；`分割。用能类型由 `energy_types`（或 `proj.energy_yearly[]` 对应字段 >0）判定，有则写该系统的描述，没有则跳过：

```
用电系统: XX用电系统主要包括[空调设备]、[照明设备]、[办公设备]；用水系统: XX用水系统主要为生活用水、卫生清洁用水等，由市政自来水供水；燃气系统: XX用气系统主要为厨房设备([具体设备名])；用油系统: XX用油系统主要为公务用车燃油消耗；供暖: XX供暖采用市政集中供热，按面积缴费。（仅当有heating数据时）
```

**设备名称和数量（按 category）：**

| category | 表述 | 示例 |
|---|---|---|
| 空调 | `{名称1}、{名称2}等共{N}台` | 冷水机组、多联机等共6台 |
| 照明 | `{名称1}、{名称2}共{N}套` | LED灯具、射灯共40套 |
| 办公/其他 | `{名称}{数量}台` | 电脑30台、打印机5台 |
| 厨房 | `厨房设备({名称1}、{名称2})` | 厨房设备(燃气灶具、消毒柜) |

- 供暖系统：仅当 `heating_energy_heat_gj` > 0 或 `heating_cost_wan` > 0（供热数据存在）时写"XX供暖采用市政集中供热，按面积缴费"
- 无设备数据时兜底：用电写"照明、空调、办公设备等"，天然气写"厨房炊事用气"

#### 7. 建筑基本信息表定义（结构化）

每栋建筑一张 `building_basic_info` 表。**LLM 输出 building 字段数据，不输出表格行/列宽/字体**；4 列键值对布局（16 行）、标签加粗、内容居中、表题在表格上方等由装配链按统一样式绘制（格式见 `energy-audit-core/references/report-format-spec.md`）。

```yaml
table_type: building_basic_info
layout:
  columns: 4
  arrangement: key_value_pair   # 键值对：标签 | 值 | 标签 | 值
  caption: "表2-N {building.name}基本信息"   # 表题在表格上方，由装配链编号
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

> field_mapping 须与 `tools/energy_audit/project_data.py` 的 `BuildingInfo` 字段保持一致（16 行渲染契约，字段缺失/为空时该行留空）；后续第3~6章表格（energy_consumption / equipment_parameter / monthly_energy / energy_balance / saving_measure / investment_analysis）沿用同一机制。

#### 8. 图片规则

| type | 用途 | 数量 | 数据来源 |
|---|---|---|---|
| building_exterior | 2.1 单位整体外观照片（紧跟段落之后） | 1 张 | `proj.images[]` 中 category=`单位整体外观`（ts_institution_scene.scene_img_id），无则 `建筑外观` 兜底 |
| building_photo | 2.2 每栋建筑单独外观照（可选） | 按建筑数 | `proj.images[]` 中 category ∈ {`建筑外观`, `各建筑外观`}，图号接续图2.1；无图/无法归属则不插 |

- 图片路径取自 `proj.images[].path`（`ImageItem`，带分类），禁止虚构
- 图片宽度（12cm）、居中、图注（10pt 宋体居中）由装配链统一处理

#### 9. 输出 — Chapter 2 Result JSON

字段口径：

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
    {"type": "building_exterior", "path": "xxx.jpg", "caption": "图2-1 莘县县政府单位整体外观"}
  ]
}
```

**输出规则：**
- `section_2_1` / `section_2_2` / `section_2_3` 为完整正文段落（author 写作，字段空时按模板兜底）
- 表格只声明 `table_type` + 原始 `building` 字段（`BuildingInfo`，见 §7），**禁止**输出行内容、列宽、字体等排版信息
- 图片只声明 `type` / `path` / `caption`，**禁止**输出宽度、对齐等排版信息
- 表号/图号（表2-1、图2-1）由装配链按出现顺序统一编号；正文"见表2-1至表2-N"由 LLM 按建筑数量 N 生成

#### 10. 校验（Reviewer）

| 检查项 | 规则 |
|---|---|
| 事实 | 所有名称/数字必须来自输入数据（`proj.*` 字段），禁止编造；数据缺失走回退流程 |
| 结构 | 2.1/2.2/2.3 齐全；2.2 含总览段、共性特征、面积汇总、逐栋段、收口句 |
| 表格 | 每栋建筑对应一张 building_basic_info；building 字段与 field_mapping（BuildingInfo）一致，关键字段无缺失 |
| 图片 | building_exterior 1 张（单位整体外观=scene_img_id，无则建筑外观兜底）；building_photo（每栋照）可选不强制；路径真实存在 |
| 逻辑 | 用能系统段与 energy_types 一一对应，无多余/遗漏系统；设备数量表述符合 §6 category 规则 |
| 格式 | 不属于本章职责，由装配链与报告格式规范保证 |

---

### 建筑基本信息表定义（原 building-param-table-spec）

> 权威依据：烟台经济技术开发区人民法院正式报告 R7 版 表2.1。旧 v2.0（10行×4列）已废弃。

#### 表结构

每栋建筑生成一张 **N行×2列** 的键值对参数表（表头 `项目 | 内容`），标题在表格上方："表2.N  建筑名基本信息"（正式版单栋=表2.1）。

#### 字段（按正式版 表2.1 顺序，有数据才列出该行，缺失字段不列出）

| 顺序 | 项目名 | BuildingInfo 字段 | 格式 |
|------|--------|-------------------|------|
| 1 | 建筑名称 | name | 原文 |
| 2 | 地址 | address | 原文（"烟台开发区衡山路20号"式） |
| 3 | 建成年代 | year | "2014年"式 |
| 4 | 建筑面积(m²) | area | 裸数字 |
| 5 | 使用面积 | use_area | 原文；未实测写"未实测（…）" |
| 6 | 建筑层数 | floors | "地上12层，地下1层"式 |
| 7 | 结构形式 | structure | 原文 |
| 8 | 供暖方式 | heating_source | "市政集中供暖"式 |
| 9 | 采暖期 | heat_time | "11月16日~次年3月31日"式 |
| 10 | 供暖末端形式 | heating_terminal | 原文 |
| 11 | 主要功能 | function | "审判法庭、办公办案"式 |
| 12 | 其他有值字段 | （orientation/height/window_type/insulation/cooling_source/cooling_terminal 等） | 有值才补行 |

> 字段无值 → **该行不列出**（不是写空值行）；有值字段即使不在上述 1-11 也补为附加行。严禁编造填充。

#### 表号与位置

- 表号："表2.N  建筑名基本信息"（N 从 1 起按栋递增；正式版单栋即"表2.1 审判综合楼建筑基本信息"）
- 位置：第2章 2.2 建筑物概况，每栋建筑叙述段之后
- 表头行：`项目 | 内容` 两列，宋体12pt 居中

#### 关键 Pitfall

- **两列键值对，不是四列**（旧 v2.0 的 4 列并排键值对已废弃）
- 标题在表上方独立段（"表2.N  …基本信息"），不合并进表内
- 空值行不列出；面积裸数字+表头带单位
- 层数格式 "地上X层，地下Y层"；采暖期格式 "M月D日~次年M月D日"

## 第3章 能源资源管理状况（原 chapter3-guide）

> 数据链路（本指南只指导 LLM 写作，不依赖正文生成脚本）：
> - `tools/energy_audit/file_resolver.py` — `enrich_management_info()`（采集阶段制度文件提炼）
> - `tools/energy_audit/llm_client.py` — `summarize_management_docs()`（LLM 提炼 3.1/3.2）
> - `tools/energy_audit/imitate_pipeline.py` — 仿写管道（新参考模式）

---

### 章节结构（共 4 节 + 图片）

| 节号 | 标题 | 主要数据源 | 为空时行为 |
|---|---|---|---|
| 3.1 | 能源资源管理机构职责 | `proj.management.management_org` | 按 `institution_category` 选用下方四套模板（党政/医疗/教育/通用） |
| 3.2 | 能源资源管理目标和方针 | `proj.management.management_policy` + `es.energy_management` | 无数据时：**仿写同类报告 3.2**（首选）或本指南「方针+管理目标」兜底模板 |
| 3.3 | 能源资源管理问题与成效 | `proj.management.honors` + `es.has_awards` / `award_name` / `energy_pain_points` | 本指南两段式兜底模板（成效段 + 问题段） |
| 3.4 | 节能改造与管理措施 | `es` 各改造字段（见下） | **无数据时不渲染该节** |
| 图片 | 管理文件 / 荣誉证书照片 | `es.management_file_images` + `award_certificate_images` + `images[]` 分类 | 无则跳过 |

> ⚠️ **3.4 是最容易漏的一节**：凡节能管理信息（`ts_institution_energy_saving`）中有改造措施字段，写作时就必须包含 3.4。

---

### 生成模式

**第3章文本由 author（LLM）基于项目数据写作**：读取 `project.management` 与最新一条 `project.energy_saving`（按 `statistical_year` 降序取第一条），按本节模板与字段规则逐节写作。采集阶段 `enrich_management_info` 已由制度文件 LLM 提炼正文，通常可直接采用。三种方式：

1. **直接采用提炼正文（默认）**：`project.management.management_org` / `management_policy` 非空时，直接作为 3.1/3.2 正文；`es` 改造字段生成 3.4。
2. **仿写参考（参考同类报告）**：调用 `energy_audit_imitate_paragraph` 工具或 `/api/energy-audit/imitate` 接口，检索同类报告第3章并按段落结构仿写正文：
   ```python
   # 直接调用（项目名 = proj.base.unit_name）
   run_imitate("莘县县政府", chapter="第3章", section="3.1 机构职责")
   ```
   ```bash
   # CLI 方式
   python -m tools.energy_audit.imitate_pipeline --project 莘县县政府 --chapter 第3章
   ```
   章节上下文：`imitate_pipeline.CHAPTER_CONTEXTS["第3章"] = "能源资源管理状况"`；`normalize_chapter("3.1")` 会自动归一为 `(第3章, 3.1)`。
3. **LLM 增强写作**：提炼文本不足时，author 基于「数据来源」字段 + 本指南模板/句式重写该节（写作原则：先有字段值才有段落，字段空则按模板/兜底）。

**必须提供照片**：管理文件截图、节能荣誉证书等现场照片（数据模型按分类路由，见「图片路由」节）。嵌入方式同第2章（装配链插入 + 图注）。

---

### 3.1 能源资源管理机构职责

**数据源（优先）**：`proj.management.management_org` —— 采集阶段 `enrich_management_info()` 已下载制度文件并 LLM 提炼组织架构/岗位/职责分工，回填此字段。

- **非空**：直接作为 3.1 正文。段落组织参考：落实节能国策与上级会议精神 → 引用制度文件名称 → 管理机构设置 → 职责表述（取自提炼结果）。
- **为空**：author 按 `institution_category` 选用下方模板（2026-09-04 对齐正式报告口径），结合单位实际微调（禁止照抄其他单位的具体名称）。

**机构类型映射**（`proj.base.institution_category` 取值：医疗/教育/党政机关/场馆机构/体育/政务服务中心）：

| institution_category | 使用模板 |
|---|---|
| 医疗 | 医疗机构模板 |
| 教育 | 学校教育模板 |
| 党政机关 / 政务服务中心 | 党政机关模板 |
| 场馆机构 / 体育 / 其他 | 通用模板 |

**医疗机构模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件，并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。
>
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括：
>
> 1.统筹节能工作规划：制定医院节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。
> 2.完善节能管理制度：建立和健全医院节能相关制度（如用电、用水、用热管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导员工养成节能习惯，营造"人人参与节能"的单位氛围。

**党政机关模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立健全的节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导机关全体成员养成节能习惯，营造"人人参与节能"的办公室氛围。 

**学校教育模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定学校节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立和健全校园节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导师生养成节能习惯，营造"人人参与节能"的校园氛围。

**场馆 / 体育 / 政务服务中心等其他类型通用模板**：

> XX各部门能够认真落实节约能源基本国策和省节能工作会议精神，切实加强建筑节能降耗工作，出台关于节水、节电等各类能源管理相关文件。并结合建筑实际情况，设置能源设备管理机构，并安排专人管理设备运行。同时，成立专门的工作领导小组，在节能降耗工作中取得了实效。 
> 为推动单位节能工作，XX制定并实施了节能减排管理措施，成立节能工作小组，负责单位节能工作的安排部署、制度制定、检查通报等事宜。具体职责包括： 
> 1.统筹节能工作规划：制定单位节能工作的中长期规划和年度计划，明确节能目标（如能耗降低指标）、重点任务及实施步骤，确保节能工作有序推进。 
> 2.完善节能管理制度：建立和健全单位节能相关制度（如用电、用水、用暖管理规定，设备节能运行规范等），明确各部门、各区域的节能责任，形成常态化管理机制。 
> 3.开展节能宣传教育：组织节能主题活动（如节能周、知识讲座、竞赛等），普及节能知识和技能，引导办公人员养成节能习惯，营造"人人参与节能"的单位氛围。 

**关键要素**：政策落实情况、制度文件、管理机构、主要负责人/部门。

> **机构等级自适应**：措辞按被审计单位行政等级调整，不要硬套"印发"——省级→厅级单位→印发工作要点；县级→中心/机关事务服务中心→印发通知。撰写"牵头成立/印发文件/部署落实"等表述时先确认单位等级。

---

### 3.2 能源资源管理目标和方针（含管理制度）

**数据源（两段合并，优先级从上到下）**：

1. `proj.management.management_policy` —— `enrich_management_info()` 由制度文件 LLM 提炼的「管理目标 + 管理方针」**合并为一段**回填（`summarize_management_docs` 返回的 `goals_policy`）。非空时作为正文。
2. `es.energy_management` 判定「管理制度」句（**仅当上面 `management_policy` 为空时**叠加）：
   - `energy_management == 1`：`"{unit}已建立能源管理制度，将节能管理纳入日常运营，通过制度建设、定期监督等方式落实节能责任。"`
   - `energy_management == 0`：`"{unit}目前尚未建立完善的能源管理制度，节能管理仍有提升空间。"`
   - `None`（未填写）：不生成，走兜底。

> ⚠️ `management_goals` 字段**当前流水线未消费**（author 写作只读 `management_policy`）。若某项目单独填了 `management_goals`，author 可将其并入正文；但不要假设它会自动出现。

**为空时的兜底与增强**：

①、② 均无数据（无制度文件附件、无法提炼）时，**首选仿写同类报告 3.2 段落**：

- 调用 `run_imitate(项目名, chapter="第3章", section="3.2 管理目标和方针")`，或 CLI：`python -m tools.energy_audit.imitate_pipeline --project XX --chapter 第3章`
- 仿写范围=**段落结构与句式风格**；机构名、制度文件名称、荣誉等具体信息必须替换为本单位实际（未知则标【待补充】），**禁止照抄其他单位名称**
- 仿写后仍需与字段互核：`es.energy_management == 0` 时不得写成"已建立完善制度"，`== None` 时不得虚构制度名
- 仿写不可用时（无同类报告），再走下面兜底：

本指南兜底模板（2026-09-04 对齐正式报告口径），结构为：

> **一、管理方针**：`{unit}以"节约优先、高效利用"为核心方针，将能源资源管理融入单位日常运营和发展规划，通过制度规范、全员参与、及时监督，实现能源消耗合理控制、资源循环利用。`
>
> **二、管理目标**：
> 1．管理与意识目标——（1）制度建设：完善能源资源计量、监测、考核制度，实现能耗数据深度管理；（2）宣传教育：主题活动+新媒体宣传，形成"节能光荣、浪费可耻"单位文化。
> 2.重点用能系统节能目标——（1）照明系统：杜绝"长明灯""白昼灯"；（2）办公系统：电子设备节电模式、下班断电；（3）空调与供暖：夏≥26℃/冬≤20℃；（4）用水系统：杜绝跑冒滴漏、水资源二次利用；（5）节能改造：调研高耗能环节、提出改造方案。

author 想进一步扩展时，可用下面的引言段句式与编号列表（根据单位实际选择）：

**引言段参考句式**：

> XX以习近平新时代中国特色社会主义思想为指导，认真贯彻落实党中央、国务院决策部署和省、市工作要求，聚焦绿色低碳中心工作，强化能源资源全面节约，持续实施绿色低碳引领行动，全面推进各项工作高质量发展。

**编号列表**（作为目标/方针的具体展开，根据单位实际选择 5~9 项；带"←"的为条件项，有对应设施/项目才加入）：
- 一、树立绿色发展理念
- 二、落实能耗"双控"目标
- 三、积极开展示范创建
- 四、坚持反对食品浪费
- 五、做好宣传教育培训
- 六、推进生活垃圾分类（← 有食堂/物业才加）
- 七、深化绿色低碳改造（← 有改造项目才加）
- 八、加强节水护水工作（← 有用水系统才加）
- 九、夯实能源资源消费统计（← 有监测系统才加）

注意：不同机构类型侧重不同——行政机关侧重办公节能+示范创建，医院侧重医疗设备节能+院感控制。

---

### 3.3 能源资源管理问题与成效

**结构：成效段 + 问题段**（标题顺序对齐正式报告「问题与成效」，正文先成效后问题）。

**数据源**：

- **成效**：`proj.management.honors`（已获节能荣誉）；另 `es.has_awards == 1` 且 `es.award_name` 非空时写 `"{unit}节能工作取得成效，{award_name}。"`。
- **问题**：`es.energy_pain_points`（能源利用痛点字段），句式 `"目前能源利用方面存在的主要痛点：{energy_pain_points}。"`。
- **为空时**：本指南兜底模板（2026-09-04 对齐正式报告口径）两段式——成效段（建立定期检查与考核机制、干部职工节能习惯养成、取得初步成效）+ 问题段（"但…管理人员未进行系统性的能源资源指标分析…节能决策滞后…"通用化表述）。
- author 增强时，可将上述真实数据组织为连贯段落，参考句式：

> XX在推进节能工作的进程中，已获得了XXX等荣誉。但对照节能工作要求，仍存在一定改进空间：一是XXX；二是XXX；三是XXX。

> ⚠️ 问题必须来自实际字段（`energy_pain_points` / 计量 / 设备 / 建筑推断），禁止编造。可结合第6章设备数据、第7章问题推断充实，但**不得虚构荣誉或问题**。
> 措辞宜柔化、避免尖锐，用"有待加强 / 进一步完善 / 逐步更新"；典型表述如"监测数据分析能力弱、老旧设备能效低、培训力度不足"。

---

### 3.4 节能改造与管理措施

**数据源**：最新一条 `es`（`ts_institution_energy_saving`）的改造字段，无对应数据时**不写此节**。各字段写作规则：

| 字段 | 条件 | 生成文案 |
|---|---|---|
| `lighting_replacement` | ==1 | `"{unit}已实施照明灯具更换等节能改造措施。"` |
| `ac_replacement` | ==1 | 同上，并入「照明灯具、空调设备更换…」 |
| `water_saving_fixture_replacement` | ==1 | 并入「…、节水型卫生器具更换…」 |
| `central_ac_control` | ==1 | "中央空调系统已增加集中控制，以提升运行能效。" |
| `other_measures` | 非空 | "其他节能改造措施：{other_measures}。" |
| `third_party_system` | 非空 | "能源系统已由第三方托管运营：{third_party_system}。" |
| `charging_pile` | ==1 | "单位已配置充电桩" + 结算方式/安装方式 |
| `third_party_outsource` | ==1 | "用能系统已由第三方外包管理" + 内容/结算方式 |

> ⚠️ author 扩写此节时，只能基于上述真实字段展开，禁止新增未记录的措施。第三方托管/外包、充电桩等均须取自 `es` 字段。

---

### 图片路由

第3章图片来源共三处（author 汇总）：

1. `es.management_file_images`（管理制度附件解析下载后的**本地路径列表**）
2. `es.award_certificate_images`（获奖证书附件下载后的本地路径）
3. `proj.images[]` 中 `category == '管理文件/荣誉'` 的 `ImageItem`（数据采集阶段已分类）

caption 自动编号（图3-1、图3-2…），由装配链嵌入。`PHOTO_CATEGORIES` 中该分类名为 **`'管理文件/荣誉'`**（不是"管理文件截图"），路由键必须一致。

---

### 写作数据映射

| 节 | 数据来源 |
|---|---|
| 3.1 机构职责 | `project.management.management_org` |
| 3.2 目标方针 | `project.management.management_policy`（+ energy_management 制度句合并） |
| 3.3 成效 | `project.management.honors`（+ es 成效/痛点合并） |
| 3.4 改造措施 | es 改造字段（有数据才写） |
| 图片 | es 图片路径 + `proj.images` 分类 `'管理文件/荣誉'` |

> ⚠️ **已无 `config.chapter_texts` 机制**：`chapter_texts` 仅存在于 `rag/energy_audit_importer.py`（知识库导入器）。第3章文本一律从 `project.management` + `project.energy_saving` 写作。

---

### 数据来源（字段速查）

- 3.1 机构职责：`proj.management.management_org`（采集阶段 `enrich_management_info` 由制度文件 LLM 提炼）；为空按 `proj.base.institution_category` 选模板。
- 3.2 目标方针：`proj.management.management_policy`（目标+方针合并段）；`es.energy_management`（1=有制度，0=无制度，None=未填写）判定的制度句在 `management_policy` 为空时叠加。`management_goals` 当前未消费。
- 3.3 问题/成效：`proj.management.honors`；`es.has_awards` / `es.award_name` / `es.energy_pain_points`。
- 3.4 改造：`es.lighting_replacement` / `ac_replacement` / `water_saving_fixture_replacement` / `central_ac_control` / `other_measures` / `third_party_system` / `charging_pile` / `charging_settlement` / `charging_installation` / `third_party_outsource` / `outsource_content` / `outsource_settlement`。
- 制度文件图片：`es.management_file_images` + `es.award_certificate_images`（本地路径，采集阶段已下载）；`proj.images[]` 分类 `'管理文件/荣誉'`。
- 最新一条节能管理信息：`es = max((e for e in proj.energy_saving if e), key=lambda e: e.statistical_year or 0, default=None)`。
- `management_files` 存的是**文件 ID 串**（逗号分隔，供 `file_resolver` 解析下载），**不是可直接引用的路径，勿当路径用**。
- 管理机构名称、负责人、方针文件名称：用户提供。

---

### 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 只写 3.1/3.2/3.3，漏 3.4 | 第3章共 4 节，3.4 改造措施缺失 | 凡 es 有改造字段，必须写 3.4 |
| 用 `config.chapter_texts` 传第3章文本 | 机制已废弃，静默丢失 | author 直接写作 |
| 引用旧编排 `agent_xiaocheng` / `search_for_chapter` 仿写 | 已废弃 | 用 `energy_audit_imitate_paragraph` 工具 / `/api/energy-audit/imitate` |
| 把 `management_files`（文件ID串）当本地路径 | 图片缺失/路径错误 | 用 `management_file_images` 本地路径；ID 串只供 `file_resolver` |
| 3.2 只取 `management_policy`，忽略 `energy_management` 制度句 | 管理制度有无未表述 | 空时按本指南叠加制度句模板 |
| 3.3 编造荣誉/问题 | 报告含虚假数据 | 只用 `honors` / `has_awards` / `award_name` / `energy_pain_points` 实际字段 |
| 3.4 扩写未记录的改造措施 | 与数据矛盾 | 只用 es 各改造字段展开 |

## 第4章 能源资源计量及统计状况（原 chapter4-guide）

> 字段路径见 `references/data-model-reference.md`。4.2 / 4.3 的独立计量判定**必须**先 `load_project()`，用 `proj.metering` + `proj.equipment`，如果均没有获得相关信息，再向用户询问索要已采集的独立计量信息。


### 生成模式

**半自动**：4.1 为固定文字（GB/T29149-2012 标准原文，不嵌入单位定制段）；

4.2-4.3 先按下方算法用采集数据判定，再按写作逻辑成文；仅缺专职人员/台账/统计频率等**未采集项**时才向用户补问。

4.4 问题段优先用 4.2/4.3 已算出的「未独立计量」清单；成效仍可向用户补。

### 4.1 能源资源计量体系

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

### 4.2 计量器具配备及管理

#### 数据来源（先加载，后补问）

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

#### 判定算法（写正文前必须算）

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
## 计量规范性入判定：3 不规范 直接视为不良；2 一般规范 降级为"需提升"
std_ok = proj.metering.metering_standard in (1, 2)
good_42 = good_42 and std_ok
```

`category` 对照：冷热源 → `"空调"`，照明 → `"照明"`，特殊设备 → `"特殊设备"`。办公/厨房/生活热水/蒸汽/输配设备/动力计入「其余」。

**表4.1 计量器具配备清单**（台账从 `proj.metering.ledger_text` 取数，空则按表数写「未记录」）：

| 序号 | 器具名称 | 计量范围 | 数量 | 安装位置 |
|------|----------|----------|------|----------|
| 1 | 电表 | [如：总进线] | 1 | [位置] |
| 2 | 电表 | [如：空调机房] | 1 | [位置] |
| ... | ... | ... | ... | ... |
| N | 水表 | 总管路 | 1 | [位置] |
| N+1 | 天然气表 | [如：厨房] | 1 | [位置] |

#### 三句核心话术数据驱动（scene 表字段，禁止固定好话）

模板中"安装位置 / 位置合理性 / 计量规范性"三句必须按字段如实写：

| 字段 | 取值 → 话术 |
|---|---|
| `install_position` | 1 → "计量器具均按照设计要求安装在相应位置"；2 → "部分计量器具未按要求安装"（同时入 4.4 问题段）；0 → 不写安装位置句 |
| `position_reasonable` | 1 → "位置设置合理"；2 → "部分器具安装位置不合理"（入 4.4）；0 → 不写 |
| `metering_standard` | 1 → "计量比较规范"；2 → "计量规范程度一般"；3 → "计量不够规范"（入 4.4）；0 → 不写 |

#### 段落写作逻辑

- `good_42` 为真 → 认定计量管理情况良好，列举 `has_ok`（可带 `independent_metering_desc`）。
- 否则用兜底段，**必须点名**哪些有、哪些没有（用 `has_ok` / `has_no`，禁止编造设备名）：

> XX能源计量器具均按照设计要求安装在相应位置，位置设置合理，计量比较规范，满足分户计量要求，达到能源利用管理的最低基本要求；但未实现分区计量和主要用能设备单独计量（已独立计量：…；未独立计量：…）。

（上句三处加粗部分按上表数据驱动替换，0 时整小句删去。）

- **合署办公**（现场表 `mode`）：为**否**时整句不写，不要回显「合署办公：否」。为**是**时也不要写「合署办公：是」，只按 `proj.shared_offices` 的独立计量出下面两句之一（用 `shared_office_metering_sentence`）：
  - 列表里**只要有一个** `independent_metering` 为「有/是」→ `有合署办公且实现了合办公单位独立计量`
  - **全部为否/无**（含无明细行）→ `有合署办公，但未实现各办公单位独立计量`



### 4.3 能源资源统计情况

#### 数据来源

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

#### 判定式（写正文前先算）

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

#### 写作逻辑（2026-09 评审口径）

1. 先写盖帽句（固定模版，可按单位名替换）。
2. **`all_ok`（100% 独立计量）**：配置了较完善的计量体系，能够对所有的 **罗列 `has_ok`（同罗列规则）** 等主要设备实现了独立计量。**不加**"但目前仍未能实现……"句。
3. **`good_43`（60% 以上 + 三类至少满足 2 个）**：配置了较完善的计量体系，能够对 **罗列 `has_ok`（同罗列规则）** 设备实现了独立计量，但目前仍未能实现对 **罗列 2 个 `has_no` + "等"** 设备的独立计量，导致仍有部分系统或设备用能数据无法精确分析，需进一步细化计量体系。
4. **特殊设备补充句**（非 100% 且 `special_gap` 为真，接在 2/3 句后）：同时 **`eqs` 中 `category=="特殊设备"` 且 `independent_metering=="无"` 的设备名（有则点名；无名单时写"特殊用能设备"）** 未满足独立计量，导致能耗指标分析时出现指标偏差。
5. **`good_43` 为假（且 `eqs` 非空）**：不满足固定句：[被审计机构]虽配置部分用水用电计量表具，但无法做到各类用能数据分区域分设备等计量。
6. **最后一段·统计粒度句**：统计周期非"日/实时"（月/季度/半年/年份区间）时追加：以 **[月/季度/半年/XX年XX月-XX年XX月]** 为统计周期，管理精细度不足，导致在分析用能情况时，无法精准挖掘用能不合理的原因以及节能潜力点。统计周期为"日/实时"（含监测系统自动日采集）视为精细，**不写该句**。
7. `eqs` 为空：只写监测系统与场景级分项是否具备，不要编设备名单，不要用 6 成/判定句结论（盖帽句与粒度句可正常写）。
8. 合署办公：`shared_office_metering_sentence(proj.metering.has_shared_office, proj.shared_offices)`。否 → 不写；是 → 只用两句固定表述，不点名「合署办公：是」。有 `pay_type` 可另写缴费方式。

**第三方托管能源段句式**（有则写，如食堂燃气由物业单独开户）：XX能源为XX单位单独开户并缴费计量，每月统计使用数据，每季度报送。[简称]不负责相关管理，仅在季度末进行数据汇总统计。

**4.4 问题段兜底句**（无计量类问题时）：部分用能点位尚未实现分项计量，能耗数据精细化管理水平有待进一步提升。



### 4.4 能源资源统计成效及问题

- **问题（优先采集）**：未独立计量设备用 4.2/4.3 的 `has_no`；分类缺口用 `independent_aircon` / `independent_light_socket` / `independent_special` / `independent_power` 为假的项；合署单位缺口用 `shared_offices` 中 `independent_metering=="无"` 的 `dept_name`；**现场三状态**：`install_position==2`（器具未按要求安装）、`position_reasonable==2`（位置不合理）、`metering_standard==3`（计量不规范）均须入问题段。禁止另编一套「常见未计量设备」。
- **成效（无字段）**：监测系统效果、人力成本节省、分类统计能力等，缺了再问用户；有 `has_monitoring_system` 则成效段必须提到监测系统。

### 必须提供照片

计量器具现场照片（电表箱、水表、监测系统界面等），嵌入方式同第2/3章（装配链插入 + 图注）。



### 县级政府适配要点

- 管理机构通常为"机关事务服务中心"，非"厅机关"
- 计量器具数量较省级机构少，但描述格式一致
- 引用的国标（GB/T29149-2012、GB17167-2016）不变

### 关键要点

1. **有监测系统的必须提到**：`has_monitoring_system` 为真时，4.2~4.4 都必须涉及（4.1 为固定文字，不含监测系统）。
2. **没有的数据不要编造**：表数为 0 只说「数量未记录」；`independent_metering == ""` 不得写成未计量。
3. **独立计量已采集则禁止再问**：4.2/4.3 的有/无清单只来自 `proj.metering` 与 `proj.equipment`，不要让用户口头确认替代 `data.json`。
