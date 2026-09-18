# docx-techniques
> 本文并入 `docx-ooxml-techniques.md`、`docx-first-line-indent.md`、`docx-watermark.md`、`word-generation-tips.md`（2026-09-18 瘦身合并第 3 组，原文件已归档至 `_archive/2026-09-18/ea-authoring/references/`）；内容逐字保留，仅统一标题层级，引用请指向本文件对应小节。

---

## OOXML 排版技术（原 docx-ooxml-techniques）

> 基础来源：19份省直能源审计报告统计分析

### 一、页面设置

| 项目 | 规格 |
|------|------|
| 纸张 | A4 (210mm × 297mm) |
| 页边距 | 上下2.54cm，左右3.17cm |
| 页眉距页边界 | **1.50 cm** |
| 页脚距页边界 | **1.75 cm** |

#### 页眉（内容 + 格式）

| 项目     | 内容                                             |
| -------- | ------------------------------------------------ |
| 文字内容 | `<被审计单位全称>  能源审计报告`（单位全称与"能源审计报告"间为两个空格，如"山东省高级人民法院  能源审计报告"） |
| 对齐     | **右对齐**                                       |
| 字体     | **宋体**，**10.5pt（五号）**，黑色，不加粗       |
| 行距     | 单倍行距                                         |
| 分隔线   | 页眉下方横线                                     |

**分隔线实现方法**（officecli 或 OOXML 二选一，交付前必验）：

```bash
## officecli：给页眉文字段落加底边线（颜色用 6 位 hex，不带 #；6 = 0.75pt 标准细线）
officecli set <报告>.docx "/header/p[2]" --prop pbdr.bottom=single\;6\;000000
```

OOXML 校验标准（`word/header*.xml` 内页眉文字段落的 `w:pPr` 下必须有）：

```xml
<w:pBdr><w:bottom w:val="single" w:color="000000" w:sz="6" /></w:pBdr>
```

**页眉结构硬约束**：
- 页眉**只允许一个段落**（文字段落；水印 DrawingML 与其共存但为独立段落）。多段落会导致文字重复显示。
- `evenAndOddHeaders` 默认关闭；除封面节（页眉空白）外各节均引用同一个 default 页眉。
- 交付前自检：`officecli get <报告>.docx /header` 应显示单段落 + `pbdr.bottom=single`，文本无重复单位名。

**覆盖范围**：除“第 1 节的首页（封面页）页眉为空白”外，其余所有页面均显示上述页眉。

####  页脚（内容 + 格式）

| 项目                                    | 内容                                                         |
| --------------------------------------- | ------------------------------------------------------------ |
| 前置部分（第 1–3 节，封面/摘要/目录等） | **页脚空白，无页码**                                         |
| 正文部分（第 4 节及之后）               | **居中页码**，仅显示数字（`PAGE` 自动页码域，无“第 X 页”字样），页码编号从1开始 |
| 字体                                    | **9pt（小五）**，黑色，宋体                                  |
| 载体                                    | 页码置于一个**透明、无边框的浮动文本框**内，水平居中于版心   |



### 二、封面格式

| 元素 | 字体 | 字号 | 加粗 | 对齐 |
|------|------|------|------|------|
| 被审计单位名称 | 宋体 | 小初（36pt） | 是 | 居中 |
| "能源审计报告" | 宋体 | 小初（36pt） | 是 | 居中 |
| 审计机构名称 | 宋体 | 四号(14pt) | 是 | 居中（底部） |
| 报告日期 | 宋体 | 四号(14pt) | 是 | 居中（底部） |

日期格式：YYYY年M月

底部对齐方法：`para.paragraph_format.space_before = Pt(420)`

> 注意：要保证“被审计单位名称”、“能源审计报告”、“审计机构名称”、“报告日期”内容在一页。
>
> 当遇到单位名称字数过多的时候在  36pt 下必然换行（432pt>416pt），将其规范地拆为两行居中，如：（"烟台经济技术开发区"/"人民法院"），保持 36pt **小初字号**



**`能源审计基本信息表`**

参考文件： `energy-audit-core/references/conventions.md`《审计基本信息三张表的表结构》一节



### 三、目录

| 元素 | 字体 | 字号 | 加粗 | 对齐 |
|------|------|------|------|------|
| 目录标题 | 黑体 | 小二号(18pt) | 是 | 居中 |

