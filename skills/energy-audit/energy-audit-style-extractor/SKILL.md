---
name: energy-audit-style-extractor
description: 能源审计写作风格提取器——从一篇样板能源审计报告（docx/md）逆向提取"写作逻辑"（结构树/论证链/语言风格），泛化去事实后编译进 energy-audit-style 规则包。学的是报告生成的"方法"，不是报告里的句子和数据。当用户提供样板报告要求"学习其写作逻辑/风格并固化为技能"、或需要更新 energy-audit-style 规则包时使用。不适用于：编写单份报告（走 energy-audit-routing）、数据采集（ea-datacollection）、指标计算（ea-calculation）。
version: 1.0.0
author: 马天远
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [energy-audit, style, extractor, skill-compiler]
    category: productivity
    related_skills: [energy-audit-style, energy-audit-core, energy-audit-report]
---

# 能源审计写作风格提取器（报告 → 写作规则包）

把一篇"写得好的"能源审计报告逆向工程成可复用的写作规则，写入
`energy-audit-style` 规则包。**学逻辑，不抄句子**——输出中禁止出现样板报告的
单位名称、人数、面积、能耗数值、年份等任何事实。

## 何时使用

- 用户提供一份样板报告（docx/md/PDF 转 md），要求"学习它的写作逻辑、格构、
  总结成写作技能"。
- 现有规则包（`energy-audit-style`）需要吸收新机构类型或新样板。
- 用户要求对照样板报告修订既有写作风格规则。

## 铁律

1. **禁止"一口气读完直接总结"**：必须按下方三遍提取，每遍只看一个维度、输出
   一个 schema。一次性总结产出的"规则"必然退化为报告摘要。
2. **输出零事实**：规则里只能有模式、句式骨架、触发条件；任何具体事实
   （单位名/数值/年份/人名）出现即为失败，回炉剥离。
3. **不重定义权威**：章节结构以 `energy-audit-core` 8 章结构与
   `energy-audit-report` 模板骨架为准；本提取器只记录样板与权威的**偏差**，
   不另立结构。指标计算口径以 `ea-calculation` 与
   `energy-audit-core/references/coefficient-caliber.md` 为准。
4. **写入规则包只走 repo**：编译落盘改
   `skills/energy-audit/energy-audit-style/`（git 权威源），再运行
   `scripts/sync_ea_skills.py` 发布。禁止只改主库。

## 五步流程

### 第 1 步：解析

- 样板是 .md/.txt → 直接读（已结构化）。
- 样板是 .docx → 运行 `python scripts/parse_report.py <报告.docx> --out /tmp/parsed.txt`
  （本技能目录下），得到按标题层级分块的文本；表格保留为 markdown 行。
- PDF → 先转 md（ocr 或文本层提取，工具链见 `pdf`/`ocr-and-documents` 技能），
  再走解析。

### 第 2 步：三遍提取（每遍独立，禁止合并）

每遍输出严格对照 `references/extraction-schema.md` 的 schema。
三遍可以用三批独立 LLM 调用完成，批间只传"上一遍的 schema 输出 + 解析文本"，
不传全文转述。

| 遍次 | 维度 | 产出 | 落盘 |
|---|---|---|---|
| Pass 1 | 结构树 | 章-节层级 + 每章目的句 + 与 core 8 章权威的偏差表 | 草稿区 |
| Pass 2 | 论证链 | 每节：输入数据 → 推理动作序列 → 输出结论（泛化） | 草稿区 |
| Pass 3 | 语言风格 | 句法模式骨架、占位体系、禁词、评价短语 | 草稿区 |

### 第 3 步：泛化闸门

三遍输出合并后逐条检查（可 grep 数字/具体名词）：

- 不得出现样板单位名、地区名、人名、年月、具体数值；
- 数值位置一律替换为占位符（如 `{年用电量}`、`{增长率}`）；
- 句法模板只留骨架：`由图X.X分析，……整体平稳。{年份}较{上一年}增加{Δ}，增加率为{增长率}。`
- 若某条规则去掉事实后失去意义（纯依赖具体数据的叙述），丢弃不写入。

### 第 4 步：编译落盘

把通过的规则写入 `skills/energy-audit/energy-audit-style/`：

| 提取产物 | 写入位置 |
|---|---|
| 结构偏差表 | `references/argument-logic.md` 对应小节（仅"与权威的差异"） |
| 论证链模式 | `references/argument-logic.md` |
| 句法/占位/禁词/评价短语 | `references/writing-style.md` |
| 样板中发现的防抄相关要求 | `references/anti-copy-gate.md` |

写入方式：**先读目标文件现状，再按机构类型/章节增量合并**；与现有规则冲突时
优先保留已标注"以正式报告为准"的条目，并记录冲突来源（哪个样板、哪一版）。
禁止整文件覆盖重写。

### 第 5 步：验证

1. 拿一个**不同项目**的真实数据（`C:/Users/matianyuan/projects/energy-audit/<项目>/data.json`），
   按新规则试写一个小节；
2. 与正式版报告（如有）同节对照：结构、论证顺序、句式是否贴合，有无事实泄漏；
3. 发现问题 → 回第 4 步修规则，再验。最多三轮，仍不收敛就把差异显式报告给用户。

## Pitfalls

- 医院/学校/法院样板混在一起提取时，共性进通用规则，差异按机构类型分目录记录，
  不得互相污染（例：医院第 4 项指标是"单位开放床日用水量"，法院是"人均机关取水量"）。
- 样板报告自身的已知瑕疵（如数值前后不一致、口径标注【待核验】）**不提取为规则**，
  可记录进"样板缺陷清单"提醒用户，禁止写入规则包。
- 母版为 PDF 扫描件时，先 OCR 再提取；OCR 噪声多的段落跳过，不猜。
- 提取器产出只进规则包，禁止顺手修改其他技能（core/report/authoring 的权威条款
  如需修订，另走变更审批）。

## Verification

- [ ] 三遍提取分别完成，各有 schema 输出。
- [ ] 泛化闸门通过：规则文本中无样板事实（grep 数字与专名）。
- [ ] 写入位置正确：只动了 `energy-audit-style/` 目录。
- [ ] 已运行 sync 脚本发布（或已明确告知用户待发布）。
- [ ] 验证小节已用另一项目数据试写并对照。
