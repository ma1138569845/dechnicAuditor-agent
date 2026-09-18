# docx-tools
> 本文并入 `omml-formula-guide.md`、`officecli-guide.md`（2026-09-18 瘦身合并第 3 组，原文件已归档至 `_archive/2026-09-18/ea-authoring/references/`）；内容逐字保留，仅统一标题层级，引用请指向本文件对应小节。

---

## OMML 公式（原 omml-formula-guide）

> 第5章 5.3 各指标段需要呈现计算公式（Word 数学公式对象，分式+下标渲染）。

### 方案选择（按优先级，2026-09-06 定）

| 方案 | 适用 | 说明 |
|------|------|------|
| **A. office_edit `doc_insert_math`（唯一首选）** | 报告生成流程中的 5.3 全部公式 | 引擎 C++ 层把 LaTeX 解析为 OMML，结构保证 Word 识别；经实测渲染为正常公式样式 |
| B. `_archive/2026-09-18/energy-audit-report/scripts/fix_chapter5_formulas.py` 脚本 | **仅存量报告**后处理（已含文本公式的旧 docx） | zip+lxml 注入，需自行保证 xmlns:m 声明正确；新报告不得走此路径 |
| C. OfficeCLI equation | 无分式的简单式子 | 不支持分式（\frac 不解析、/ 不转 m:f，实测 m:f=0），5.3 公式禁用 |

**默认用方案 A**：在 author 写第5章 5.3 各指标段时，直接用 office_edit 工具集调用
`doc_insert_math` 插入公式（LaTeX 参数，见下表）。**不用**：
- 纯文本公式行（"Ejrcn=（E−Egn−Ejt）/M"）——非数学对象，Word 不渲染为公式样式，2026-09-06 起废除
- 事后 zip+lxml 注入（缺根 xmlns:m 声明时 Word 静默按普通文本渲染；声明写法错误时 Word 直接拒开）
- 截图/图片公式（模糊、不可检索、格式校验不过）

### 符号定义段（"式中"）的下标处理（2026-09-06 定）

公式对象（`doc_insert_math`）只覆盖分式本身。**定义段/符号段里的变量符号**（如 `Ejrcn——单位建筑面积非供暖能耗，……；E——综合能耗……`）也要有下标：

- 正式报告样式（省人社厅0620 实测）：变量主体**正体**、下标部分用 **Word 下标格式**（w:vertAlign subscript），**不用 oMath**（oMath 会把变量渲染成数学斜体，与正式版不一致）。
- 实现：文本照常写入后，用 `doc_update_text_property` 对下标部分设 `vertical_align: "subscript"`：
  ```json
  office_edit(file_id=…, operation="doc_update_text_property",
    arguments={"ranges": [{"begin": 下标起点, "end": 下标终点}], "vertical_align": "subscript"})
  ```
- 下标范围定位：先 `doc_find`（`text="Egn——"` 等含下标符号+破折号串）拿 begin/end，下标部分 = begin+1 .. end-2（去掉主体首字符与"——"）。多匹配时按 `related_text` 上下文区分。
- **下标清单**（第5章全部）：Ejrcn→jrcn、Egn→gn、Ejt→jt、Eja→ja、ED→D、Er→r、Vuc→uc、Vk→k、Np→p、Egnm→gnm、Mgn→gn（高校 Vu/Nu、Ws/Ns、医院 Vz/Ni、政务 Vui/Nc 同理：变量名主体之外的全小写部分设下标）。
- 验证：渲染 PDF 后按 y 坐标比对——下标字符 y0 应比同行正文低约 4-5pt（fitz `search_for` 拿 rect），不得只凭"操作成功"下结论。

### doc_insert_math 调用方式

```json
office_edit(
  file_id=<报告 file_id>,
  operation="doc_insert_math",
  arguments={"idx": <段落结束位置，来自 doc_get_last_operable_pos 或上一写操作返回值>, "latex": "<LaTeX>"}
)
```

- idx 是 DOC 坐标，必须来自查询结果或上一次写操作返回值，勿按肉眼字符数/段落序号手算。
- 公式插入前先把"符号+中文定义"文本段（`Ejrcn——单位建筑面积非供暖能耗，……；`）照常写入，
  公式对象插在定义段之前或之后（与正式报告版式一致处）。
