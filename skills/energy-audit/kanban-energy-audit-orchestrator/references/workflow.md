# 能源审计 Kanban 工作流详解

> knowledger profile 不在本任务图内（知识库/问答辅助角色，见 role-definitions.md 顶部说明）。

## 任务图结构

每个公共机构项目生成 6 个父子链接的 Kanban 任务 + 1 个汇总 Director
（DataVA 在三个检查点各介入一次，与 bootstrap_pipeline.py 一致）：

```
Director (汇总审查)
  └─ Project A: 采集 (datacollection)
      └─ V1 验证 DATA_CHECK (datava)
          └─ 计算 (caliber)
              └─ V2 指标复核 INDICATOR_REVIEW (datava)
                  └─ 报告 (author)
                      └─ V3 报告审查 REPORT_REVIEW (datava) ──┐
  ...（各项目并行）                                            │
Director ←────────────────────────────────────────────────────┘
```

- **纵向**（同一项目）：严格串行，前一步完成 → 后一步自动晋升 ready
- **横向**（不同项目）：完全并行，互不依赖
- **Director**：所有项目报告完成后触发，assignee = profiles["director"]（推荐 editor 专职汇总审查，与 author 写作分离；缺省回退 reporter）

## 每步任务详解

### Step 1 — 数据采集

- **Worker:** datacollection Profile（技能: ea-datacollection + energy-audit-core + energy-audit-pg-data）
- **输入:** config.json（复制到 workspace）
- **产出:** data.json（项目基础数据+能耗+建筑+设备+人员+图片+指标预计算）
- **完成标记:** `kanban_complete(metadata={"data_path": "..."})`

### Step 2 — V1 数据验证（DATA_CHECK）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core + energy-audit-pg-data）
- **输入:** data.json
- **产出:** validation.json（完整性检查+异常检测+KG因果诊断+质量评级；P0→block / P1P2→记录）
- **完成标记:** `kanban_complete(metadata={"validation_path": "..."})`

### Step 3 — 指标计算

- **Worker:** caliber Profile（技能: ea-calculation + energy-audit-core + energy-audit-report）
- **输入:** validation.json + data.json
- **产出:** indicators.json + chapter5.md + charts/
- **完成标记:** `kanban_complete(metadata={"chapter5_path": "..."})`

### Step 4 — V2 指标复核（INDICATOR_REVIEW）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core）
- **输入:** indicators.json + chapter5.md
- **产出:** indicator_review.json（指标年际对比+对标合理性+数据一致性）
- **完成标记:** `kanban_complete(metadata={"indicator_review_path": "..."})`

### Step 5 — 报告生成

- **Worker:** author Profile（技能: ea-authoring + energy-audit-core + energy-audit-report + energy-audit-imitate）
- **输入:** chapter5.md + validation.json + data.json
- **产出:** 完整 8 章 .docx 能源审计报告
- **完成标记:** `kanban_complete(metadata={"report_path": "..."})`

### Step 6 — V3 报告审查（REPORT_REVIEW）

- **Worker:** datava Profile（技能: ea-validation + energy-audit-core + energy-audit-report-qa 口径）
- **输入:** 报告 .docx + data.json
- **产出:** report_review.json（跨章一致性+格式规范+结论完整性；P0→block / P1P2→记录）
- **完成标记:** `kanban_complete(metadata={"report_review_path": "..."})`

## 一个项目 = 一份报告

- 一个公共机构可能包含多栋建筑
- 全部建筑的数据存在一个 config.json 中
- 采集步骤一次处理所有建筑的数据
- 生成一份涵盖所有建筑的完整审计报告

## 并行度控制

```yaml
# ~/.hermes/config.yaml
kanban:
  dispatch_in_gateway: true
  max_in_progress: 5            # 全局最多同时 5 个任务
  dispatch_interval_seconds: 30
  failure_limit: 2
```
