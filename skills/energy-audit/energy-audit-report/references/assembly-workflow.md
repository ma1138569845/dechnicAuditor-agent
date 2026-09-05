# 报告组装与交付工作流（实测于烟台法院项目，2026-09）

完整编制一份 Word 报告的实操链路。

## 0. 路径定位（2026-09-04 定）

- **默认路径 = ea-authoring**：author 按 skill 逐章 LLM 写作 → office_editor 组装 Word → 三件套 + 附录（officecli）。
- **本文件描述的是仿写路径**：spec.json → assemble_report.py（energy-audit-imitate 工具，内部用 python-docx 渲染）→ 附录追加（officecli）→ 数值断言。仅当走"仿写同类报告"模式时使用。
- 正文生成脚本（report_generator 的 build_chapter1~8）已退役，任何路径都不再调用。

## 1. 组装（assemble_report.py）

正文写进 spec.json 的 `imitated_chapters`（键为 第1章~第8章，缺章即失败），
图表数据进 `chart_data`，三张信息表进 `audit_info_tables`，然后：

```bash
python "$HERMES_HOME/skills/productivity/energy-audit-imitate/scripts/assemble_report.py" \
  spec.json "reports/<单位>能源审计报告.docx"
```

从仓库根目录运行（assemble 内部 `from tools.energy_audit.report_generator import`），
用仓库 .venv 的 python（assemble_report.py 工具内部依赖 python-docx/matplotlib/graphviz；author 手工编辑文档一律 officecli，见第3节）。

**正文语法**：`1.1 标题`/`1.1.1 标题` 行→H2/H3；`表X.Y 标题` 行后紧跟 `| |`
表格块→Word 规范表（12pt 居中、行高 1.01cm）；`[[图:类型|图注]]`→matplotlib 图。

## 2. 图表类型与口径陷阱（实测）

| 类型 | 内容 | 口径 | 可用性 |
|---|---|---|---|
| flow | 能源流向图（graphviz） | 实物量 | ✅ 与正文一致 |
| monthly_electricity_kwh / monthly_water_m3 / monthly_natural_gas_m3 | 三年逐月对比柱 | 实物量 | ✅ 与正文一致 |
| cost_pie | 最新年费用占比饼图 | 万元 | ⚠️ 仅电/水/气/热 4 项（无油费），只画最新年 |
| trend / pie | 逐年 tce 柱 / 能源结构饼 | **0.1229 折标** | ❌ 与正文 0.31 等价口径矛盾，勿用于指标展示 |

- `flow` 的 energy_types 支持 electricity_kwh/water_m3/natural_gas_m3/
  heating_energy_heat_gj/petrol_kg/diesel_kg；equipment 可选（按 category 归类）。
- 图号按章连续递增，先正文引用后插图（图5.1 流向图、图5.2~5.4 逐月电/水/气、
  图5.5 费用占比）。

## 3. 附录追加（assemble 只生成 8 章；2026-09-03 起统一用 officecli，禁用 python-docx）

**工具**：`office_cli_command`（officecli）——与 ea-authoring 全链一致，python-docx 禁令无例外。
追加方式：对生成后的 docx 依次执行（只改 body，水印/TOC/页码域自动保留）：

```bash
# 标题
officecli add report.docx /body --type heading --prop level=1 --prop text="附录1 建筑基本信息及设备统计表"
# 表格（N行M列）
officecli add report.docx /body --type table --prop rows=N --prop cols=M
officecli set report.docx '/body/table[K]/row[1]/cell[1]' --prop text="..."
officecli set report.docx '/body/table[K]/col[2]' --prop width=5cm
```

**附录清单（7 个，2026-09-05 用户确认；无发票时 6 个）**：

