# 能源审计报告编写格式规范标准

> 基础来源：19份省直能源审计报告统计分析

## 一、页面设置

| 项目 | 规格 |
|------|------|
| 纸张 | A4 (210mm × 297mm) |
| 页边距 | 上下2.54cm，左右3.17cm |
| 页眉距页边界 | **1.50 cm** |
| 页脚距页边界 | **1.75 cm** |

### 页眉（内容 + 格式）

| 项目     | 内容                                             |
| -------- | ------------------------------------------------ |
| 文字内容 | `<被审计单位全称>  能源审计报告`（单位全称与"能源审计报告"间为两个空格，如"山东省高级人民法院  能源审计报告"） |
| 对齐     | **右对齐**                                       |
| 字体     | **宋体**，**10.5pt（五号）**，黑色，不加粗       |
| 行距     | 单倍行距                                         |
| 分隔线   | 页眉下方横线                                     |

**分隔线实现方法**（officecli 或 OOXML 二选一，交付前必验）：

```bash
# officecli：给页眉文字段落加底边线（颜色用 6 位 hex，不带 #；6 = 0.75pt 标准细线）
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

###  页脚（内容 + 格式）

| 项目                                    | 内容                                                         |
| --------------------------------------- | ------------------------------------------------------------ |
| 前置部分（第 1–3 节，封面/摘要/目录等） | **页脚空白，无页码**                                         |
| 正文部分（第 4 节及之后）               | **居中页码**，仅显示数字（`PAGE` 自动页码域，无“第 X 页”字样），页码编号从1开始 |
| 字体                                    | **9pt（小五）**，黑色，宋体                                  |
| 载体                                    | 页码置于一个**透明、无边框的浮动文本框**内，水平居中于版心   |



## 二、封面格式

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

参考文件： `references/audit-info-tables.md` 



## 三、目录

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

### 目录必须用 TOC 域生成（红线：禁止手写静态目录）

> ⚠️ **不要**手写目录条目（逐条敲「第1章 …」「1.1 …」）。手写目录是静态文本，页码不随正文更新，Word 也不视其为目录。**必须插入 TOC 域**，Word 打开后更新域自动生成。

**前置条件**：正文 H1/H2/H3 已应用 `Heading 1/2/3` 样式（见「四、正文标题」）。TOC 域默认按 Heading 样式（或大纲级别）收集。

**A. officecli**

```bash
officecli add report.docx /body --type toc --prop headingLevel=3
# headingLevel=3 = 收集到三级标题（H1/H2/H3）
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


## 四、正文标题

| 层级 | 字体 | 字号 | 加粗 | 对齐 |
|------|------|------|------|------|
| 一级（第X章） | **宋体** | 小三号(15pt) | 是 | **居中** |
| 二级（X.X） | **宋体** | 四号(14pt) | 是 | 左对齐 |
| 三级（X.X.X） | 宋体 | 12pt | 是 | 左对齐 |

### 大纲级别（红线：标题必须被识别为标题）

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
# 1) 改 Heading 样式定义（全文档该级标题统一生效，只做一次）
officecli set report.docx /style[Heading1] --prop font=宋体 --prop size=15 --prop bold=true --prop alignment=center --prop color=000000
officecli set report.docx /style[Heading2] --prop font=宋体 --prop size=14 --prop bold=true --prop color=000000
officecli set report.docx /style[Heading3] --prop font=宋体 --prop size=12 --prop bold=true --prop color=000000

# 2) 插入标题时应用对应样式（不要用默认 Normal）
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

## 五、正文段落

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

操作细则：`references/docx-first-line-indent.md`（`office_save` 之后、加水印之前，用 `office_cli_command` 批处理；禁止 python-docx）。

## 六、表格格式

| 元素 | 字体 | 字号 | 加粗 | 对齐 | 行高 |
|------|------|------|------|------|------|
| 表格标题 | 宋体 | 12pt（小四号） | 是 | 居中 | — |
| 表头 | 宋体 | 12pt | 是 | 居中 | 1.01cm exactly |
| 表格内容 | 宋体 | 12pt | 否 | 居中 | 1.01cm exactly |
| 垂直对齐 | — | — | — | center | — |

**列宽**：不加限制，让 Word 自动处理。

> 原19份报告统计：表格内容 10.5pt（五号）。用户纠正为：12pt（小四号）。

## 七、无序列表（1.6审计依据等）

- 用实心圆点 `● ` 前缀
- 12pt 宋体，无首行缩进

## 八、图片嵌入

- 宽度 12cm，居中
- 下方图注：10pt 宋体，居中

## 九、计量单位

格式：`数字 + 空格 + 单位`，如 `1234 tce`、`5678 kWh`

## 十、文字水印

- 内容：被审计单位全称（`proj.base.unit_name`）
- 位置：各节页眉，衬于文字下
- 形态：DrawingML，禁止 VML `textpath`
- 操作细则：`references/docx-watermark.md`

