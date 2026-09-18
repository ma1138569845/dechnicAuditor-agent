# script-assembly-chain
> 本文并入 `assembly-workflow.md`（2026-09-18 瘦身合并第 4 组，原文件已归档至 `_archive/2026-09-18/energy-audit-report/references/`）；内容逐字保留，仅统一标题层级。

---

## 装配脚本链（build → finalize → asserts，2026-09-17 主链）

> 定位：报告"版式装配 + 收尾"的**默认路径**；内容层不变（正文仍由 LLM 逐章写 `chapter_md/chN.md`）。
> office_editor 路径降为**备用**（存量报告定点修改、应急）。
> 首次验证（2026-09-17，烟台经开区法院）：与 45 页终稿逐段文本 diff=0、交付断言 10/10、
> 单份装配+收尾 ≈30 秒（不含写章）。

### 两条命令 + 一个断言器

```bash
## ① 装配（一次构建：封面/信息表/目录/8章/附录/页眉水印页脚）
python skills/energy-audit/energy-audit-report/scripts/build_energy_audit_docx.py \
    --project-dir <项目目录> [--out <docx路径>]

## ② 收尾（Word COM 一次：刷目录域缓存 → 保存 → ExportAsFixedFormat → 封面盖章）
python skills/energy-audit/energy-audit-report/scripts/finalize_energy_audit_pdf.py \
    --project-dir <项目目录> [--no-seal] [--seal-text 审计机构名]

## ③ 交付断言（每份必跑；docx 级 10 项硬检查 + PDF 级度量）
python skills/energy-audit/energy-audit-report/scripts/ea_docx_asserts.py \
    <报告.docx> [--pdf <报告.pdf>] [--expect pages=45]
```

默认输出：`<项目>/output/_script_build/<单位全称>能源审计报告.docx|pdf`。

**交付归置（2026-09-17 定；烟台法院项目首用）**：对外交付时，把 docx + 签章 PDF **复制**到 `<项目>/output/交付件/<单位全称>能源审计报告.docx|pdf`——`交付件/` 为唯一对外出口；沙箱正本（`_script_build` 等）保留不动，**复制不移动、不覆盖、不删除**既有文件。

### 输入契约（项目目录）

| 输入 | 说明 |
|---|---|
| `data.json` | base（unit_name/audit_org_name/audit_org_address/contact/phone/report_date）、energy_yearly（审计期间年）、audit_team、cooperation |
| `chapter_md/ch1..ch8.md` | LLM 逐章正文（第5章用 caliber 产出的 `ch5_import.md`，脚本优先匹配 `chN_import.md`）。`ch5_import.md` 由 `ea-calculation/scripts/prepare_chapter_md.py <项目名>` 就位（不覆盖作者已并入叙述段的版本；退出码 2 = 装配稿早于计算产物需人工确认） |
| `chapter_md/appendix.md` | 附录（7 附录约定；有发票插发票附录） |
| `report_images.json` | 图清单：`{images: [{caption: "图X.Y …", src: 相对路径}]}`；caption 须与 md 图注行**精确一致**（`图4.1` 双图=两条同 caption 记录） |
| `assets/omml_formulas.json` | OMML 公式库（当前法院/机关型 5 个）。其他机构类型在其项目首次使用时从同类成品提取补入——同一 JSON 加键 `FORMULAn` 即可，无需改代码 |

### 装配覆盖（对齐 45 页终稿）

- 封面：3 空行 + 单位 22pt + 报告名 26pt + 审计期间 + 8 空行 + 机构/日期 + 分页；
- 三张信息表（机构/审计组/配合人员）；
- 目录页：'目  录'（无标题样式防自收录）+ TOC 域 `\o "1-3"`；**其后不插分页**（第1章同页顺延，复刻终稿）；
- 章节：H1 15pt 居中 / H2 14pt / H3 12pt；正文 1.5 行距 + 两端对齐 + 首行缩进 2 字符（firstLineChars=200）；表 Table Grid、12pt 居中、行高 1.01cm；图 12cm 独立居中段 + 图注段；公式三段式（按式→OMML 居中段→计算）；项目符号 Wingdings 圆点；
- 页眉（单位全称 + 两空格 + 能源审计报告，右对齐宋体 10.5pt + pBdr 底边线 + EAWatermark 水印 behindDoc）/ 页脚（— PAGE —）/ settings updateFields；
- 附录：'附录：' 总页（H1 样式、12pt 非粗、左对齐）+ 清单行（1.5 行距无缩进）+ H2 附录标题 + 附表题（居中加粗）+ 表格。