| 附录 | 内容 | 数据来源 |
|---|---|---|
| 附录1 建筑基本信息及设备统计表 | 建筑基本信息（18 字段）+ 设备统计（分系统设备表） | 引用正文表2.1 / 6.x + 说明 |
| 附录2 建筑能耗数据信息表 | 每年一张 7 列表：月份×水量(m³)/水费(元)/单价(元/m³)/电量(kWh)/电费(元)/单价(元/kWh)，12 月+合计行 | 逐月费用从 DB 拉取，**合计必须与正文主表费用一致**（report-qa 铁律） |
| 附录3 电费、水费、油费、燃气费充值发票 | 缴费发票照片（`proj.images` 分类'缴费发票'，caption 为"电费 1月~2月"等类型+期间，按 caption 前缀分组嵌入） | 发票照片采集自 ts_institution_energy_invoice+invoice_image 双表（2026-09-04 接入） |
| 附录4 室内环境测量表 | 室内温度/湿度/照度等实测数据表；**如有室内环境测量表的附件图片则展示** | `proj.indoor_env`（ts_institution_environment，取 deleted=0 且 room_name 合理的记录） |
| 附录5 空气质量判定方法 | 空气质量判定方法 A/B/C/D 表 | 标准固定表 |
| 附录6 室内空气质量指标及要求 | 空气质量指标限值表（GB/T 18883-2022） | 标准固定表 |
| 附录7 各种能源折标准煤参考系数 | 固定表：原煤0.7143/天然气1.2143/液化气1.7143/汽油1.4714/柴油1.4571/燃料油1.4286/电力0.31等价/热力0.03412当量 | 固定（权威值见 core/references/standards-values.md） |

**动态编号规则（2026-09-05 用户确认）**：若无发票相关附件照片，则**没有附录3**，后续附录序号依次前移（附录4→附录3、附录5→附录4、附录6→附录5、附录7→附录6），即无发票时共 6 个附录。编写时先查 `proj.images` 是否有'缴费发票'分类照片再定编号，全文引用的附录编号须与实际编号一致。

追加表格格式：Table Grid 样式、12pt 宋体居中、行高 1.01cm（officecli set 实现）。
无数据的附录列标题 + "待补充"，不编造。

## 4. 组装后数值断言（必做）

对 .docx 全文（段落+表格）做 40+ 项关键数值断言，与 DB 计算值逐一比对：
电量/水量/气量/热量/油量三年值、五项指标值（含供暖）、费用合计、同比率、定额三档值、
用能人数、建筑面积、热价。再扫残留占位符——"测试"命中先确认是否"水平衡测试"
等专业术语，"待补充"应为真实缺失数据（建筑外窗/保温/消防、附件等）。

## 5. 参照报告（RAG 库）

- 党政机关基准：`{HERMES_HOME}/rag/report/能源审计报告/公共机构/党政机关/`
  省贸促会能源审计报告0620.docx（定额三档值出处）
- **法院类最佳参照**：`.../党政机关/法院/省法院报告0620.docx`（8章+12附录完整结构、
  指标计算口径、第7章问题-措施6条对齐示例）
- 指标口径（省法院报告实证）：非供暖能耗=电×0.31 + 天然气×1.2143（热/油剔除）；
  常规电耗=总电量/面积；人均综合能耗=电+气+热(当量0.03412)+汽油(1.4714)全部计入；
  人均取水=水量/人数。信息中心无独立计量时按总电量口径核算并在 5.3 注明未剔除，
  勿编造剔除值；天然气无厨房分项时暂按全部计入并注明。

## 6. 定额值来源验证（硬要求）

- 正确三档值：非供暖能耗 25.5/16.6/9.6、电耗 81.0/52.0/35.5、人均综合能耗
  1611.5/1240.4/700.9 kgce/(p·a)、人均取水 先进10/通用25——以 energy-audit-core/references/standards-values.md（权威单点）
  与样例报告（省贸促会/省法院）为准。
- ⚠️ `tools/energy_audit/indicators.py` 内置 `_DEFAULT_BENCHMARKS['government']`
  =(12.8/8.8/6.0, 45/35/25, 800/600/400) 为**错误兜底值**，勿作对标依据。
- DB 无定额表（ts_energy_standard 仅折标系数）；省级规章（如烟台供暖期《烟台市
  供热管理办法》：市区 11月16日~次年3月31日）必须 web_search 验证后引用。

## 7. 审计机构信息

ts_register_dept（注册单位表）正式记录 2026-09-02 用户已改："同方德诚（山东）科技股份公司/山东省济南市历下区鲁商国奥城5号楼23楼/吕晓晗/15628998185"。名称/地址/负责人/
联系方式必须向用户提问确认（封面+三张信息表用），勿采用测试值；项目记录中
audit_dept_name 亦常为测试值。
