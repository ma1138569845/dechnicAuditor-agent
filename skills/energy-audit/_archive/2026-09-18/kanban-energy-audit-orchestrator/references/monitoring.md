# 监控与干预指南

## 常规监控

### 一眼看进度
```bash
# 任务板快照（计数统计）
hermes kanban list --tenant <slug>

# 只看运行中的
hermes kanban list --tenant <slug> --status running

# 只看阻塞的
hermes kanban list --tenant <slug> --status blocked
```

### 自动监控
```bash
# 每 30 秒自动扫描
python scripts/monitor.py --tenant <slug>

# 一次快照
python scripts/monitor.py --tenant <slug> --once
```

### 实时事件流
```bash
hermes kanban watch --tenant <slug>
```

## 常见问题诊断

### 任务卡在 running（心跳超时）

**症状:** 状态 running 但无心跳 > 5 分钟

**诊断:**
```bash
hermes kanban show <task_id>
# 查看 runs 历史和最后 heartbeat_at
```

**常见原因:**
1. Worker 进程已死但未通知 kanban → `hermes kanban reclaim <task_id>`
2. Worker 陷入死循环 → 同上
3. 模型 API 调用超时 → 减小任务 body 的 max_runtime

### 任务反复失败

**症状:** 同一任务 retries ≥ 2 次

**诊断:**
```bash
hermes kanban show <task_id>
# 查看每轮 error/summary/outcome
```

**常见原因和修复:**
1. **缺少依赖** (pandas/psycopg2)
   → 在 Profile 的 venv 中安装: `hermes -p <profile> -- pip install xxx`
2. **API key 缺失**
   → 检查 `~/.hermes/.env` 中相应 key
3. **输入文件不存在**（上游任务产出路径错误）
   → 检查上游任务的 metadata，修正路径

### 阻塞任务堆积

**症状:** blocked 任务 > 3 个，且无评论说明

**处理:**
1. 逐个查看: `hermes kanban show <id>`
2. 阅读 block reason
3. 评估是否需要人工介入:
   - 数据缺失 → 补充数据后 `/unblock`
   - 诊断置信度不足 → 确认或驳回后 `/unblock`
   - API 不可用 → 等待恢复后 `/unblock`

### 某项目报告不合格

**处理:**
```bash
# 1. 在报告任务上评论反馈
hermes kanban comment <report_task_id> "第7章建议重复，第5章床位数应为4389"

# 2. 创建修正任务（父任务=原报告任务）
hermes kanban create "修正报告 - <楼名>" \
    --assignee <reporter_profile> \
    --parents <report_task_id> \
    --body "根据评论修正报告。原报告:<path>。修正项:..."
```

## 干预速查

| 场景 | 命令 |
|------|------|
| 卡死任务 | `hermes kanban reclaim <id>` |
| 换 Profile | `hermes kanban reassign <id> <新Profile>` |
| 手动完成 | `hermes kanban complete <id> --summary "..."` |
| 补充评论 | `hermes kanban comment <id> "反馈内容"` |
| 解除阻塞 | `hermes kanban unblock <id>` |
| 撤销任务 | `hermes kanban archive <id>` |
