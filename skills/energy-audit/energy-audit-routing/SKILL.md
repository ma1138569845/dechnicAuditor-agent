---
name: energy-audit-routing
description: "能源审计任务双轨调度：单项目/散单 default 直跑，批量转 editor kanban。用户提出\"编制/生成/完成XX能源审计报告\"或任何涉及某单位能源审计的任务（采集/校验/核算/分析/报告）时，default（当前会话）必须先加载本技能做分诊——单项目数据齐备走直跑轨（脚本链直跑+三批写章），多份报告/批量/数据残缺走 kanban 轨（转交 editor）。"
version: 1.2.0
author: DechnicAuditor
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [energy-audit, routing, dual-track, profiles, multi-agent]
---

# 能源审计任务双轨调度

## When to Use（触发条件）

用户提出涉及**某单位能源审计**的任务（数据收集/校验/核算/分析/报告编制）时，default 先加载本技能做**双轨分诊**，再决定直跑或转交。default 其余时间只做：日常对话、咨询答疑、结果核验汇报。

## 双轨分诊（一句话规则）

> **"一份报告、数据齐备、当前会话" → default 直跑；"多份报告 / 批量 / 数据残缺需流水线补采" → 转 editor。**

| 场景 | 轨道 | 理由 |
|---|---|---|
| 单项目（会话中点名 1 个单位，1 份报告） | **default 直跑** | 省 8 会话冷启动 + 调度间隔 + 跨任务数据重读 |
| 小批量散单（≤3 个单位，逐个对话发起） | **default 直跑，串行** | 同上；项目间串行、上下文批次隔离 |
| 批量生产（≥2 项目同时出报告 / 100+ 栋规模 / 需要跨项目 Director 对比） | **kanban（转 editor）** | 项目间并行 + 任务隔离 + 审查独立 |
| 直跑中 V1 判 P0 阻塞 或 数据严重缺失需多轮补采 | **升级转 editor** | 避免 default 上下文被多轮补采拖爆 |

硬规则：**只要用户一次提出 ≥2 个单位出报告，即为批量，转 editor**；不因"default 能干"而自行扩轨。

---

## 直跑轨（default 直跑操作规程）

直跑 = 脚本链直连 CLI（不经 LLM 传声筒）+ LLM 只干三件事：写章、装配、复核。

### 阶段 0：前置确认

1. 项目名模糊 → `energy_audit_search_projects` 反查确认单位全称
2. 工具链可达：`EA_TOOLS_ROOT` 指向 repo 根（含 `tools/energy_audit`），或用绝对路径调用；缺省按 `_paths.py` 三级降级解析
3. 确认项目目录 `~/projects/energy-audit/<单位全称>/`；未指定版本且 data.json 已存在则跳过采集。任务带了 `versionCode` / `--version-code` 时必须重采。
4. 部署前提自检（新机/换机必做）：见 `energy-audit-core/references/deployment-prerequisites.md`

### 阶段 1：脚本链直跑（无 LLM 思考环节）

> 路径约定：`<skills>` = repo 根 `skills/energy-audit/`；profile 场景取其技能目录（`.../profiles/<角色>/skills/energy-audit/`）。

```bash
# 1) 采集（未指定版本且 data.json 已存在可跳过；指定 --version-code 必须重采）
python tools/energy_audit/data_collection_cli.py <项目名> [--version-code <versionCode>]
# 2) V1 数据验证（exit 0=过 / 1=输入缺失 / 2=P0 阻塞）
python <skills>/ea-validation/scripts/data_verification_agent.py <项目名> --mode DATA_CHECK --json
# 3) 指标计算 + 第5章
python <skills>/ea-calculation/scripts/caliber_agent.py <项目名>
# 3.5) 第5章装配稿就位（2026-09-17 新增，消灭手工搬运断点）
#      exit 0=已就位或有更新的装配稿（保留）；2=装配稿早于计算产物，人工确认后加 --force
python <skills>/ea-calculation/scripts/prepare_chapter_md.py <项目名>
# 4) V2 指标复核（exit 0/2 裁决同上）
python <skills>/ea-validation/scripts/data_verification_agent.py <项目名> --mode INDICATOR_REVIEW --json
```

- exit 1（输入缺失）：对话里直接问用户补线索，补齐重跑该步
- exit 2（P0）：停止，向用户说明 P0 内容 → 用户决定"修数据重跑"或"升级转 editor"
- 3.5 步 exit 2：装配稿 `chapter_md/ch5_import.md` 早于 `chapter5.md`（可能用了旧数据）→ 先问用户，确认后 `--force` 覆盖
- 每步产物落盘项目目录（data.json / validation.json / indicators.json / chapter5.md / chapter_md/ch5_import.md / charts/）

### 阶段 2：LLM 写章（3 批，批间落盘 + /compact）

