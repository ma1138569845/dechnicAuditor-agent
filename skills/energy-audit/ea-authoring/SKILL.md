---
name: ea-authoring
description: "author（小德）Agent 专属技能，仅流水线 author 角色装配时使用。当 author 编写或生成公共机构能源审计报告时使用——覆盖第1/2/3/4/6/7/8章正文写作（第5章由 caliber 的 ea-calculation 产出，author 只装配不重写）、OMML 公式、office_editor 工具集（office_create/edit/save）文档编辑、Word 生成、以及最终产物（.docx + 默认签章 .pdf）。⚠️ default 主对话收到\"编制/生成XX能源审计报告\"请求时应加载 energy-audit-routing 转交 editor 流水线，勿直接采用本技能。数据采集/入库/校验问题不适用本技能。"
version: 1.5.0
author: 马天远
---

# 报告编写专属知识（ea-authoring）

## 概述

本技能回答"如何写出 8 章完整、格式规范的公共机构能源审计报告 .docx"，只含报告写作/排版环节的深度知识。

**共享核心（REQUIRED BACKGROUND）：** 8章结构、格式规范、DB37 标准等通用原则在 `energy-audit-core` 技能中，本技能不重复，写作前须先具备该核心知识。

## 最终产物

每个审计项目交付**两个文件**，缺一不可：

| 产物 | 格式 | 说明 |
|------|------|------|
| 能源审计报告 | `.docx` | 8 章正文 + 排版 + 首行缩进 + 单位名水印+页眉/页脚 + 目录（本技能主流程产出） |
| 能源审计报告 | `.pdf` | 由定稿 `.docx` 转换，**默认加盖签章** |

**命名与落盘**：`<单位全称>能源审计报告.docx` / `<单位全称>能源审计报告.pdf`，均落盘到项目 `output/` 目录。

**PDF 生成与签章**：

1. `.docx` 定稿（水印 + 首行缩进全部完成后）转 `.pdf`，走 `office_render(file_id=..., format="pdf")`（内部 `office_to_pdf`）：
   - 首选 **OnlyOffice ConvertService**（`tools/office_onlyoffice.convert_to_pdf`，远程 DocumentServer `HERMES_OFFICE_DS_URL`）
   - 回退 **COM automation**（本地 Word `ExportAsFixedFormat`，`tools/office_pdf_convert.com_to_pdf`）
   - 不用 LibreOffice。
2. **签章默认启用**：对生成的 `.pdf` 加盖签章，走 `office_render(..., seal_text=<审计机构名>)`：
   - **真实签章图**：存在 `tools/energy_audit/assets/default_seal.png` 时自动使用（真实印章 PNG，`seal_text` 被忽略）；把审计机构印章放到该路径即自动生效
   - **占位章回退**：无该图时，用 `seal_text`（审计机构名）生成红色圆形默认章
   - 盖章位置：封面底部居中（审计机构名称落款处）

## 何时使用 / 不使用

- ✅ 编写任意章节正文、生成/修改 .docx、排版样式、公式、图片与表格嵌入
- ❌ 数据采集、数据校验、入库 → 属于 datacollection Agent 职责（`ea-datacollection`），不要在本技能内解决。
- ❌ **default 主对话/非 author 角色**收到"编制/生成XX能源审计报告"请求 → 先加载
  `energy-audit-routing` 转交 editor 流水线，勿直接按本技能动手（本技能仅 author
  profile 装配，写作前置数据必须来自上游 caliber 产出）。

## 输入内容（强制前置流程）

按顺序执行，禁止跳步：

1. 调用 `tools/energy_audit/project_data.py` 的 `load_project(unit_name)` 查询当前审计项目数据。
   - 返回 `AuditProject` **dataclass**（非 dict），用 `.` 属性访问；`None` 表示项目不存在，用 `list_projects()` 确认。
   - 完整字段映射与取值规则见 `references/data-model-reference.md`，写作前必读。
2. 若返回 NULL 或缺少所需数据 → 回退流程，转交 profiles 的 datacollection Agent 获取数据。
3. 若 datacollection 仍无法获取 → **立即终止整个报告编制流程**，提示用户先完善该审计项目的数据。禁止编造数据继续写作。

## 章节写作指南

使用 **office_editor 工具集**进行文档的创建与编辑（`office_edit` 走 editor_sdk MCP，详见下「Office 编辑」节）。

所有参考文件位于 `references/` 目录：