- **字体**：黑体（中文）/ Times New Roman（英文）
- **字号**：18pt
- **颜色**：自动（黑色）
- **加粗**：是
- **对齐方式**：居中对齐
- **行距**：1.2倍行距
- **样式**：toc 1 或自定义目录样式

#### 目录必须用 TOC 域生成（红线：禁止手写静态目录）

> ⚠️ **不要**手写目录条目（逐条敲「第1章 …」「1.1 …」）。手写目录是静态文本，页码不随正文更新，Word 也不视其为目录。**必须插入 TOC 域**，Word 打开后更新域自动生成。

**前置条件**：正文 H1/H2/H3 已应用 `Heading 1/2/3` 样式（见「四、正文标题」）。TOC 域默认按 Heading 样式（或大纲级别）收集。

**A. officecli**

```bash
officecli add report.docx /body --type toc --prop headingLevel=3
## headingLevel=3 = 收集到三级标题（H1/H2/H3）
```

**B. python-docx —— 插入 TOC 域**

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

para = doc.add_paragraph()
run = para.add_run()
fld_begin = OxmlElement('w:fldChar'); fld_begin.set(qn('w:fldCharType'), 'begin')
instr = OxmlElement('w:instrText'); instr.set(qn('xml:space'), 'preserve')
instr.text = ' TOC \\o "1-3" \\h \\z \\u '   # \o=收集1-3级标题 \h=超链接 \u=按大纲级别
fld_sep = OxmlElement('w:fldChar'); fld_sep.set(qn('w:fldCharType'), 'separate')
t = OxmlElement('w:t'); t.text = '(打开后按 F9 更新目录)'
fld_end = OxmlElement('w:fldChar'); fld_end.set(qn('w:fldCharType'), 'end')
run._r.append(fld_begin); run._r.append(instr); run._r.append(fld_sep); run._r.append(t); run._r.append(fld_end)
```

**必须设置「打开时更新域」**（否则打开后目录仍是占位符，需手动 F9）：在 `word/settings.xml` 写入 `<w:updateFields w:val="true"/>`。

**验收**：
1. XML 中有 TOC 域（`<w:instrText> TOC \o "1-3" …`）。
2. `word/settings.xml` 含 `<w:updateFields w:val="true"/>`。
3. Word 打开 → 目录更新后列出全部 H1/H2/H3 标题及页码。


### 四、正文标题

| 层级 | 字体 | 字号 | 加粗 | 对齐 |
|------|------|------|------|------|
| 一级（第X章） | **宋体** | 小三号(15pt) | 是 | **居中** |
| 二级（X.X） | **宋体** | 四号(14pt) | 是 | 左对齐 |
| 三级（X.X.X） | 宋体 | 12pt | 是 | 左对齐 |

#### 大纲级别（红线：标题必须被识别为标题）

> ⚠️ **只设字体格式 ≠ 标题**。若 H1/H2/H3 只用 `Normal` 样式 + 手动字体/字号/加粗，而没有应用 `Heading 1/2/3` 段落样式、也没有 `w:outlineLvl`（大纲级别），则 Word 导航窗格不识别这些标题，**TOC 域无法收集它们**，目录无法通过域生成。

正确做法：每个标题段落**必须应用 Word 内置 Heading 样式**（写 `w:pStyle`），再覆盖字体格式为上面的规范外观。

| 标题 | 应用样式 | 大纲级别 | 需覆盖的默认外观 |
|------|---------|---------|-----------------|
| H1（第X章） | `Heading 1` | 1 级 | 默认蓝色 Calibri Light 左对齐 → 宋体 15pt 黑色加粗居中 |
| H2（X.X） | `Heading 2` | 2 级 | → 宋体 14pt 黑色加粗左对齐 |
| H3（X.X.X） | `Heading 3` | 3 级 | → 宋体 12pt 黑色加粗左对齐 |

两种实现方式（推荐 A：先改样式定义，一次生效全文档）：

**A. officecli —— 改样式定义 + 应用样式**

```bash
## 1) 改 Heading 样式定义（全文档该级标题统一生效，只做一次）
officecli set report.docx /style[Heading1] --prop font=宋体 --prop size=15 --prop bold=true --prop alignment=center --prop color=000000
officecli set report.docx /style[Heading2] --prop font=宋体 --prop size=14 --prop bold=true --prop color=000000
officecli set report.docx /style[Heading3] --prop font=宋体 --prop size=12 --prop bold=true --prop color=000000