按 ea-authoring 同款批次划分（kanban 轨称"3 卡"，直跑轨称"3 批"，是同一件事——术语见 `energy-audit-core/SKILL.md` 术语表；**其余全部照 ea-authoring 执行**）：

- 批 1：封面数据 + 第 1~4 章 → `chapter_md/ch1~ch4.md`
- 批 2：第 5 章装配（**装配稿由阶段 1 的 3.5 步就位**：`chapter_md/ch5_import.md`；作者可在其上并入叙述段，但**禁重算数值**）+ 第 6/7 章
- 批 3：第 8 章 + 附录 → `chapter_md/ch8.md`、`chapter_md/appendix.md`
- **三批全落盘后 → 装配脚本链**（2026-09-17 起主链）：`build_energy_audit_docx.py` → `finalize_energy_audit_pdf.py` → `ea_docx_asserts.py`，见 `energy-audit-report/references/script-assembly-chain.md`；office_editor 路径为备用

**直跑铁律（与 kanban 三卡铁律同源）**：

1. 数值一律从 data.json / indicators.json / chapter5.md 读取，禁从前序章节文本或 memory 提取
2. **批与批之间必须压缩上下文，下一批只信文件不信上文**——直跑成败的生命线。交互会话用 `/compact`；**非交互模式**（`hermes chat -q/-Q`、kanban worker）无法执行斜杠命令 → 用"**每批一个独立会话/任务**"或 `--resume` 分次续跑替代：批边界即任务边界，不依赖上文（2026-09-18 实测确认）
3. 每批完成必须把章节 md 落盘 `chapter_md/`（脚本链只从文件读内容，禁止只留在会话/内存）——备用路径沿用 `office_save` 落盘、`office_open` 接续、禁重建文件的约定
4. 备用路径（office_editor）：正文一律 `doc_insert_markdown` 整章导入、禁逐段插入、每批后跑格式修复链；主链（脚本装配）无此要求

### 阶段 3：V3 直跑 + 每次人工确认（2026-09-06 定）

```bash
python <skills>/ea-validation/scripts/data_verification_agent.py <项目名> --mode REPORT_REVIEW --report <报告.docx> --json
```

- P0 → 定点修复后重跑 V3
- **直跑模式 V3 结论每次都必须向用户完整展示并请其确认**（P0/P1/P2 全列，不得只报"通过"二字）。自审丧失独立性，用人工复核补偿；用户未确认前不得交付

### 阶段 4：交付

双文件落盘 `<单位全称>能源审计报告.docx` + `.pdf`（签章默认启用；脚本链默认输出 `output/_script_build/`，正式命名切换待定），向用户报路径 + 各阶段实测耗时。

---

## kanban 轨（批量转交 editor，原约定保留）

### 调度边界（2026-09-05 定位统一，不变）

- **editor = 编排入口 + Director 终审**：接收 default 转交、启动 kanban 任务图流水线、终审汇总；运行时任务调度归 kanban dispatcher。
- **default = 分诊入口**：直跑轨自己干；批量轨转 editor，不创建 kanban 任务图、不直接唤醒执行 profile。
- **同一任务同一时间只有一个调度者**：直跑轨 = default 自己；批量轨 = kanban dispatcher。

### 执行角色（kanban 轨，由 editor 调度）

| Profile | 流水线环节 | 职责 |
|---|---|---|
| datacollection | 采集 | PG/Excel/Config 多源采集 → data.json |
| datava | 验证 | 完整性检查 + 异常 + KG 诊断（V1/V2/V3） |
| caliber | 指标计算 | 5项指标 + 定额对标 + 图表 + 第5章 |
| author | 报告生成 | 8 章报告 docx（三卡串行） |

### 转交操作模板

```bash
hermes -p editor chat -q "<任务描述>" -Q    # background=true, notify_on_complete=true
```

任务描述需包含：单位全称、任务类型（采集/校验/报告）、已知数据位置、上游产出路径、用户要求（如缺失数据必须标【待补充】）。

### 核验（default 保留质量把关）

editor 完成后，default 回读核验再向用户汇报：
- 读产出文件（data.json / 报告 docx）与 editor 会话库（`$LOCALAPPDATA/hermes/profiles/editor/state.db`）
- 确认新会话 `profile_name='editor'`，任务写入正确位置
- 产出异常时指出并退回，不直接报"完成"

---

## 硬约定（两轨通用）

- **单位目录统一**：`~/projects/energy-audit/<单位全称>/`（Windows 本机即 `C:\Users\<当前用户>\projects\energy-audit\`，勿写死机器名）
- **数据真实性**：所有数字必须来自原始台账/账单，禁止编造
- **直跑轨技能加载**：写章前按需 `skill_view` 加载 ea-authoring / ea-calculation / ea-validation / ea-datacollection（default 技能可见性已含全部 4 个，按需加载即可）
- **成本透明**：每次 LLM 调用是真实模型调用；直跑轨脚本链环节零 LLM 介入
