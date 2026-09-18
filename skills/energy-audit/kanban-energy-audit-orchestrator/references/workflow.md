# workflow
> 本文并入 `monitoring.md`（2026-09-18 瘦身合并第 6 组，原文件已归档至 `_archive/2026-09-18/kanban-energy-audit-orchestrator/references/`）；内容逐字保留，仅统一标题层级。

---

## 调度工作流与任务图（原 workflow）

> knowledger profile 不在本任务图内（知识库/问答辅助角色，见 role-definitions.md 顶部说明）。

### 任务图结构

每个公共机构项目生成 8 个父子链接的 Kanban 任务 + 1 个汇总 Director
（DataVA 在三个检查点各介入一次；报告环节由 author 拆 3 张串行卡，与 bootstrap_pipeline.py 一致）：

```
Director (汇总审查)
  └─ Project A: 采集 (datacollection)
      └─ V1 验证 DATA_CHECK (datava)
          └─ 计算 (caliber)
              └─ V2 指标复核 INDICATOR_REVIEW (datava)
                  └─ 报告卡1 基础章 (author)
                      └─ 报告卡2 数据章 (author)
                          └─ 报告卡3 收尾章 (author)
                              └─ V3 报告审查 REPORT_REVIEW (datava) ──┐
  ...（各项目并行）                                                  │
Director ←──────────────────────────────────────────────────────────┘
```

- **纵向**（同一项目）：严格串行，前一步完成 → 后一步自动晋升 ready
- **横向**（不同项目）：完全并行，互不依赖
- **Director**：所有项目报告完成后触发，assignee = profiles["director"]（推荐 editor——编排入口 + Director 终审，与 author 写作分离；缺省回退 reporter）
- **报告三卡拆分的动机**：单卡写 8 章曾致上下文膨胀（~50 万 token）与迭代预算耗尽（90/90 超时）。拆卡后每卡 3~4 章、上下文不膨胀；任一卡失败仅重跑该卡（前卡产物已落盘 docx）。

### 每步任务详解

#### Step 1 — 数据采集

- **Worker:** datacollection Profile（技能: ea-datacollection + energy-audit-core + energy-audit-pg-data）
- **输入:** config.json（复制到 workspace）
- **产出:** data.json（项目基础数据+能耗+建筑+设备+人员+图片+指标预计算）
- **完成标记:** `kanban_complete(metadata={"data_path": "..."})`

#### Step 2 — V1 数据验证（DATA_CHECK）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core + energy-audit-pg-data）
- **输入:** data.json
- **产出:** validation.json（完整性检查+异常检测+KG因果诊断+质量评级；P0→block / P1P2→记录）
- **完成标记:** `kanban_complete(metadata={"validation_path": "..."})`

#### Step 3 — 指标计算

- **Worker:** caliber Profile（技能: ea-calculation + energy-audit-core + energy-audit-report）
- **输入:** validation.json + data.json
- **产出:** indicators.json + chapter5.md + charts/
- **完成标记:** `kanban_complete(metadata={"chapter5_path": "..."})`

#### Step 4 — V2 指标复核（INDICATOR_REVIEW）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core）
- **输入:** indicators.json + chapter5.md
- **产出:** indicator_review.json（指标年际对比+对标合理性+数据一致性）
- **完成标记:** `kanban_complete(metadata={"indicator_review_path": "..."})`

#### Step 5a — 报告卡1（基础章）

- **Worker:** author Profile（技能: ea-authoring + energy-audit-core + energy-audit-report + energy-audit-imitate）
- **输入:** data.json + validation.json + indicators.json + indicator_review.json
- **产出:** 第1~4章 LLM 分 1~2 批生成 md 落盘 `chapter_md/ch1~ch4.md` → `office_create` 建 docx + `doc_insert_markdown` 整章导入（封面/审计信息表模板注入，第1章 1.1~1.6）→ 格式修复链 → `office_save` 落盘
- **完成标记:** `kanban_complete(metadata={"report_path": "..."})`

#### Step 5b — 报告卡2（数据章）

- **Worker:** author Profile（技能同上）
- **输入:** data.json + indicators.json + chapter5.md + 卡1落盘的 docx
- **产出:** 第6~7章 LLM 1 次批生成 md 落盘 `chapter_md/ch6~ch7.md` → `office_open` 接续 → 第5章 chapter5.md 直接 `doc_insert_markdown` 导入（不重算）+ 第6/7章整章导入 + 设备照片 `doc_insert_image` → 格式修复链 → `office_save` 落盘
- **完成标记:** `kanban_complete(metadata={"report_path": "..."})`

#### Step 5c — 报告卡3（收尾章）