## 2) 插入标题时应用对应样式（不要用默认 Normal）
officecli add report.docx /body --type heading --prop text="第1章 能源审计执行概要" --prop level=1
```

**B. python-docx —— 应用样式 + 直接格式覆盖**

```python
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

def add_heading(doc, text, level):
    p = doc.add_paragraph()
    p.style = doc.styles[f'Heading {level}']   # 关键：应用 Heading 样式 → 获得大纲级别
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    sizes = {1: (15, WD_ALIGN_PARAGRAPH.CENTER), 2: (14, None), 3: (12, None)}
    size, align = sizes[level]
    run.font.size = Pt(size)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)
    if align is not None:
        p.alignment = align
    return p
```

**兜底（仅在无法用 Heading 样式时）**：手动加 `w:outlineLvl`，配 TOC 域的 `\u` 开关也能被收集：

```python
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
pPr = p._p.get_or_add_pPr()
outlineLvl = OxmlElement('w:outlineLvl')
outlineLvl.set(qn('w:val'), str(level - 1))   # 0=H1, 1=H2, 2=H3
pPr.append(outlineLvl)
```

**验收**：

1. 抽查 H1/H2/H3：`p.style.name` 为 `Heading 1/2/3`，或 XML 含 `<w:pStyle w:val="Heading1"/>`（兜底则含 `<w:outlineLvl>`）。
2. Word「视图 → 导航窗格」能看到完整标题树。
3. 更新 TOC 域（F9）后目录能列出全部标题。

### 五、正文段落

| 属性 | 值 |
|------|-----|
| 中文字体 | 宋体 |
| 英文/数字字体 | Times New Roman |
| 字号 | 12pt（小四号） |
| 行距 | 1.5倍 |
| 首行缩进 | 2字符（仅正文自然段） |
| 对齐 | 两端对齐（JUSTIFY） |

**谁缩进 / 谁不缩进**

- **要**：各章叙述性正文自然段。
- **不要**：H1/H2/H3、封面、目录、表题、图注、表格单元格、§七无序列表、空段。

**换算**：12pt 下 2 字符 = **24pt = 480 twips**。OOXML 优先 `w:ind w:firstLineChars="200"`（百分之一字符，200 = 2 字符），并写 `w:firstLine="480"` 作回退。禁止用两个全角空格假装缩进。

操作细则：`references/docx-techniques.md`（`office_save` 之后、加水印之前，用 `office_cli_command` 批处理；禁止 python-docx）。

### 六、表格格式

| 元素 | 字体 | 字号 | 加粗 | 对齐 | 行高 |
|------|------|------|------|------|------|
| 表格标题 | 宋体 | 12pt（小四号） | 是 | 居中 | — |
| 表头 | 宋体 | 12pt | 是 | 居中 | 1.01cm exactly |
| 表格内容 | 宋体 | 12pt | 否 | 居中 | 1.01cm exactly |
| 垂直对齐 | — | — | — | center | — |

**列宽**：不加限制，让 Word 自动处理。

> 原19份报告统计：表格内容 10.5pt（五号）。用户纠正为：12pt（小四号）。

### 七、无序列表（1.6审计依据等）

- 用实心圆点 `● ` 前缀
- 12pt 宋体，无首行缩进

### 八、图片嵌入

- 宽度 12cm，居中
- 下方图注：10pt 宋体，居中

### 九、计量单位

格式：`数字 + 空格 + 单位`，如 `1234 tce`、`5678 kWh`

### 十、文字水印

- 内容：被审计单位全称（`proj.base.unit_name`）
- 位置：各节页眉，衬于文字下
- 形态：DrawingML，禁止 VML `textpath`
- 操作细则：`references/docx-techniques.md`

### 十一、md 导入与格式修复链（2026-09-06 定；**适用：office_editor 路径/存量报告**）

> **适用域（2026-09-17 定）**：本章修复链适用于 **office_editor 路径**（备用路径）产出的 docx 与存量报告定点修复。
> 新报告默认走**装配脚本链**（`energy-audit-report/references/script-assembly-chain.md`），脚本自带格式规范，无需本章修复链。

**背景**：正文写入由逐段 `doc_insert_paragraph_with_text` 改为 `doc_insert_markdown` 整章导入（几百次 MCP 往返 → 每章 1 次）。md 导入的默认样式 ≠ 格式规范，必须跑下面的修复链。

#### 11.1 导入规范

- 每章 1 次 `doc_insert_markdown`，idx 用 `doc_get_last_operable_pos().position`（卡2/卡3 接续编辑时同理，勿硬编码大数）
- 表格随 md 表格语法导入；大表（如第5章指标表、附录2能耗数据信息表）可用 `doc_insert_table_by_csv`
- 第5章直接导入 caliber 产出的 chapter5.md（不重写）
- 图片不随 md 导入，仍单独 `doc_insert_image`（宽度 12cm 居中，图注 10pt 宋体居中）

#### 11.2 格式修复链操作序列（每卡导入完成后统一跑，非脚本）

1. **定位**：`doc_get_outline` 拿全部标题（层级/位置）与表格位置
2. **标题修复**：对每个标题段 `doc_modify_paragraph`（`paragraph_style` = Heading 1/2/3，ranges 数组尽量批量）+ `doc_update_text_property`（ranges 数组批量设字体，一次调用覆盖多段，PoC 实测生效）：
   - H1：宋体 15pt 加粗 居中
   - H2：宋体 14pt 加粗
   - H3：宋体 12pt 加粗
3. **表格修复**：对每张表 `doc_set_table_properties`（边框全网格、对齐 center、垂直居中 cell_v_align=center）+ `doc_set_table_layout`（行高：**mode=manual + row_heights_dxa=[573,573,...]，1.01cm=573 twips/行**，col_widths_dxa 与 row_heights 同传；mode=auto 对已 100% 宽表格报空命令错，勿用）+ 表格字体 12pt 宋体走 `doc_update_text_property`（ranges 覆盖表格区间）；表头加粗。**注意 `doc_modify_paragraph` 定位用 ranges 数组，勿猜 paragraph_id**（PoC 实测 p_0 不存在）
4. **正文修复**：正文自然段 `doc_modify_paragraph`（`alignment`=两端对齐、`line_spacing_rule`+`line_spacing`=1.5 倍）
5. **首行缩进**：仍走 officecli 批处理（`docx-techniques.md`，firstLineChars=200），不在此链内

**⚠️ 公式段禁区（2026-09-16 实测）**：修复链的批量文字属性操作（`doc_update_text_property`）**必须跳过含数学公式的段落**——对含 `<m:oMath>` 的段落做文字属性/格式批处理，save 落盘时公式会被压平为纯文本（分式结构丢失：`E_jrcn=(E−Egn−Ejt)/M` → 纯文本「Ejrcn=E−Egn−EjtM」）。恢复方式：从同版式参考 docx 移植原生 `<m:oMath>` 元素（python-docx 手术式替换，禁止手写 OMML），或对该段重插 `doc_insert_math`；修复后不得再让任何文字属性操作覆盖该段。正文分段分类时请显式排除公式段。

#### 11.3 验收

1. Word「视图 → 导航窗格」标题树完整（H1/H2/H3 层级正确）
2. 表格：12pt 宋体居中、行高 1.01cm、垂直居中（抽查 2~3 张）
3. V3 格式检查通过 + 正式报告对照（PoC 阶段逐项比对）
4. 红线不触：本链是 author 调用 office_editor 工具的**固定操作序列**，不是脚本生成正文（红线4）；禁止 python-docx（**适用域 = office_editor 路径内**，2026-09-17 方案确认；脚本装配链不受限）

**⚠️ 渲染陷阱（2026-09-06 PoC 实测）**：`office_render` / `office_preview` 渲染的是**磁盘保存状态**，未 `office_save` 前渲染输出纯白页。凡需渲染验证（视觉检查/V3 预览），必须先 `office_save` 再 render，否则误判文档为空。

**⚠️ 插图锚点坑（2026-09-07 PoC 实测，3 条铁律）**：

1. `doc_insert_image(idx=标题begin)` 会把图片 inline 插进标题段落内部——标题文本被截断（"5.2"变".2"，V3 检出缺章/异常标题）。插图后**立即** `doc_insert_paragraph(idx=图片index+1)` 拆分段落，图片即独立成段；若标题已截断，用 `doc_find_and_replace` 补回残缺标题文本（残体".2 能源…"→"5.2 能源…"）。
2. **任何写操作后旧 idx 全部失效**：插入图片/段落/图注都会膨胀文档，后续 `doc_insert_markdown`/`doc_insert_image` 的 idx 必须重新 `doc_get_last_operable_pos` 或重新 `doc_find`。用"插图前拿的锚点位置"去插下一段 = 内容错位（PoC 曾致第6章整章插进表5.8 中间，被迫全量删除重导）。
3. 图片在图注段前插入时同样会被 inline 并入图注段——图后插段落符拆分，或图注用 `doc_insert_paragraph_with_text(idx=图片位置)` 紧跟图片段后插入。
4. 批量插图时**从后往前**（锚点位置大的先插），或每插一张图立即拆分+重找锚点，避免位置漂移。

**⚠️ 致命坑：`doc_update_text_property` 范围跨越表格时，save 导出会复制内容（2026-09-07 实验复现）**：

- 症状：编辑器内存态干净（doc_find 每文本 1 处），但 office_save 落盘的 XML 里表格及后续内容被复制 3-7 份（"第5章"13 次、"峰值特征显著"5 次），文档从 48 页膨胀到 165 页，V3 检测到内容重复。
- 触发条件（最小复现）：含表格 md 导入 → `doc_update_text_property` ranges **跨越表格**（如全文 0~END 设 12pt）→ save。仅 `doc_set_table_layout` 或标题级 ranges 不含表格时**不触发**。
- 铁律：**editor_sdk 内所有 `doc_update_text_property` 的 ranges 必须只覆盖非表格区域**（标题段、独立正文段）。全文正文字号统一改用 **python-docx 后处理**（save 落盘后打开 docx，遍历 body 段落+表格 run 设字号，天然避开编辑器导出 bug）。
- 注意：python-docx 后处理后再回 editor_sdk 编辑会使内存态与磁盘失同步（office_render 报"服务器运行失败"）——**python-docx 后处理必须是最后一步**，之后渲染用 Word COM 路径（docx-render-verify 技能 render_word_pdf.ps1），不用 office_render。
- 验证手段：解包 docx 读 word/document.xml，`count('关键短语')` 应各为 1；页数用 Word COM 转 PDF + fitz 核对（正文 8 章约 28 页，加附录约 48 页）。

---

## 正文首行缩进 2 字符（原 docx-first-line-indent）

SOUL 红线：落盘后、加水印前，必须给**正文自然段**加上首行缩进 2 字符；无缩进视为未完成交付。

本文件只回答三件事：**何时设、给谁设、怎么设**。全程用 **office 工具**（`office_cli_command` / `office_edit`）。

---

### 何时设

- **一次、全文写完并第一次正式 `office_save` 之后立刻做，再加水印。**
- 写作过程中若用 officecli 插入正文，可当时带上缩进属性（见下「写作时」）；仍须在落盘后做一次全文核对，补漏段。
- 不要用两个全角空格、`\u3000\u3000` 或段首空格假装缩进。
- 打开已有报告补交时：用 `office_cli_command` 抽查正文段，没有 `firstLineChars=200` 就补设。

推荐顺序：

```
office_create → 逐章 office_edit（或 office_cli_command add）
  → office_save 到交付路径
  → office_cli_command：筛正文段并 set firstLineChars=200
  → 加水印（见 docx-techniques.md）
  → office_preview
