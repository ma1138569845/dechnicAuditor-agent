---
name: energy-audit-report
description: 能源审计报告共享资产库——机构类型实例库（法院/医院/学校）、市州0-11章模板骨架、报告装配工作流（spec.json→assemble_report.py→附录→数值断言）、Word成品工艺（md→docx、格式三件套）、附录/折标系数规范、定额补充（EUE表5、省级规章验证铁律）、PG数据导出流程。当需要"查找同类报告实例/参考""市州报告模板骨架""报告装配与数值断言""Word成品格式处理""md转Word""附录规范""数据导出"等场景时使用。章节正文写作规则见 ea-authoring（第1/2/3/4/6/7/8章）与 ea-calculation（第5章），章结构权威见 energy-audit-core/references/public-institution-report-structure.md。
agent_created: true
---

# Energy Audit Report 共享资产库（实例库 + 装配工艺 + Word 成品）

> **本 skill 不再定义"编制报告"的写作规则**（2026-09-03 定位修正）。
> - 第1/2/3/4/6/7/8章正文写作 → `ea-authoring`（author 专属）
> - 第5章计算与写作 → `ea-calculation`（caliber 专属）
> - 报告 8 章结构与章间联动铁律 → `energy-audit-core/references/public-institution-report-structure.md`
> - 定额矩阵/折标系数/版本归一权威单点 → `energy-audit-core/references/`
>
> 本 skill 提供的是**跨角色共享的资产与工艺**：同类报告实例、市州模板骨架、
> 装配工作流、Word 成品工艺、附录规范、数据导出。

## 内部结构导航

| 路径 | 内容 |
|------|------|
| `references/examples/court-agency-audit.md` | **法院/党政机关实例**（烟台法院 8 章工作流、指标口径、Word 参数） |
| `references/examples/hospital-audit.md` | 医院实例（DB37/T 2673-2019、床日用水量、特殊用能） |
| `references/examples/school-audit-template.md` | 学校实例（寄宿制修正、寒暑假日历） |
| `references/city-template-guide.md` | 市州模板 0-11 章骨架 + 单位类型适配 + 示例数据自洽规则 |
| `references/assembly-workflow.md` | 报告装配工作流（spec.json → assemble_report.py → 附录追加 → 40+ 数值断言） |
| `references/word-finishing.md` | ⚠️ 历史工艺存档（report_generator/assemble 旧链路）；**当前 Word 成品主链在 ea-authoring**（office_editor 工具集 + office_cli_command 缩进/水印，见 ea-authoring 排版技术节） |
| `references/quota-supplement.md` | 定额补充（EUE 表5、区域供热办法、省级规章验证铁律） |
| `scripts/md_to_docx_energy_audit.py` | Markdown → Word 转换（通用化参数） |

## 资产使用场景

1. **找同类报告参考**：按机构类型查 `references/examples/`（法院/医院/学校），写报告前先读同型实例。
2. **市州项目**：按 `city-template-guide.md` 的 0-11 章骨架选模板。
3. **报告装配**（仿写/组装模式）：按 `assembly-workflow.md`——正文写进 spec.json，`assemble_report.py` 组装，附录手动追加，最后 40+ 项数值断言。
4. **Word 成品处理**：`word-finishing.md`（目录 updateFields / 水印 DrawingML 禁 VML / 页码第X页共Y页）+ `scripts/md_to_docx_energy_audit.py`。
5. **数据导出**：PG 整库导出流程已移至 `energy-audit-pg-data/references/data-export.md`。

## 章节写作规则去向（合并后单点）

| 章 | 权威位置 |
|---|---|
| 第1章 | `ea-authoring/references/chapter1-templates.md` |
| 第2章 | `ea-authoring/references/chapter2-guide.md` |
| 第3章 | `ea-authoring/references/chapter3-guide.md` |
| 第4章 | `ea-authoring/references/chapter4-guide.md` |
| 第5章 | `ea-calculation/references/chapter5-writing-guide.md`（生成逻辑）+ `chapter5-writing-logic.md`（写作逻辑与计算三铁律） |
| 第6章 | `ea-authoring/references/chapter6-*.md` |
| 第7章 | `ea-authoring/references/chapter7-guide.md` |
| 第8章 | `ea-authoring/references/chapter8-guide.md` |
| 8章结构/章间联动 | `energy-audit-core/references/public-institution-report-structure.md` |
