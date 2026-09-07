---
name: energy-audit-style
description: 能源审计报告写作逻辑与语言风格规则包——跨章论证链（数据→分析→结论→建议）、句法模式、占位体系、评价短语、防抄三闸门（事实/句法/查重）。author 写作、editor 终审、imitate 仿写后查重时引用。结构权威不在此（见 energy-audit-core/report），章节模板不在此（见 ea-authoring），计算口径不在此（见 ea-calculation）。
version: 1.0.0
author: 马天远
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [energy-audit, writing-style, argument-logic, anti-plagiarism]
    category: productivity
    related_skills: [energy-audit-core, energy-audit-report, ea-authoring, energy-audit-imitate, energy-audit-report-qa]
---

# 能源审计报告写作逻辑与语言风格规则包

从正式样板报告（法院/医院/学校实例）中提取的**跨章写作规则**：怎么写才像
一份合格的能源审计报告——不是"每章写什么"（那是 `ea-authoring` 的章节指南），
而是"拿到数据后怎么推理、怎么下结论、用什么句式写、怎么不抄参考报告"。

## 与现有技能的边界（防止权威分裂）

| 问题 | 权威位置（本包不重复） |
|---|---|
| 8 章结构 / 章间联动铁律 | `energy-audit-core/references/public-institution-report-structure.md` |
| 市州 0-11 章模板骨架 | `energy-audit-report/references/city-template-guide.md` |
| 每章写作模板与数据源 | `ea-authoring/references/chapter*-guide.md` |
| 指标计算 / 第5章 | `ea-calculation` + `ea-calculation/references/` |
| 定额数值 | `energy-audit-core/references/standards-values.md`（权威单点） |
| 折标系数 | `energy-audit-core/references/coefficient-caliber.md`（权威单点） |
| 格式（字体/表格/页眉/水印） | `energy-audit-core/references/report-format-spec.md` |

本包只负责**跨章共性**：论证链怎么走、语言怎么组织、防抄怎么查。

## 本包文件

| 文件 | 内容 | 使用场景 |
|---|---|---|
| `references/argument-logic.md` | 分章/分系统论证链（输入→推理→输出→触发） | 写作前查"这节该怎么推" |
| `references/writing-style.md` | 句法模式骨架、占位体系、禁词、评价短语 | 写句时对齐句式与用词 |
| `references/anti-copy-gate.md` | 防抄三闸门 + 查重步骤与阈值 | 仿写后/终审前查重 |

## 通用写作铁律（先于一切章节规则）

1. **有数据才写段**：H2/H3 按实际系统动态生成，数据缺失的章节跳过或占位，
   禁止用模板句凑节。
2. **数值只取自本项目数据**，禁止从参考报告或前章文本复制数值；第8章结论
   复用第5/7章数值，不得引入新数值。
3. **证据先行**：先给数据/图表，再给分析，最后给结论与建议——禁止无数据的
   定性判断（"明显偏高"必须跟上对比依据）。
4. **问题从数据推断**：第4章计量问题、第7章现状问题只能从本项目
   metering/equipment/energy 字段推断，禁止罗列通用问题凑数。
5. **缺失即占位**：【待补充】/【待核验】/【待核实】三占位语义见
   `writing-style.md`，禁止用编造内容填补。
6. **防抄三闸门**：仿写参考报告时，事实层、句法层、查重层三道闸全部通过才
   算合格（见 `anti-copy-gate.md`）。

## 维护

- 规则更新走 `energy-audit-style-extractor` 技能（样板报告→三遍提取→泛化→
  编译进本包），只改 repo `skills/energy-audit/energy-audit-style/` 后 sync。
- 与正式报告口径冲突时，以正式报告/标准原文为准，修订后记录来源与日期。