```

---

### 给谁设 / 不给谁设

只处理**各章正文自然段**。不是文档里每一个段落。

| 类别 | 是否缩进 | 判定（看 `officecli get` 的 `text` / `style` / `format`） |
|------|----------|------|
| 各章叙述性正文 | **要** | 非空；`style` 不是 Heading/标题/TOC/List；非居中/右对齐 |
| H1 / H2 / H3 | 不要 | `style` 含 Heading/标题；或「第X章」；或 `1.1` / `1.1.1` 且加粗；或 `size` ≥ 14pt |
| 封面、目录标题 | 不要 | 居中；「能源审计报告」「目录」 |
| 表题、图注 | 不要 | `align=center`；文本以 `表2-1` / `图2-1` 开头 |
| 表格单元格 | 不要 | 路径在 `tbl` 下。只处理 `/body` 的直接子段落，不要 `query paragraph` 全表 |
| 无序列表（1.6 等） | 不要 | 文本以 `●` / `•` / `·` / `○` 开头，或已有 `hangingIndent` / `listStyle` |
| 空段、封面 spacer | 不要 | 无可见文本 |

换算（12pt 小四号）：

- 2 字符 = OOXML `w:ind @w:firstLineChars="200"`（百分之一字符）
- 回退长度：`firstLineIndent=24pt`（24pt = 2 × 12pt）

officecli 属性名（已核实）：

| 属性 | 值 | 说明 |
|------|----|------|
| `firstLineChars` | `200` | **主属性**，字符相对缩进 |
| `firstLineIndent` | `24pt` | 长度回退，与上一行一起设 |

---

### 怎么设（office 工具）

#### 写作时（插入正文段）

**officecli 插入**（`office_cli_command`）：

```text
officecli add "<交付路径>" /body --type paragraph --prop text="……" --prop align=justify --prop lineSpacing=1.5x --prop size=12pt --prop font.ea=宋体 --prop font.latin="Times New Roman" --prop firstLineChars=200 --prop firstLineIndent=24pt
```

标题、表题、图注、列表 **不要**带 `firstLineChars`。

**`office_edit`（editor_sdk）插入**：`doc_insert_paragraph_with_text` 默认无首行缩进。插入时若 `office_list_tools` 能找到段落缩进参数就带上；**找不到不要用正文空格凑**。无论插段时带没带上，落盘后都必须走下面的全文补设。

#### 落盘后全文补设（强制）

文件必须已经 `office_save` 到交付路径。全部命令走 **`office_cli_command`**（`command` 以 `officecli` 开头）。优先用稳定路径 `/body/p[@paraId=…]`，不要用会随插入漂移的 `/body/p[N]`。

**1. 列出正文级段落（不含单元格）**

```text
officecli get "<交付路径>" /body --depth 1 --json
```

只看 `type=paragraph` 的直接子节点。忽略 `type=table` / `type=section`。

**2. 按「给谁设」过滤**，得到要改的 `path` 列表。一条都没有 → 停止交付，检查判定。

**3. 批量写入**（推荐 `--input`，避免命令行转义）：

`indent-batch.json` 示例：

```json
[
  {
    "command": "set",
    "path": "/body/p[@paraId=00100002]",
    "props": {
      "firstLineChars": "200",
      "firstLineIndent": "24pt"
    }
  }
]
```

```text
officecli batch "<交付路径>" --input "<indent-batch.json 的绝对路径>" --json
officecli save "<交付路径>"
```

段数很少时可以逐条：

```text
officecli set "<交付路径>" "/body/p[@paraId=00100002]" --prop firstLineChars=200 --prop firstLineIndent=24pt --json
```

**4. 抽查**

```text
officecli get "<交付路径>" "/body/p[@paraId=<正文段>]" --json
```

`format.firstLineChars` 应为 `200`。再抽一条 H1/表题/列表，确认 **没有** `firstLineChars`。

---

### 验收

1. 抽 3 段各章叙述正文：`officecli get` 的 `format.firstLineChars` 为 `200`（可同时有 `firstLineIndent=24pt`）。
2. 抽 H1「第X章」、H2/H3、`表N-` / `图N-`、`● ` 列表、任一单元格：这些段落 **没有** 首行缩进。
3. 正文里没有段首全角空格冒充缩进。
4. `office_preview` 正文首行明显缩进约两字，标题仍顶格。

任一失败 = 未完成交付，修好后再交。

---

## 项目名称水印（原 docx-watermark）

SOUL 红线：落盘前必须有文字水印，内容为被审计单位名称；无水印视为未完成交付。

本文件只回答三件事：**何时加、加在哪、怎么加才兼容 OnlyOffice**。

---

### 何时加

- **一次、全文写完之后、第一次正式 `office_save` 之后立刻做。**
- 不要在第 1～8 章写作过程中反复加。
- 不要在封面/目录写完就加（后续 `office_edit` 可能重建节/页眉，水印会被冲掉）。
- 打开已有报告补交时：若页眉没有 DrawingML 水印，补加后再 `office_save`。

推荐顺序：

```
office_create → 逐章 office_edit → office_save 到交付路径
  → office_cli_command 正文首行缩进 2 字符（见 docx-techniques.md）
  → execute_code 给该 .docx 注入水印（原地覆盖）
  → office_preview / 抽查 header*.xml