| 章节 | 参考文件 |
|------|---------|
| 数据模型 | `references/data-model-reference.md`（load_project 返回格式 + 字段速查） |
| 报告结构 | `energy-audit-core/references/public-institution-report-structure.md` |
|  封面  |`references/docx-ooxml-techniques.md`|
| 审计信息 |`references/building-param-table-spec.md`|
| 第1章 | `references/chapter1-templates.md`（模板替换式） |
| 第2章 | `references/chapter2-guide.md`（LLM 生成 + 自动表格/图片） |
| 第3章 | `references/chapter3-guide.md` |
| 第4章 | `references/chapter4-guide.md` |
| 第5章 | `ea-calculation`（caliber 产出 chapter5.md，author **只装配引用、不重写**；计算与写作口径见 ea-calculation/references/chapter5-*） |
| 第6章 | 见下方专项列表 |
| 第7章 | `references/chapter7-guide.md` |
| 第8章 | `references/chapter8-guide.md` |

**第6章参考文件**（分系统详述，文件最多，单独列出）：

- `references/chapter6-guide.md`
- `references/chapter6-indoor-env.md`
- `references/chapter6-reference-structure.md`
- `references/chapter6-sub-system-spec.md` / `chapter6-sub-system-spec-v2.md` / `chapter6-sub-system-final-spec.md`
- `references/chapter6-writing-spec.md`

多份 spec 内容冲突时，以 `chapter6-sub-system-final-spec.md` 为准。

## 排版技术

| 技术 | 参考文件 |
|------|---------|
| office_editor 工具集 | 见下「Office 编辑（office_editor 工具集）」节 |
| OMML 公式 | `references/omml-formula-guide.md` |
| OfficeCLI 集成 | `references/officecli-guide.md`（LaTeX 公式/目录/页眉页脚，python-docx 的替代工具） |
| Word 生成技巧 | `references/word-generation-tips.md` |
| 正文首行缩进 2 字符 | `references/docx-first-line-indent.md`（落盘后、加水印前必做） |
| 项目名称水印（OnlyOffice 兼容） | `references/docx-watermark.md`（落盘前必做） |
| 辅助视觉 | `references/auxiliary-vision-config.md` |

## 架构与历史参考

| 文件 | 内容 |
|------|------|



## Office 编辑（office_editor 工具集）

报告 .docx 的创建/写入/保存走 `office_editor` 工具集的 7 个工具，**不要假定存在独立的"OfficeCLI"**（officecli 只是 editor_sdk 缺失时的受限回退引擎）。

**新建报告基本工作流**：

1. `office_create(doc_type="doc", file_path="<绝对路径>/<项目名>能源审计报告.docx")` → `file_id`
2. `office_edit(operation=..., op_args=...)` 逐章写入（**operation 是 MCP 操作名**，不是自定义方法名）：
   - `doc_insert_paragraph_with_text` — 追加段落（idx=目标段 end_index；末尾用 `doc_get_last_operable_pos().position`，勿硬编码大数）
   - `doc_insert_text` — 指定位置插入
   - `doc_replace_text` — 替换文本（`ranges=[{begin, end}]`，对象数组格式）
   - `doc_get_outline` / `doc_get_last_operable_pos` — 读结构 / 定位
3. `office_save(file_id=..., save_path="<绝对路径>")` 落盘（高层参数是 `save_path`，handler 内部映射为 editor_sdk 的 `file_path`）
4. **正文首行缩进（强制）**：对刚保存的 .docx，用 **`office_cli_command`（officecli）** 给正文自然段设 `firstLineChars=200`（可加 `firstLineIndent=24pt`）。做法见 `references/docx-first-line-indent.md`。禁止 python-docx。标题/表题/图注/单元格/列表不缩进。无缩进不得交付。
5. **加水印（强制）**：注入被审计单位名称水印，再预览。做法见 `references/docx-watermark.md`。无水印不得交付。
6. 排版预览用 `office_preview`；确认引擎用 `office_status`

**附录编写（officecli，2026-09-03 定）**：附录1~5（建筑基本信息及设备统计表/能耗数据信息表/室内环境测量/室内空气质量指标及要求/折标准煤参考系数）用 `office_cli_command` 追加——`add ... --type heading/table` + `set ... --prop text/width`，格式 Table Grid、12pt 宋体居中、行高 1.01cm。**全链路禁用 python-docx，附录无例外**；清单与数据来源详见 `energy-audit-report/references/assembly-workflow.md`

**引擎与回退**：
- 首选 **editor_sdk**（本地二进制，MCP 协议）：`office_edit` 的 199 个 MCP 编辑操作全可用。
- **editor_sdk 缺失**（`office_status` 报不可用）→ officecli 回退：MCP 操作**不会自动翻译**，须改用 `office_cli_command` 工具按 officecli 原生语法（`add <file> /body --type paragraph --prop text="..."` 等）编辑，能力受限。