- **Worker:** author Profile（技能同上）
- **输入:** data.json + indicators.json + validation.json + 卡2落盘的 docx
- **产出:** 第8章 LLM 生成 md 落盘 `chapter_md/ch8.md` 整章导入 → 格式修复链 → 附录1~7（officecli）→ 收尾三件套（目录/缩进/页眉分隔线）→ 水印 → PDF 签章（双文件交付）
- **完成标记:** `kanban_complete(metadata={"report_path": "...", "pdf_path": "..."})`

**三卡铁律（防口径分裂）**：所有数值一律从 data.json / indicators.json / chapter5.md 读取，禁止从前序章节文本提取数值；每卡完成必须 `office_save` 落盘后再 `kanban_complete`；卡2/卡3 用 `office_open` 接续编辑，禁止重建文件；**正文写入禁逐段 `doc_insert_paragraph_with_text`，一律 `doc_insert_markdown` 整章导入**（图片嵌入、封面表模板注入例外），导入后跑格式修复链（序列见 ea-authoring/references/docx-techniques.md「md 导入与格式修复链」）。

#### Step 6 — V3 报告审查（REPORT_REVIEW）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core + energy-audit-report-qa 口径）
- **输入:** 报告 .docx + data.json
- **产出:** report_review.json（跨章一致性+格式规范+结论完整性；P0→block / P1P2→记录）
- **完成标记:** `kanban_complete(metadata={"report_review_path": "..."})`

### 一个项目 = 一份报告

- 一个公共机构可能包含多栋建筑
- 全部建筑的数据存在一个 config.json 中
- 采集步骤一次处理所有建筑的数据
- 生成一份涵盖所有建筑的完整审计报告

### 并行度控制

```yaml
## ~/.hermes/config.yaml
kanban:
  dispatch_in_gateway: true
  max_in_progress: 5            # 全局最多同时 5 个任务
  dispatch_interval_seconds: 30
  failure_limit: 2
```

---

## 监控与干预指南（原 monitoring）

### 常规监控

#### 一眼看进度
```bash
## 任务板快照（计数统计）
hermes kanban list --tenant <slug>

## 只看运行中的
hermes kanban list --tenant <slug> --status running

## 只看阻塞的
hermes kanban list --tenant <slug> --status blocked
```

#### 自动监控
```bash
## 每 30 秒自动扫描
python scripts/monitor.py --tenant <slug>

## 一次快照
python scripts/monitor.py --tenant <slug> --once
```

#### 实时事件流
```bash
hermes kanban watch --tenant <slug>
```

### 常见问题诊断

#### 任务卡在 running（心跳超时）

**症状:** 状态 running 但无心跳 > 5 分钟

**诊断:**
```bash
hermes kanban show <task_id>
## 查看 runs 历史和最后 heartbeat_at
```

**常见原因:**
1. Worker 进程已死但未通知 kanban → `hermes kanban reclaim <task_id>`
2. Worker 陷入死循环 → 同上
3. 模型 API 调用超时 → 减小任务 body 的 max_runtime

#### 任务反复失败

**症状:** 同一任务 retries ≥ 2 次

**诊断:**
```bash
hermes kanban show <task_id>
## 查看每轮 error/summary/outcome
```

**常见原因和修复:**
1. **缺少依赖** (pandas/psycopg2)
   → 在 Profile 的 venv 中安装: `hermes -p <profile> -- pip install xxx`
2. **API key 缺失**
   → 检查 `~/.hermes/.env` 中相应 key
3. **输入文件不存在**（上游任务产出路径错误）
   → 检查上游任务的 metadata，修正路径

#### 阻塞任务堆积

**症状:** blocked 任务 > 3 个，且无评论说明

**处理:**
1. 逐个查看: `hermes kanban show <id>`
2. 阅读 block reason
3. 评估是否需要人工介入:
   - 数据缺失 → 补充数据后 `/unblock`
   - 诊断置信度不足 → 确认或驳回后 `/unblock`
   - API 不可用 → 等待恢复后 `/unblock`

#### 某项目报告不合格

**处理:**
```bash
## 1. 在报告任务上评论反馈
hermes kanban comment <report_task_id> "第7章建议重复，第5章床位数应为4389"

## 2. 创建修正任务（父任务=原报告任务）
hermes kanban create "修正报告 - <楼名>" \
    --assignee <reporter_profile> \
    --parents <report_task_id> \
    --body "根据评论修正报告。原报告:<path>。修正项:..."
```

### 干预速查

| 场景 | 命令 |
|------|------|
| 卡死任务 | `hermes kanban reclaim <id>` |
| 换 Profile | `hermes kanban reassign <id> <新Profile>` |
| 手动完成 | `hermes kanban complete <id> --summary "..."` |
| 补充评论 | `hermes kanban comment <id> "反馈内容"` |
| 解除阻塞 | `hermes kanban unblock <id>` |
| 撤销任务 | `hermes kanban archive <id>` |