```

`office_editor` **没有**水印 MCP 操作，不要用 `office_edit` 往正文插入灰色大字冒充水印。

---

### 加在哪

| 项 | 规定 |
|----|------|
| 位置 | **每个节的页眉**（`section.header`；若启用首页不同/奇偶页不同，还要写 `first_page_header`、`even_page_header`） |
| OOXML | 页眉里的 **DrawingML** `w:drawing` → `wp:anchor behindDoc="1"`（衬于文字下、页面水平/垂直居中） |
| 文案 | `proj.base.unit_name`（被审计单位全称）。**不要用** `proj.base.name`（带「能源审计」后缀） |
| 空值 | `unit_name` 为空时用任务里的项目名称；再没有则停下来补数据，禁止写「WATERMARK」占位 |
| 外观 | 浅灰 `#C0C0C0`、宋体、斜向约 45°、半透明观感靠浅色实现；不挡正文阅读 |

覆盖范围：封面、目录、正文所有页。页眉注入一次即可随节应用到各页。

---

### 怎么加才兼容 OnlyOffice

OnlyOffice 对 Word 经典水印（VML WordArt）支持差：导入常不显示，再保存会把 Word/WPS 里的水印弄丢。

| 做法 | Word | OnlyOffice | WPS | 结论 |
|------|------|------------|-----|------|
| VML `w:pict` + `v:shape` + `v:textpath` | 设计→水印的默认形态 | 经常不显示 | 往返易错 | **禁止** |
| DrawingML 页眉形状/文本框（`wp:anchor` + `wps:wsp`） | 能显示 | 一般能显示 | 一般能显示 | **默认采用** |
| DrawingML 页眉图片（浅色斜字 PNG） | 稳 | 最稳 | 稳 | 文本框在 OO 仍看不见时的回退 |
| OnlyOffice `InsertWatermark` / `watermark_on_draw` | 不保证写进 docx | 仅 OO 会话 | — | author 不用（走 office_editor，不是 OO API） |
| 正文灰色大字 | 会占排版 | 能看见但不是水印 | 会破坏格式 | **禁止** |