- 变量符号定义段仍用正文格式：变量符号 Times New Roman 斜体、中文定义与单位宋体 12pt；
  单位写法不加括号（`kgce/(m²·a)`，报告铁律）。

### 第5章公式清单（LaTeX 写法 + 符号与正式版一致）

| 指标 | LaTeX（doc_insert_math 用） | 变量 |
|------|------|------|
| 单位建筑面积非供暖能耗 5.3.1 | `E_{jrcn}=\frac{E-E_{gn}-E_{jt}}{M}` | E 综合能耗 kgce/a；Egn 供暖能耗；Ejt 交通能耗；M 建筑面积 m² |
| 常规用能系统单位建筑面积电耗 5.3.2 | `E_{ja}=\frac{E_{D}}{M}` | ED 电量总和 kWh/a（已剔供暖电耗）；M 建筑面积 |
| 人均综合能耗 5.3.3 | `E_{r}=\frac{E}{P}` | E 综合能耗 kgce/a；P 用能人数 p |
| 取水指标 5.3.4（按机构类型自适应，DB37/T 4452-2021） | 机关(7)：`V_{uc}=\frac{V_{k}}{N_{p}}`（m³/(人·a)）<br>高校(3)：`V_{u}=\frac{W_{u}}{N_{u}}`（Nu=统招生+留学生+0.5×教职工）<br>中小学/幼儿园(4)：`V_{s}=\frac{W_{u}}{N_{s}}`（Ns=非住宿生+2×住宿生+教职工）<br>医院(5)：`V_{z}=\frac{W_{z}}{\sum_{i=1}^{365}N_{i}}\times10^{3}`（L/(床·日)，ΣNi=全年实际开放床日数）<br>政务/场馆(6)：`V_{ui}=\frac{V_{j}}{N_{c}}\times1000`（L/(m²·a)） | 变量定义见 energy-audit-core/references/standards-values.md；不对标：政务/场馆（4452 无面积定额） |
| 单位采暖建筑面积供暖能耗 5.3.5 | `E_{gnm}=\frac{E_{gn}}{M_{gn}}` | Egn 供暖能耗 kgce/a；Mgn 采暖建筑面积 m² |

> 变量符号（Ejrcn/Eja/Er/Vuc/Egnm + 取水按类型 Vuc/Vu/Vs/Vz/Vui）以正式报告与 DB37/T 4452-2021 为准（2026-09-05 用户确认对齐；2026-09-05 晚按烟台法院正式版勘误：5.3.1=Ejrcn、5.3.2=Eja，此前 Ejfgn/Ejd 为误记）；报告中的符号不可自行改名。

### 方案 B：存量报告后处理（_archive/2026-09-18/energy-audit-report/scripts/fix_chapter5_formulas.py）

仅用于修复**历史生成的报告**（5.3 还是文本公式的旧 docx）：

```bash
python skills/energy-audit/energy-audit-report/_archive/2026-09-18/energy-audit-report/scripts/_archive/2026-09-18/energy-audit-report/scripts/fix_chapter5_formulas.py <报告.docx> [--dry-run]
```

⚠ 该脚本历史上存在两类失败（2026-09-06 实测定位）：
1. 根元素用字符串/伪 QName 注入 `xmlns:m` → 生成 `ns0:m` 伪装属性 → **Word 拒开文件**；
2. 不声明 m 前缀（ns0/ns1 局部前缀）→ Word 能打开但**公式按普通文本渲染，不显示公式样式**。
正确声明方式（lxml）：序列化前 `etree.register_namespace('m', M_NS)`。
新报告一律走方案 A，不要依赖本脚本。

### 验证（必做）

1. `office_render(file_id, format="png")` 渲染后**必须视觉复核**渲染图（vision 不可用时让用户看图确认或对比引擎原生公式 docx），确认公式为分式+下标样式，而非文本/乱码。
2. 结构化抽查：解包 docx，公式段落应含 `m:oMath`（或 `m:oMathPara`）+ document.xml 根元素 `xmlns:m` 声明（doc_insert_math 自动满足）。
3. 渲染异常时：先用 `doc_insert_math` 重插（勿手动修 XML），仍异常则报告阻塞，不得交付未验证的公式。

### 附录：引擎原生 OMML 结构（参考，勿手写）

