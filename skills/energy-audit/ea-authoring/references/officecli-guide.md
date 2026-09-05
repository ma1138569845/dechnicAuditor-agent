# OfficeCLI 集成指南（能源审计报告用）

## 概述

[OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) 是专为 AI Agent 设计的 Office 套件 CLI。单二进制、无需安装 Office、Apache 2.0 开源，支持 Word/Excel/PowerPoint 三件套。

相比 Hermes 内置的 `docx` (npm) skill 和当前项目用的 `python-docx`，核心优势：

| 功能 | python-docx (当前方案) | OfficeCLI |
|------|:---------------------:|:---------:|
| 公式 | ❌ 需手写 OMML XML (见 `omml-formula-guide.md`) | ✅ **LaTeX 输入** — 一行命令 |
| 目录 | ✅ 但 TOC 字段复杂 | ✅ 原生支持 |
| 页眉/页脚/页码 | ✅ 但需三处同步设 | ✅ 原生支持 |
| 表格合并单元格 | ⚠️ 需 XML 操作 | ✅ 原生 |
| 实时预览 | ❌ 需转 PDF → 看图 | ✅ `officecli watch` 浏览器实时渲染 |
| 校验 | ❌ | ✅ `officecli validate` 内置质检 |
| 模板合并 | ❌ 需代码 | ✅ `officecli merge` |
| Word/Excel/PPT | ❌ 只有 Word | ✅ 全支持同一个二进制 |

**结论**：对能源审计报告批量生成场景，OfficeCLI 比 python-docx 更省时间。

## 安装

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.ps1 | iex
```

### 验证

```bash
officecli --version
officecli --help
```

## 技术原理

OfficeCLI 是 .NET 10 自包含编译的单二进制（无需 .NET 运行时）。通过 Resident Mode 连接到文档进程，命令实时生效：

```
Agent → officecli create/add/set/get/merge → 内存中修改 → officecli close 写盘
```

Agent 调用模式（Python SDK 或 subprocess）：

```python
import json, subprocess
def oc(*args):
    return json.loads(subprocess.check_output(['officecli', *args, '--json'], text=True))

# 创建文档
oc('create', 'report.docx')

# 设置页眉（文字 + 分隔线；单位全称替换为实际名称）
oc('set', 'report.docx', '/header/default', '--prop', 'text=<被审计单位全称>  能源审计报告', '--prop', 'font=宋体', '--prop', 'size=10.5', '--prop', 'align=right')
oc('set', 'report.docx', '/header/p[1]', '--prop', 'pbdr.bottom=single;6;000000')

# 添加公式
oc('add', 'report.docx', '/body', '--type', 'equation',
   '--prop', 'latex=E_{jrcn} = \\frac{E - E_{gn} - E_{jt}}{M}')

# 插入目录
oc('add', 'report.docx', '/body', '--type', 'toc')

# 关闭
oc('close', 'report.docx')
```

## Word 常用操作速查

### 创建文档 + 页眉页脚

```bash
# 创建
officecli create report.docx

# 页眉（首页不同 + 奇偶页不同可选；对齐右对齐，单位全称替换为实际名称）
officecli set report.docx /header/default --prop text="<被审计单位全称>  能源审计报告" --prop font=宋体 --prop size=10.5 --prop align=right
# 页眉分隔线（pbdr.bottom；颜色 6 位 hex 不带 #，6=0.75pt）
officecli set report.docx /header/p[1] --prop pbdr.bottom=single\;6\;000000

# 页脚 + 页码（仅 PAGE 域数字，居中；不再写"第 X 页 共 Y 页"）
officecli set report.docx /footer/default --prop text="" --prop font=宋体 --prop size=10.5
officecli add report.docx /footer/default --type pageNumber

# 页码从正文开始（封面无页码）
officecli set report.docx /sectPr --prop titlePg=true
```

### 标题样式与目录

```bash
# 设置 H1、H2 样式（匹配格式规范）
officecli set report.docx /style[Heading1] --prop font=宋体 --prop size=15 --prop bold=true --prop alignment=center
officecli set report.docx /style[Heading2] --prop font=宋体 --prop size=14 --prop bold=true

# 插入目录
officecli add report.docx /body --type toc --prop headingLevel=3
```

### 公式（LaTeX 输入 → 自动 OMML）

```bash
# 一行命令，LaTeX 语法
officecli add report.docx /body --type equation \
  --prop latex="E_{jrcn} = \frac{E - E_{gn} - E_{jt}}{M}"

# 公式符号说明（普通段落）
officecli add report.docx /body --type paragraph \
  --prop text="式中：E_jrcn——单位建筑面积非供暖能耗(kgce/m²)"
```

### 表格

```bash
# 3列4行表格
officecli add report.docx /body --type table --prop rows=4 --prop cols=3

# 设置列宽
officecli set report.docx '/body/table[1]/col[1]' --prop width=3cm
officecli set report.docx '/body/table[1]/col[2]' --prop width=5cm

# 单元格赋值
officecli set report.docx '/body/table[1]/row[1]/cell[1]' --prop text="建筑名称"
officecli set report.docx '/body/table[1]/row[2]/cell[1]' --prop text="综合楼"

# 合并单元格
officecli set report.docx '/body/table[1]/row[1]/cell[1]' --prop hMerge=3
```

### 实时预览

```bash
# 打开浏览器实时预览（watch 模式）
officecli watch report.docx

# 然后在另一个终端修改——浏览器自动刷新
```

### 模板合并（批量报告）

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

## 与 python-docx 的切换策略

报告正文写作已全面转向 LLM + office_editor（officecli 回退），python-docx 仅存在于仿写脚本（assemble_report.py 等工具内部实现）。涉及 docx 编辑的手工操作一律 officecli：

### A) 渐进式替换（推荐）

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

### B) 全量重写（当前已定型）

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

## 安装后要做的事

1. 确保 `officecli` 在 PATH 中（`which officecli` 或 `where officecli`）
2. Hermes 内加载官方 SKILL.md：`curl -fsSL https://officecli.ai/SKILL.md | less`（参考用，无需手动装）
3. 在小项目上先试公式注入和模板合并，再推到全流程

## 已知限制

- OfficeCLI 的公式是 LaTeX → OMML 自动转换，不是所有 LaTeX 语法都支持（基础公式、分式、求和、积分、矩阵等常用功能支持良好）
- 生成 docx 后仍需校验（`officecli validate` + 视觉检查）
- 对极端复杂的 Word 排版（如多级列表 + 多字体混排），可能不如 python-docx 精细可控