硬规则：

1. 禁止生成或保留 `v:textpath` / `v:shapetype` 水印。
2. 必须写入 `word/header*.xml` 的 `w:drawing`，且 `behindDoc="1"`。
3. 不要依赖 Word「设计 → 水印」菜单语义；OnlyOffice 的「删除水印」也识别不到这种对象，这是预期。

---

### 实现（execute_code + python-docx）

对已经 `office_save` 的交付文件原地写入。`unit_name` 含 `& < >` 时必须 XML 转义。

```python
import html
from pathlib import Path
from docx import Document
from docx.oxml import parse_xml

def _watermark_paragraph_xml(text: str, doc_pr_id: int) -> str:
    safe = html.escape(text, quote=True)
    size = "88" if len(text) <= 12 else "56"  # 半磅：88=44pt
    return f'''
<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
     xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
     xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
     xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
  <w:r>
    <w:drawing>
      <wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0"
                 relativeHeight="251658240" behindDoc="1" locked="0"
                 layoutInCell="1" allowOverlap="1">
        <wp:simplePos x="0" y="0"/>
        <wp:positionH relativeFrom="page"><wp:align>center</wp:align></wp:positionH>
        <wp:positionV relativeFrom="page"><wp:align>center</wp:align></wp:positionV>
        <wp:extent cx="5486400" cy="2194560"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:wrapNone/>
        <wp:docPr id="{doc_pr_id}" name="EAWatermark"/>
        <wp:cNvGraphicFramePr>
          <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
        </wp:cNvGraphicFramePr>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">
            <wps:wsp>
              <wps:cNvSpPr txBox="1"/>
              <wps:spPr>
                <a:xfrm rot="2700000">
                  <a:off x="0" y="0"/>
                  <a:ext cx="5486400" cy="2194560"/>
                </a:xfrm>
                <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
                <a:noFill/>
                <a:ln><a:noFill/></a:ln>
              </wps:spPr>
              <wps:txbx>
                <w:txbxContent>
                  <w:p>
                    <w:pPr><w:jc w:val="center"/></w:pPr>
                    <w:r>
                      <w:rPr>
                        <w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/>
                        <w:sz w:val="{size}"/>
                        <w:szCs w:val="{size}"/>
                        <w:color w:val="C0C0C0"/>
                      </w:rPr>
                      <w:t>{safe}</w:t>
                    </w:r>
                  </w:p>
                </w:txbxContent>
              </wps:txbx>
              <wps:bodyPr wrap="none" fromWordArt="0"><a:noAutofit/></wps:bodyPr>
            </wps:wsp>
          </a:graphicData>
        </a:graphic>
      </wp:anchor>
    </w:drawing>
  </w:r>
</w:p>'''

def add_unit_name_watermark(docx_path: str, unit_name: str) -> None:
    if not (unit_name or "").strip():
        raise ValueError("水印文案为空：需要 proj.base.unit_name")
    doc = Document(docx_path)
    n = 1
    for section in doc.sections:
        headers = [section.header]
        if section.different_first_page_header_footer:
            headers.append(section.first_page_header)
        if section.even_page_header is not None:
            headers.append(section.even_page_header)
        for header in headers:
            xml = header._element.xml
            if "EAWatermark" in xml or 'name="Watermark"' in xml:
                if "v:textpath" in xml:
                    raise RuntimeError("页眉含 VML textpath，禁止交付；改为 DrawingML 后重试")
                continue
            header._element.append(parse_xml(_watermark_paragraph_xml(unit_name.strip(), n)))
            n += 1
    doc.save(docx_path)

## add_unit_name_watermark(r"<交付路径>", proj.base.unit_name)
```