### 收尾（Word COM）要点

- 打开**必须传绝对路径**（相对路径 Word 按自身工作目录解析 → 报"找不到您的文件"）。
- 流程：`TablesOfContents(1).Update()` + `Fields.Update()` + `Repaginate()` → `Save()` → `ExportAsFixedFormat(pdf, 17)`。
- **Word 保存会剥离 `<w:updateFields>`** → 收尾脚本 zip 级自动补写（与 45 页终稿终态一致）。
- 盖章：`tools/energy_audit/assets/default_seal.png` 存在即用真实印章（忽略 seal_text），否则按 `base.audit_org_name` 生成 480×480 占位红章；位置 = 封面水平居中、y≈0.66·页高、宽 120pt。

### 已知偏差（vs 45 页终稿；验收口径 = 断言全绿 + 文本一致 + 页数 ±2）

1. 页数 44 vs 45（±1 容差内）：TOC 区占用 +1 页、ch6 −1、ch7 +1、ch8 −1、附录 −1（净 −1）。
2. 表列宽：脚本 = 全幅均分（8312 twips）；终稿 = 导入链自然宽（3280~8340 不等）。行数/行高/单元格格式一致。
3. Word 收尾按字体脚本边界**拆分 run**（渲染不变）：对收尾后 docx 的文本正则必须按段落拼接 `w:t` 后再匹配（断言器图注度量已按此实现）。
4. 目录占位文本"（打开文档后目录将自动更新）"由收尾刷新为缓存条目；断言器区分"未缓存占位（合法）"与"自收录错误"。

### 模板资产（随技能维护）

| 资产 | 来源 | 用途 |
|---|---|---|
| `assets/header_template.xml` | 烟台法院 45 页终稿 header（单位名→`{{UNIT}}` 占位、去 pStyle 引用） | 页眉文字 + 水印注入（zip 级替换 headerN.xml） |
| `assets/footer_template.xml` | 同上 footer（— PAGE —） | 页脚注入 |
| `assets/omml_formulas.json` | R7 终稿提取的 5 个已验证 OMML | `[FORMULAn]` 占位行注入 |

### 验证

- 单元：`pytest tests/skills/test_energy_audit_docx_build.py -q`（17 项：结构/样式/公式/图/附录/页眉/收尾 --help/缺键告警/变体注入）；
- E2E：法院项目全量重跑，对照 45 页终稿（文本 diff=0、断言全绿、耗时记录）；
- 交付：每份必跑断言器；数值断言仍走 `tools/energy_audit/report_qa.py`（口径不变）。

### 操作坑（实战记录）

- Word COM 一律绝对路径；收尾结束前用重试式原子替换（Word 关闭瞬间句柄未释放）。
- 断言/比对工具对"收尾后 docx"须按段落拼接文本（run 拆分，见偏差 3）。
- 封面签章图核验：PDF p1 应存在 480×480 图对象（ycenter≈0.66）。

---

## 报告装配工作流（spec.json → assemble_report.py → 附录 → 数值断言；含仿写链工艺）

完整编制一份 Word 报告的实操链路。

### 0. 路径定位（2026-09-04 定；2026-09-17 更新）

- **主链（2026-09-17 起）= 装配脚本链**：`build_energy_audit_docx.py` → `finalize_energy_audit_pdf.py` → `ea_docx_asserts.py`（见 `script-assembly-chain.md`）；内容仍由 LLM 逐章写 `chapter_md/`，脚本只做版式装配与收尾。
- **备用路径 = office_editor（ea-authoring 内）**：author 按 skill 逐章 LLM 写作 → office_editor 组装 Word → 三件套 + 附录（officecli）。
- **本文件描述的是仿写路径**：spec.json → assemble_report.py（energy-audit-imitate 工具，内部用 python-docx 渲染）→ 附录追加（officecli）→ 数值断言。仅当走"仿写同类报告"模式时使用。
- 正文生成脚本（report_generator 的 build_chapter1~8）已退役，任何路径都不再调用。

### 1. 组装（assemble_report.py）

正文写进 spec.json 的 `imitated_chapters`（键为 第1章~第8章，缺章即失败），
图表数据进 `chart_data`，三张信息表进 `audit_info_tables`，然后：

```bash
python "$HERMES_HOME/skills/energy-audit/energy-audit-imitate/scripts/assemble_report.py" \
  spec.json "reports/<单位>能源审计报告.docx"
```

