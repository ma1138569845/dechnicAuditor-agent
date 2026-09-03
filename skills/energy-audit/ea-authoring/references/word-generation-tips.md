# Word 报告生成注意事项

## 封面底部对齐

使用 spacer 段落 + `space_after` 将审计机构和日期推到页面底部：

```python
spacer = doc.add_paragraph()
spacer.paragraph_format.space_after = Pt(460)  # ~162mm
```

A4 可用高度 246mm，36pt 标题偏移 + 460pt spacer 确保底部信息靠近下边缘。

## 中文字体设置

 使用office工具分别设置西文和中文字体：

```
"Times New Roman"        # 西文
"宋体"                    # 中文
```

## 中文字体验证

`run.font.name` 只返回西文字体。验证中文字体需检查 XML：

```python
from lxml import etree
xml = etree.tostring(run._element, encoding='unicode')
# 检查 w:eastAsia 属性
```

## 正文首行缩进

落盘后、加水印前，必须给正文自然段加上首行缩进 2 字符。用 `office_cli_command`（officecli `set` / `batch`，属性 `firstLineChars=200`）。细则见 `references/docx-first-line-indent.md`。

## 项目名称水印

落盘前必须加水印。何时加、加在哪、OnlyOffice 兼容做法见 `references/docx-watermark.md`。

## 格式规范来源

`references/report-format-spec.md` — 基于 19 份省直能源审计报告分析总结。