若 OnlyOffice 预览仍看不见：用 PIL 把同一文案做成浅灰斜字透明 PNG，再作为 DrawingML **图片**插入同一页眉位置（仍禁止 VML）。

---

### 验收

落盘后抽查（可用 `zipfile` 读包，不必 Word）：

1. `word/header*.xml` 中有 `w:drawing` 且 `behindDoc="1"`。
2. 全包内 **没有** `v:textpath`。
3. 水印字符串等于 `proj.base.unit_name`，不是 `proj.base.name`。
4. `office_preview` 正文可正常阅读，水印在文字下方。

任一失败 = 未完成交付，修好后再交。

---

## Word 报告生成注意事项与编辑安全（原 word-generation-tips）

### 封面底部对齐

使用 spacer 段落 + `space_after` 将审计机构和日期推到页面底部：

```python
spacer = doc.add_paragraph()
spacer.paragraph_format.space_after = Pt(460)  # ~162mm
```

A4 可用高度 246mm，36pt 标题偏移 + 460pt spacer 确保底部信息靠近下边缘。

### 中文字体设置

 使用office工具分别设置西文和中文字体：

```
"Times New Roman"        # 西文
"宋体"                    # 中文
```

### 中文字体验证

`run.font.name` 只返回西文字体。验证中文字体需检查 XML：