从仓库根目录运行（assemble 内部 `from tools.energy_audit.report_generator import`），
用仓库 .venv 的 python（assemble_report.py 工具内部依赖 python-docx/matplotlib/graphviz；author 手工编辑文档一律 officecli，见第3节）。

**正文语法**：`1.1 标题`/`1.1.1 标题` 行→H2/H3；`表X.Y 标题` 行后紧跟 `| |`
表格块→Word 规范表（12pt 居中、行高 1.01cm）；`[[图:类型|图注]]`→matplotlib 图。

### 2. 图表类型与口径陷阱（实测）

| 类型 | 内容 | 口径 | 可用性 |
|---|---|---|---|
| flow | 能源流向图（graphviz） | 实物量 | ✅ 与正文一致 |
| monthly_electricity_kwh / monthly_water_m3 / monthly_natural_gas_m3 | 三年逐月对比柱 | 实物量 | ✅ 与正文一致 |
| cost_pie | 各年费用占比饼图（每年一张，三年三张连号） | 万元 | ✅ 费用类型仅含>0 项（含油费/柴油费），逐年标题"{year}年能源费用占比" |
| trend / pie | 逐年 tce 柱 / 能源结构饼 | **2026-09-05 已修复：0.31/1.2143 等价口径，水不折标不进图**（旧版 0.1229 当量已废弃，历史报告中的旧图勿复用） | ✅ 与正文一致 |

- `flow` 的 energy_types 支持 electricity_kwh/water_m3/natural_gas_m3/
  heating_energy_heat_gj/petrol_kg/diesel_kg；equipment 可选（按 category 归类）。
- 图号按章连续递增，先正文引用后插图（图5.1 流向图、图5.2~5.N 各能源类型图表、
  最后 3 张连号为各年费用占比饼图）。

### 3. 附录追加（assemble 只生成 8 章；2026-09-03 起统一用 officecli，禁用 python-docx）

**工具**：`office_cli_command`（officecli）——与 ea-authoring 全链一致，python-docx 禁令无例外。
追加方式：对生成后的 docx 依次执行（只改 body，水印/TOC/页码域自动保留）。

**附录标题格式（对齐正式报告，2026-09-05 用户确认）**：

1. **附录总目录页**（第8章之后、各附录之前）：`附录：` 用 Heading 1 样式但 **宋体 12pt 不加粗**；其下逐条列 `附录N：<名称>`（Normal，宋体 12pt 不加粗）。
2. **各附录实际标题**：用 **Heading 2（宋体 14pt 加粗）**，文本 `附录N：<名称>`（**中文冒号**，不是空格）。

```bash
## 附录总目录页（第8章之后；Heading1 样式但显式降为宋体12pt不加粗）
officecli add report.docx /body --type paragraph --prop style=Heading1 --prop text="附录：" --prop size=12 --prop bold=false --prop font=宋体
officecli add report.docx /body --type paragraph --prop text="附录1：建筑基本信息及设备统计表"
officecli add report.docx /body --type paragraph --prop text="附录2：建筑能耗数据信息表"
## ... 逐条列出全部附录（按动态编号规则）

## 各附录标题（Heading2 样式 + 显式宋体14pt加粗，中文冒号）
officecli add report.docx /body --type paragraph --prop style=Heading2 --prop text="附录1：建筑基本信息及设备统计表" --prop size=14 --prop font=宋体
## 表格（N行M列）
officecli add report.docx /body --type table --prop rows=N --prop cols=M
officecli set report.docx '/body/table[K]/row[1]/cell[1]' --prop text="..."
officecli set report.docx '/body/table[K]/col[2]' --prop width=5cm
```

⚠ officecli **不支持 `--type heading`**（会报 Unknown element type）；标题一律 `--type paragraph --prop style=HeadingN` + 显式 `--prop size/font/bold`（模板默认样式如 Heading2=13pt 与规范 14pt 不符，必须显式覆盖）。

**附录清单（7 个，2026-09-05 用户确认；无发票时 6 个）**：

