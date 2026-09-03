# 能源审计Agent架构模式：独立Profile vs delegate_task子Agent

## 背景

能源审计流水线涉及多个Agent协作。有两种实现方式，适用场景不同。

## 两种模式对比

| 维度 | 独立Profile | delegate_task子Agent |
|------|-------------|---------------------|
| 启动方式 | `hermes -p <name>` 或包装脚本 | 由主Agent通过delegate_task派发 |
| 人格/角色 | SOUL.md独立设定 | 继承主Agent人格 |
| 配置隔离 | 独立config.yaml（模型/工具集/超时等） | 共享主Agent配置 |
| 密钥隔离 | 独立.env | 共享主Profile密钥 |
| 交互能力 | 可与用户对话、引导确认 | 静默执行，不可与用户交互 |
| 适用场景 | 需要用户交互、独立人格的任务 | 纯后台计算任务 |
| 典型例子 | DataCollection, DataVA | 小方(指标计算), 小德(文本生成) |

## 决策指南

### 使用独立Profile when

Agent需要与用户交互（引导确认、展示报告、等待反馈）。

典型场景：
- **DataCollection** — 采集后向用户报告缺失项，引导补充
- **DataVA** — 逐项展示异常，等待用户确认/驳回/填写原因
- 任何需要独立人格、独立工具集配置的Agent

### 使用delegate_task子Agent when

Agent是纯后台计算、无需用户交互。

典型场景：
- **小方** — 指标计算（5项指标+三级兜底）
- **小德** — 报告文本生成（按模板填充+LLM润色）
- **小诚** — 知识库检索（Qdrant/KG查询返回结果）

## Profile 结构模板

```
~/.hermes/profiles/<name>/
├── profile.yaml       # 描述 + description_auto: false
├── config.yaml        # 轻量配置（模型/工具集/超时/禁用无关工具）
├── SOUL.md            # 人格设定（角色定位+核心能力+工作原则+行为边界）
├── .env               # 密钥（可选，继承主环境时空着）
├── <name>.bat         # Windows启动脚本
└── <name>.sh          # Git Bash启动脚本
```

### config.yaml 要点

```yaml
model:
  base_url: https://api.deepseek.com/v1
  default: deepseek-v4-flash
  provider: deepseek
toolsets:
  - hermes-cli
agent:
  max_turns: 50
  disabled_toolsets:
    - browser
    - vision
    - image_gen
    # 禁用本Agent不需要的工具集
terminal:
  cwd: D:\data\pyProject\dc_agent\dc-eau-agent
display:
  language: zh
memory:
  memory_enabled: false    # 验证类Agent不需要记忆持久化
  user_profile_enabled: false
skills:
  disabled:
    - agent-xiaocheng     # 禁用不相关的技能
curator:
  enabled: false
```

### SOUL.md 结构

```
你是<Agent名>，同方德诚能源审计智能体——专业<职责描述>。

## 角色定位
- <职责1>
- <职责2>

## 核心能力
1. <能力1>
2. <能力2>

## 工作原则
- <原则1>
- <原则2>

## 输入/输出规范
<输入来源和格式>
<输出格式和位置>

## 行为边界
<不能做什么>
```

### 启动脚本模板（bat）

```batch
@echo off
chcp 65001 >nul
REM <Agent名> — 启动脚本

where hermes >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 找不到 hermes 命令
    pause
    exit /b 1
)

if "%1"=="" (
    hermes -p <profile名>
) else (
    hermes -p <profile名> --startup "Run <任务描述> for project: %*"
)
```

## 数据流：Profile间协作

```
DataCollection (datacollection Profile)
    ↓ ~/projects/energy-audit/<name>/data.json（project_data.py::save_project）
DataVA (datava Profile)
    ↓ validation.json + diagnosis_chapter7_material.txt
小同  ← delegate_task → 小方(指标) + 小德(文本)
    ↓
报告生成
```

## v2.0 合并方案：Skill → Profile SOUL.md

**背景**: 之前同一个 Agent 同时在 Profile SOUL.md 和 `agent-*` Skill 中定义了角色，两处内容不一致。

**合并方向**: Skill SKILL.md 内容合并到 Profile SOUL.md，删除独立 `agent-*` 技能目录。
Profile 是运行主体，Skill 是辅助知识。

**合并后 always_load**:
```yaml
skills:
  always_load:
    - energy-audit  # 共享知识库（公式/标准/格式）
```

**保留的技能**: 只保留 `energy-audit`（共享知识）和 `kanban-energy-audit-orchestrator`（编排器）。
**删除的技能**: agent-datacollection, agent-datava, agent-caliber, agent-xiaode, agent-xiaofang, agent-xiaoshu, agent-xiaocheng, energy-audit-multi-agent, energy-audit-orchestration。

## Kanban Worker 模式注意

- **不要**在 SOUL.md 中写入 Kanban Worker 生命周期指令（kanban_show/kanban_complete 等）。框架通过 `HERMES_KANBAN_TASK` 环境变量和 KANBAN_GUIDANCE 系统 prompt 自动注入。
- Task body 中的所有路径必须在 bootstrap 时展开为绝对路径，不依赖 shell 变量。

## Pitfalls

- **不要给Profile过量技能** — 只加载必要的技能，其他用 `skills.disabled` 禁用
- **Profile间的数据共享通过文件** — 上游 kanban_complete 的 metadata 传递输出路径
- **记忆（memory）关闭** — 验证/采集类Profile不需要跨session记忆
- **Skill vs Profile 不重复定义** — 同一 Agent 信息只在一处维护（Profile SOUL.md）