doc_insert_math 生成的公式（formula_ref 实测）结构特征：
根元素声明 `xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"`；
`w:p` 内直接 `m:oMath`；每个 `m:r` 含 `<m:rPr/><w:rPr/>`；`m:sSub` 含 `<m:sSubPr/>`；
`m:f` 含 `<m:fPr/>`；settings.xml 含 `m:mathPr`/`m:mathFont=Cambria Math`。
手写 OMML 若缺上述空元素与根声明，Word 可能拒开或按纯文本渲染——所以**一律走 doc_insert_math，不手写**。

---

## officecli 集成（原 officecli-guide）

### 概述

[OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) 是专为 AI Agent 设计的 Office 套件 CLI。单二进制、无需安装 Office、Apache 2.0 开源，支持 Word/Excel/PowerPoint 三件套。

相比 Hermes 内置的 `docx` (npm) skill 和当前项目用的 `python-docx`，核心优势：

| 功能 | python-docx (当前方案) | OfficeCLI |
|------|:---------------------:|:---------:|
| 公式 | ❌ 需手写 OMML XML (见 `docx-tools.md`) | ✅ **LaTeX 输入** — 一行命令 |
| 目录 | ✅ 但 TOC 字段复杂 | ✅ 原生支持 |
| 页眉/页脚/页码 | ✅ 但需三处同步设 | ✅ 原生支持 |
| 表格合并单元格 | ⚠️ 需 XML 操作 | ✅ 原生 |
| 实时预览 | ❌ 需转 PDF → 看图 | ✅ `officecli watch` 浏览器实时渲染 |
| 校验 | ❌ | ✅ `officecli validate` 内置质检 |
| 模板合并 | ❌ 需代码 | ✅ `officecli merge` |
| Word/Excel/PPT | ❌ 只有 Word | ✅ 全支持同一个二进制 |

**结论**：对能源审计报告批量生成场景，OfficeCLI 比 python-docx 更省时间。

### 安装

#### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex
```

#### 验证

```bash
officecli --version
officecli --help
```

### 技术原理

OfficeCLI 是 .NET 10 自包含编译的单二进制（无需 .NET 运行时）。通过 Resident Mode 连接到文档进程，命令实时生效：

```
Agent → officecli create/add/set/get/merge → 内存中修改 → officecli close 写盘
```

Agent 调用模式（Python SDK 或 subprocess）：

```python
import json, subprocess
def oc(*args):
    return json.loads(subprocess.check_output(['officecli', *args, '--json'], text=True))

## 创建文档
oc('create', 'report.docx')

## 设置页眉（文字 + 分隔线；单位全称替换为实际名称）
oc('set', 'report.docx', '/header/default', '--prop', 'text=<被审计单位全称>  能源审计报告', '--prop', 'font=宋体', '--prop', 'size=10.5', '--prop', 'align=right')
oc('set', 'report.docx', '/header/p[1]', '--prop', 'pbdr.bottom=single;6;000000')

## 添加公式
oc('add', 'report.docx', '/body', '--type', 'equation',
   '--prop', 'latex=E_{jrcn} = \\frac{E - E_{gn} - E_{jt}}{M}')

## 插入目录
oc('add', 'report.docx', '/body', '--type', 'toc')

## 关闭
oc('close', 'report.docx')
```

### Word 常用操作速查

#### 创建文档 + 页眉页脚

```bash
## 创建
officecli create report.docx

## 页眉（首页不同 + 奇偶页不同可选；对齐右对齐，单位全称替换为实际名称）
officecli set report.docx /header/default --prop text="<被审计单位全称>  能源审计报告" --prop font=宋体 --prop size=10.5 --prop align=right
## 页眉分隔线（pbdr.bottom；颜色 6 位 hex 不带 #，6=0.75pt）
officecli set report.docx /header/p[1] --prop pbdr.bottom=single\;6\;000000

## 页脚 + 页码（仅 PAGE 域数字，居中；不再写"第 X 页 共 Y 页"）
officecli set report.docx /footer/default --prop text="" --prop font=宋体 --prop size=10.5
officecli add report.docx /footer/default --type pageNumber

## 页码从正文开始（封面无页码）
officecli set report.docx /sectPr --prop titlePg=true
```

#### 标题样式与目录

```bash
## 设置 H1、H2 样式（匹配格式规范）
officecli set report.docx /style[Heading1] --prop font=宋体 --prop size=15 --prop bold=true --prop alignment=center
officecli set report.docx /style[Heading2] --prop font=宋体 --prop size=14 --prop bold=true

