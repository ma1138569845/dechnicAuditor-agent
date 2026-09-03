# Kanban Worker 模式下的 Profile SOUL.md 原则

## 核心规则

**SOUL.md 只写领域专有能力，不写框架生命周期。**

Hermes Kanban dispatcher 启动 Worker 时自动注入：
- `HERMES_KANBAN_TASK` 环境变量
- `KANBAN_GUIDANCE` 系统 Prompt 块（含完整的：读任务→执行→kanban_complete/block→heartbeat 流程）
- `--skills kanban-worker` 参数（如任务配置了）

Worker 无需在 SOUL.md 中重复这些通用指令。

## 正确示例（DataCollection 的 SOUL.md）

```markdown
你是 DataCollection，专业的数据采集专家。

## 核心能力
1. PG数据库采集：连接10.10.1.165:5432/dc_energy_audit2
2. 多源合并：PG > Config > 对话，三级兜底
3. 缺失字段标注【待补充】，不编造

## 工作原则
- 每个字段标注来源
- 输出 data.json 到任务指定的路径
```

## 错误示例（不要这样做）

```markdown
## Kanban Worker 模式

1. 读任务 — kanban_show() 获取任务标题    ← 框架已处理
2. 提交结果 — kanban_complete(...)          ← 框架已处理
3. 心跳 — kanban_heartbeat(...)             ← 框架已处理
```

**这些是框架责任，不是 Profile 的"角色定义"。**

## 例外

如果 Profile 有特殊的提交格式要求（如 metadata 必须包含特定字段），可以在 SOUL.md 中说明 **格式约定**，而非流程步骤：

```markdown
## 输出约定
提交时 metadata 需包含:
- data_path: 输出文件绝对路径
- source_summary: {pg_count: N, config_count: N, missing_count: N}
```
