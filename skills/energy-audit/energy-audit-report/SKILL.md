---
name: energy-audit-report
description: 能源审计报告共享资产库——机构类型实例库（法院/医院/学校）、市州0-11章模板骨架、报告装配工作流（spec.json→assemble_report.py→附录→数值断言；主链脚本链见 references/script-assembly-chain.md）、附录/折标系数规范、定额补充（EUE表5、省级规章验证铁律）、PG数据导出流程。当需要"查找同类报告实例/参考""市州报告模板骨架""报告装配与数值断言""附录规范""数据导出"等场景时使用。章节正文写作规则见 ea-authoring（第1/2/3/4/6/7/8章）与 ea-calculation（第5章）；章结构权威=逐章指南（ea-authoring/references/chapter*-guide.md）与市州模板骨架（references/city-template-guide.md）。
agent_created: true
---

# Energy Audit Report 共享资产库（实例库 + 装配工艺 + Word 成品）

> **本 skill 不再定义"编制报告"的写作规则**（2026-09-03 定位修正）。
> - 第1/2/3/4/6/7/8章正文写作 → `ea-authoring`（author 专属）
> - 第5章计算与写作 → `ea-calculation`（caliber 专属）
> - 报告 8 章结构与章间联动铁律 → 逐章指南 `ea-authoring/references/chapter*-guide.md` + `references/city-template-guide.md`
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
| ~~`references/word-finishing.md`~~ | 已归档至 `_archive/2026-09-17/energy-audit-report/references/`（旧 report_generator/assemble 链路工艺）；**当前主链 = 装配脚本链**（见下行 `script-assembly-chain.md`），office_editor 路径为备用 |
| `references/script-assembly-chain.md` | **装配脚本链使用说明（2026-09-17 起主链）**：build/finalize/asserts 三命令、输入契约、已知偏差、操作坑 |
| `references/quota-supplement.md` | 定额补充（EUE 表5、区域供热办法、省级规章验证铁律） |
| `scripts/md_to_docx_energy_audit.py` | Markdown → Word 转换（通用化参数；**legacy**，新链见下行） |
| `scripts/fix_chapter5_formulas.py` | 存量第5章公式修复（方案B，仅旧 docx 后处理；用法见 ea-authoring/references/omml-formula-guide.md） |
| `scripts/build_energy_audit_docx.py` | **装配主链①**：一次构建报告 docx（封面/信息表/目录/8章/附录/页眉水印/页脚） |
| `scripts/finalize_energy_audit_pdf.py` | **装配主链②**：Word COM 刷目录缓存 + 导出签章 PDF |
| `scripts/ea_docx_asserts.py` | 交付断言器（docx+PDF 级硬检查与度量，每份必跑） |
| `assets/`（header/footer_template.xml、omml_formulas.json） | 页眉/页脚/OMML 模板资产 |

## 资产使用场景

1. **找同类报告参考**：按机构类型查 `references/examples/`（法院/医院/学校），写报告前先读同型实例。
2. **市州项目**：按 `city-template-guide.md` 的 0-11 章骨架选模板。
3. **报告装配**（仿写/组装模式）：按 `assembly-workflow.md`——正文写进 spec.json，`assemble_report.py` 组装，附录手动追加，最后 40+ 项数值断言。
4. **Word 成品处理**：`references/script-assembly-chain.md`（构建→收尾→断言三命令、页眉/水印/页脚/目录要点）+ `scripts/md_to_docx_energy_audit.py`（legacy）。
5. **数据导出**：PG 整库导出流程已移至 `energy-audit-pg-data/references/data-export.md`。
6. **报告装配（脚本主链，默认）**：`build_energy_audit_docx.py` → `finalize_energy_audit_pdf.py` → `ea_docx_asserts.py` 三步，见 `references/script-assembly-chain.md`；office_editor 路径降为**备用**（存量修改/应急）。

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
| 8章结构/章间联动 | `ea-authoring/references/chapter*-guide.md`（逐章）+ `references/city-template-guide.md`（市州模板） |