## 插入目录
officecli add report.docx /body --type toc --prop headingLevel=3
```

#### 公式（LaTeX 输入 → 自动 OMML）

```bash
## 一行命令，LaTeX 语法
officecli add report.docx /body --type equation \
  --prop latex="E_{jrcn} = \frac{E - E_{gn} - E_{jt}}{M}"

## 公式符号说明（普通段落）
officecli add report.docx /body --type paragraph \
  --prop text="式中：E_jrcn——单位建筑面积非供暖能耗(kgce/m²)"
```

#### 表格

```bash
## 3列4行表格
officecli add report.docx /body --type table --prop rows=4 --prop cols=3

## 设置列宽
officecli set report.docx '/body/table[1]/col[1]' --prop width=3cm
officecli set report.docx '/body/table[1]/col[2]' --prop width=5cm

## 单元格赋值
officecli set report.docx '/body/table[1]/row[1]/cell[1]' --prop text="建筑名称"
officecli set report.docx '/body/table[1]/row[2]/cell[1]' --prop text="综合楼"

## 合并单元格
officecli set report.docx '/body/table[1]/row[1]/cell[1]' --prop hMerge=3
```

#### 实时预览

```bash
## 打开浏览器实时预览（watch 模式）
officecli watch report.docx

## 然后在另一个终端修改——浏览器自动刷新
```

#### 模板合并（批量报告）

先做一个模板 docx（含 `{{building_name}}` 等占位符），一次渲染多份报告：

```bash
officecli merge template.docx output-batch/ --data reports.json
```

`reports.json` 格式：

```json
[
  {"building_name": "综合楼", "area": 12000},
  {"building_name": "门诊楼", "area": 8000}
]
```

### 与 python-docx 的切换策略

报告正文写作已全面转向 LLM + office_editor（officecli 回退），python-docx 仅存在于仿写脚本（assemble_report.py 等工具内部实现）。涉及 docx 编辑的手工操作一律 officecli：

#### A) 渐进式替换（推荐）

Step 7 保持 python-docx，但将**公式**和**表格**部分改为调 OfficeCLI subprocess 注入 OMML。公式部分可用 OfficeCLI 的 LaTeX 替代当前的 `_add_formula()` 手工 OMML XML。

```python
import subprocess, json

def add_equation(officecli_path, docx_path, latex):
    """用 OfficeCLI 注入公式，替代 OMML XML 手写"""
    subprocess.run([
        'officecli', 'add', docx_path, '/body',
        '--type', 'equation',
        '--prop', f'latex={latex}'
    ], check=True)
```

#### B) 全量重写（当前已定型）

报告 docx 一律由 office_editor 工具集（editor_sdk）或 officecli 直接编辑：
- 更少代码量（OfficeCLI 自动处理 OMML/TOC/页码）
- 支持实时预览
- 支持内置 `validate` 质检

```python
import officecli as oc

with oc.create('report.docx') as doc:
    # 封面
    doc.send({'command': 'add', 'parent': '/', 'type': 'paragraph',
              'prop': {'text': '能源审计报告', 'font': '宋体', 'size': 22, 'bold': True, 'alignment': 'center'}})

    # 目录
    doc.send({'command': 'add', 'parent': '/body', 'type': 'toc'})

    # 公式
    doc.send({'command': 'add', 'parent': '/body', 'type': 'equation',
              'prop': {'latex': 'E_{jrcn} = \\frac{E - E_{gn} - E_{jt}}{M}'}})

    # 文档自动写盘 on close
```

### 安装后要做的事

1. 确保 `officecli` 在 PATH 中（`which officecli` 或 `where officecli`）
2. Hermes 内加载官方 SKILL.md：`curl -fsSL https://officecli.ai/SKILL.md | less`（参考用，无需手动装）
3. 在小项目上先试公式注入和模板合并，再推到全流程

### 已知限制

- OfficeCLI 的公式是 LaTeX → OMML 自动转换，不是所有 LaTeX 语法都支持（基础公式、分式、求和、积分、矩阵等常用功能支持良好）
- 生成 docx 后仍需校验（`officecli validate` + 视觉检查）
- 对极端复杂的 Word 排版（如多级列表 + 多字体混排），可能不如 python-docx 精细可控