| 附录 | 内容 | 数据来源 |
|---|---|---|
| 附录1：建筑基本信息及设备统计表 | 建筑基本信息（18 字段）+ 设备统计（分系统设备表） | 引用正文表2.1 / 6.x + 说明 |
| 附录2：建筑能耗数据信息表 | 每年一张 7 列表：月份×水量(m³)/水费(元)/单价(元/m³)/电量(kWh)/电费(元)/单价(元/kWh)，12 月+合计行 | 逐月费用从 DB 拉取，**合计必须与正文主表费用一致**（report-qa 铁律） |
| 附录3：电费、水费、油费、燃气费充值发票 | 缴费发票照片（`proj.images` 分类'缴费发票'，caption 为"电费 1月~2月"等类型+期间，按 caption 前缀分组嵌入） | 发票照片采集自 ts_institution_energy_invoice+invoice_image 双表（2026-09-04 接入） |
| 附录4：室内环境测量表 | 室内温度/湿度/照度等实测数据表；**如有室内环境测量表的附件图片则展示** | `proj.indoor_env`（ts_institution_environment，取 deleted=0 且 room_name 合理的记录） |
| 附录5：空气质量判定方法 | 空气质量判定方法 A/B/C/D 表 | 标准固定表 |
| 附录6：室内空气质量指标及要求 | 空气质量指标限值表（GB/T 18883-2022） | 标准固定表 |
| 附录7：各种能源折标准煤参考系数 | 固定表：原煤0.7143/天然气1.2143/液化气1.7143/汽油1.4714/柴油1.4571/燃料油1.4286/电力0.31等价/热力0.03412当量 | 固定（权威值见 energy-audit-core/references/standards-values.md） |

**动态编号规则（2026-09-05 用户确认）**：若无发票相关附件照片，则**没有附录3**，后续附录序号依次前移（附录4→附录3、附录5→附录4、附录6→附录5、附录7→附录6），即无发票时共 6 个附录。编写时先查 `proj.images` 是否有'缴费发票'分类照片再定编号，全文引用的附录编号须与实际编号一致。

追加表格格式：Table Grid 样式、12pt 宋体居中、行高 1.01cm（officecli set 实现）。
无数据的附录列标题 + "待补充"，不编造。

### 4. 组装后数值断言（必做）

对 .docx 全文（段落+表格）做 40+ 项关键数值断言，与 DB 计算值逐一比对：
电量/水量/气量/热量/油量三年值、五项指标值（含供暖）、费用合计、同比率、定额三档值、
用能人数、建筑面积、热价。再扫残留占位符——"测试"命中先确认是否"水平衡测试"
等专业术语，"待补充"应为真实缺失数据（建筑外窗/保温/消防、附件等）。

### 5. 参照报告（RAG 库）

- 党政机关基准：`{HERMES_HOME}/rag/report/能源审计报告/公共机构/党政机关/`
  省贸促会能源审计报告0620.docx（定额三档值出处）
- **法院类最佳参照**：`.../党政机关/法院/省法院报告0620.docx`（8章+12附录完整结构、
  指标计算口径、第7章问题-措施6条对齐示例）
- 指标口径（省法院报告实证）：非供暖能耗=电×0.31 + 天然气×1.2143（热/油剔除）；
  常规电耗=总电量/面积；人均综合能耗=电+气+热(当量0.03412)+汽油(1.4714)全部计入；
  人均取水=水量/人数。信息中心无独立计量时按总电量口径核算并在 5.3 注明未剔除，
  勿编造剔除值；天然气无厨房分项时暂按全部计入并注明。

### 6. 定额值来源验证（硬要求）

- 正确三档值：非供暖能耗 25.5/16.6/9.6、电耗 81.0/52.0/35.5、人均综合能耗
  1611.5/1240.4/700.9 kgce/(p·a)、人均取水 先进10/通用25——以 energy-audit-core/references/standards-values.md（权威单点）
  与样例报告（省贸促会/省法院）为准。
- ⚠️ `tools/energy_audit/indicators.py` 内置 `_DEFAULT_BENCHMARKS['government']`
  =(12.8/8.8/6.0, 45/35/25, 800/600/400) 为**错误兜底值**，勿作对标依据。
- DB 无定额表（ts_energy_standard 仅折标系数）；省级规章（如烟台供暖期《烟台市
  供热管理办法》：市区 11月16日~次年3月31日）必须 web_search 验证后引用。

### 7. 审计机构信息

ts_register_dept（注册单位表）正式记录 2026-09-02 用户已改："同方德诚（山东）科技股份公司/山东省济南市历下区鲁商国奥城5号楼23楼/吕晓晗/15628998185"。名称/地址/负责人/
联系方式必须向用户提问确认（封面+三张信息表用），勿采用测试值；项目记录中
audit_dept_name 亦常为测试值。
