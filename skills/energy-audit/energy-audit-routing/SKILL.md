---
name: energy-audit-routing
description: "能源审计任务转交：default→editor 唯一调度，采集/校验/报告归流水线。"
version: 1.1.0
author: DechnicAuditor
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [energy-audit, routing, profiles, multi-agent]
---

# 能源审计任务转交约定

## When to Use（触发条件）

用户提出涉及**某单位能源审计**的任务（数据收集/校验/核算/分析/报告编制）时，default（当前会话）**不自派执行**，统一转交 `editor` 编排。default 只做：日常对话、咨询答疑、任务转交、结果核验汇报。

## 调度边界（唯一调度者）

- **editor = 能源审计流水线唯一调度者**：编排 datacollection→datava→caliber→author 流水线、kanban 任务图、补采回路、Director 终审。
- **default = 用户日常入口 + 转交通道**：不自行拆派任务给执行 profile；判定任务需要实操时，唤醒 editor。
- **同一任务同一时间只有一个调度者：editor**。default 不创建 kanban 任务图、不直接唤醒执行 profile 干活。
- 接收default委派的能源审计项目报告的编制任务，并启动一个kanban任务图流水线，完成编制。

## 执行角色（由 editor 调度，default 不直接唤醒）

| Profile | 流水线环节 | 职责 |
|---|---|---|
| datacollection | 采集 | PG/Excel/Config 多源采集 → data.json |
| datava | 验证 | 完整性检查 + 异常 + KG 诊断（V1/V2/V3） |
| caliber | 指标计算 | 5项指标 + 定额对标 + 图表 + 第5章（待建） |
| author | 报告生成 | 8 章报告 docx（映射原设计 xiaode） |

## 转交操作模板

```bash
hermes -p editor chat -q "<任务描述>" -Q    # background=true, notify_on_complete=true
```

任务描述需包含：单位全称、任务类型（采集/校验/报告）、已知数据位置、上游产出路径、用户要求（如缺失数据必须标【待补充】）。

## 核验（default 保留质量把关）

editor 完成后，default 回读核验再向用户汇报：
- 读产出文件（data.json / 报告 docx）与 editor 会话库（`$LOCALAPPDATA/hermes/profiles/editor/state.db`）
- 确认新会话 `profile_name='editor'`，任务写入正确位置
- 产出异常时指出并退回，不直接报"完成"

## 硬约定

- **单位目录统一**：`C:\Users\Dechnic\projects\energy-audit\<单位全称>\`
- **数据真实性**：所有数字必须来自原始台账/账单，禁止编造
- **跨 profile 进程级隔离**：不共享上下文，靠文件 + 会话库交接，default 负责对账
- **成本透明**：每次唤醒是真实模型调用
