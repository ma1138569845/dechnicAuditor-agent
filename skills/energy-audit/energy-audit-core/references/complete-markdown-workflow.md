# 完整 Markdown 报告生成工作流

当用户需要一份包含全部8章的完整能源审计报告（Markdown格式）时使用本流程。

## 问题背景

`MarkdownReportBuilder` 只从 `report_data['sections']` 读取内容，而 `sections` 通常只包含第4章和第5章的纯文本（4.1~4.4、5.1~5.3）。第1-3章和第6-8章由 Word 专用的 `build_chapter1()` ~ `build_chapter8()` 方法生成，其内容在 Markdown 输出中全部显示为 `[内容待补充]`。

## 两阶段流程

### 阶段1：生成 Word 验证内容

1. 基于 `generate_report_shengli.py` 模板，修改参数（单位名、地址、审计周期、审计机构等）
2. 运行脚本生成 `.docx` 文件，验证 Word 输出完整
3. 确认所有8章内容、表格格式、数据完整性

### 阶段2：手动编写完整 Markdown

从 Word builder 的各章 `report_data` 提取文本，转换为 Markdown 格式：

**第1章（模板替换）**：从 `report_data['chapter1']` 取出参数，按 `ea-authoring/references/chapter1-templates.md` 模板填充：
- 1.1 两段式（审计目的定义 + 委托关系）
- 1.2 两段式（物理范围 + 工作范围含能源类型）
- 1.3 审计时间 + 审计周期
- 1.4 固定三段（管理/分析/建议）
- 1.5 三期过程（前期/中期/后期）
- 1.6 ● 无序列表（省级规章 + 国标 + 地方标准）

**第2章（LLM生成）**：从 `report_data['chapter2']` 取 `section_2_1/2_2/2_3` 和 `buildings` 列表。每栋建筑生成一张参数表。

**第3章（LLM生成）**：从 `report_data['chapter3']` 取 `section_3_1/3_2/3_3`。

**第4-5章**：内容已在 `sections` 中，MarkdownReportBuilder 能正常输出。

**第6章（动态生成）**：从 `report_data['chapter6']` 取 cooling/water/heating/other_energy 各系统的 text + equipment 列表，每个系统生成 H2 节 + 设备表。

**第7章（结构化）**：从 `report_data['chapter7']` 取 problems/solutions 列表，问题→建议一一对应，最后附 summary 汇总表。

**第8章（综合聚合）**：从 `report_data['chapter8']['text']` 取综合结论文本。

### 验证清单

生成后运行以下验证：
```python
import re
content = open('报告.md', 'r', encoding='utf-8').read()
# 8章
assert len(re.findall(r'# 第\d章', content)) == 8
# 关键数据点
assert '67636' in content
assert 'DB37/T 2673-2019' in content
# 表格分隔符
assert '|---' in content
```

## 模板文件

- `tools/energy_audit/generate_report_shengli.py` — 省立东院完整 Word 生成模板（含全部 report_data 结构）
- `tools/energy_audit/report_generator.py` — WordReportBuilder（各章 build 方法）和 MarkdownReportBuilder