**坑位（勿回退）**：
- `office_edit` 的 operation 必须是 MCP 工具名（如 `doc_insert_text`）；把工具名直接当 method 会报 `-32601 Method not found`。
- `office_save` 传 `save_path`（高层工具参数），不要直接传 `file_path` 之外的字段。
- 既有 .docx（如已生成的报告含第2章图片/表格）用 `office_open(file_path)` 打开后，对占位/待修段落做**定点 `office_edit`**，不必全文重建。

## 关键规则（红线）

1. **第6章 6.1 分系统详述**，结构参考 `references/chapter6-reference-structure.md`：
   空调与供暖/照明/办公设备/其他用电(或医疗设备)/厨房/信息机房/变配电——每个分系统含冷热源描述+运行时间+设备照片+设备表。
2. **第4章 4.2/4.3 独立计量、第7章问题必须从实际数据推断**（基于 `proj.metering` / `proj.equipment` / `proj.buildings`），禁止写虚假问题；已采集的独立计量禁止再向用户索取，只有当相关数据缺失的时候才可向用户询问。
3. **格式规范**：H1宋体15pt居中 / H2宋体14pt / H3宋体12pt / 正文12pt宋体+TNR、1.5倍行距、两端对齐、**首行缩进2字符**。细则见 `references/docx-ooxml-techniques.md` 与 `references/docx-first-line-indent.md`。
4. **第8章默认占位文本会阻塞自动生成**：`report_generator.py` 中 `'chapter8': {'text': '【待前7章就绪后LLM综合生成】'}` 会导致 `build_chapter8()` 直接返回。必须改为 `'chapter8': {}` 让自动生成生效。
5. **新增 config 字段必须三处同步**：config JSON / `pg_collector.py` 构造参数 / `report_generator.py` 的 `load_from_project()`。漏任一处会导致字段静默丢失。
6. **落盘前必须有项目名称水印**：文案用 `proj.base.unit_name`，写入各节**页眉 DrawingML**（`behindDoc=1`）。禁止 VML `textpath`。细则见 `references/docx-watermark.md`。
7. **落盘后、加水印前必须有正文首行缩进**：用 `office_cli_command` 只给正文自然段设 `firstLineChars=200`（可加 `firstLineIndent=24pt`）。禁止 python-docx，禁止全角空格假装缩进，禁止给标题/表题/图注/单元格/列表缩进。细则见 `references/docx-first-line-indent.md`。

## 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 数据缺失时编造内容继续写 | 报告含虚假数据，审计无效 | 走"输入内容"回退流程，仍缺则终止并提示用户 |
| 保留 chapter8 占位文本 | `build_chapter8()` 直接返回，第8章为空 | 占位改为 `'chapter8': {}`（红线4） |
| config 新字段只改一处 | 字段静默丢失，排查困难 | 三处同步（红线5） |
| 第4章已有独立计量仍问用户 | 与 data.json 矛盾或漏写已计量设备 | 4.2/4.3 先算 `has_ok`/`has_no`，见 `chapter4-guide.md` |
| 第7章凭经验罗列通用问题 | 与实际数据矛盾 | 仅从 metering/equipment/building 字段推断（红线2） |
| 第6章多份 spec 混用旧版 | 分系统结构不一致 | 以 `chapter6-sub-system-final-spec.md` 为准 |
| 使用"OfficeCLI"独立工具编辑 | 工具已废弃/不指向正确引擎 | 用 `office_editor` 工具集（office_edit 走 editor_sdk MCP；officecli 回退走 `office_cli_command`） |
| `office_edit` 把操作名直接当 method | `-32601 Method not found` | operation 用 MCP 工具名（`doc_insert_text` 等），走 `tools/call` 格式 |
| `office_save` 传非 `save_path` 字段 | editor_sdk 的 `save_file` 认 `file_path` | 高层工具统一传 `save_path`，由 handler 映射 |
| 落盘无水印或用 VML `textpath` | OnlyOffice 不显示；再保存会破坏 Word 水印 | 页眉 DrawingML，文案 `proj.base.unit_name`（见 `docx-watermark.md`） |
| 水印写成 `proj.base.name` 或正文灰字 | 文案带「能源审计」后缀 / 破坏排版 | 只用单位全称；注入页眉，不进正文 |
| 插入段落不设首行缩进 | 正文顶格，不符合报告体例 | `office_save` 后用 `office_cli_command` 按 `docx-first-line-indent.md` 批处理 |
| 给标题/列表/表题/单元格也缩进 | 标题不顶格、列表错位 | 只缩进正文自然段；例外见格式规范 §五 / §七 |
| 用全角空格假装缩进 | 复制/再排版会乱，不是真正的段落格式 | `officecli set`：`firstLineChars=200` |