```python
from lxml import etree
xml = etree.tostring(run._element, encoding='unicode')
## 检查 w:eastAsia 属性
```

### 正文首行缩进

落盘后、加水印前，必须给正文自然段加上首行缩进 2 字符。用 `office_cli_command`（officecli `set` / `batch`，属性 `firstLineChars=200`）。细则见 `references/docx-techniques.md`。

### 项目名称水印

落盘前必须加水印。何时加、加在哪、OnlyOffice 兼容做法见 `references/docx-techniques.md`。

### 格式规范来源

`energy-audit-core/references/report-format-spec.md` — 基于 19 份省直能源审计报告分析总结。

### 编辑安全：patch 的 replace_all 禁用于批量改编号（2026-07-02 事故）

曾用 `patch(replace_all=True)` 把"表5.3~表5.8"批量改成动态表号，结果 4 个不同表题被替换成同一字符串，损失约 30 分钟逐个修回。

1. `replace_all=True` 只用于**确实所有匹配都应替换成相同内容**的场景；
2. 批量编号用 `变量 + offset` 在生成时算好，不靠事后替换；
3. 受影响行多于 3 行时，直接整段重写比逐条替换更安全。

> 原文件 `patch-replace-all-danger.md` 已归档至 `_archive/2026-09-17/energy-audit-core/references/`。
