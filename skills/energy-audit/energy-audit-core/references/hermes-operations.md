# Hermes 会话管理 & Token 统计 & 多Profile运维

能源审计报告编制通常是长时间多轮对话，需要关注 Token 消耗。以下操作通过 `state.db` 管理会话。

## state.db 位置

```
~/AppData/Local/hermes/state.db   # Windows — HERMES_HOME 目录
~/.hermes/state.db                # macOS/Linux
```

> **Windows 上注意**：`HERMES_HOME` = `C:\Users\<user>\AppData\Local\hermes`，而 `~/.hermes`（`C:\Users\<user>\.hermes`）是另一个独立目录。profile 实际有效路径在 `HERMES_HOME/profiles/<name>/`，而非 `~/.hermes/profiles/<name>/`。旧 `~/.hermes/profiles/` 下的空壳目录可安全删除。

## 查询所有会话及 Token 消耗

```python
import sqlite3

conn = sqlite3.connect(os.path.expanduser('~/AppData/Local/hermes/state.db'))
cur = conn.cursor()
cur.execute('''SELECT id, source, title, message_count,
    datetime(started_at, 'unixepoch', 'localtime'),
    model, input_tokens, output_tokens, api_call_count
FROM sessions ORDER BY started_at DESC''')
for r in cur.fetchall():
    total = (r[6] or 0) + (r[7] or 0)
    print(f'{r[0][:28]} | {r[1]:6} | {r[3]:4}条 | 入:{r[6]} 出:{r[7]} 共:{total}')
conn.close()
```

## sessions 表关键字段

| 字段 | 说明 |
|------|------|
| `id` | 会话ID（格式：YYYYMMDD_HHMMSS_random） |
| `source` | tui / cli / feishu / telegram ... |
| `title` | 会话标题 |
| `message_count` | 消息总数 |
| `input_tokens` | 累计输入Token |
| `output_tokens` | 累计输出Token |
| `cache_read_tokens` | 缓存命中Token（省钱） |
| `estimated_cost_usd` | 估算费用（USD） |
| `started_at` | Unix时间戳 |

## 删除指定会话

```python
import sqlite3
conn = sqlite3.connect(os.path.expanduser('~/AppData/Local/hermes/state.db'))
sid = '20260626_121305_ef9ff053'  # 替换为实际ID
conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
conn.commit()
conn.close()
```

## 清空所有会话

```bash
rm ~/AppData/Local/hermes/state.db  # 重启 Hermes 自动重建
```

## Token 管理建议

- 长会话（>500条）每次对话都发送完整历史，token 消耗线性增长
- 使用 `/new` 或开新会话开始新主题
- session_search 可以在不加载历史的情况下回顾此前内容
- 关注 `input_tokens` 远大于 `output_tokens` 是正常的（历史上下文 + tool schemas）

## 多Profile运维（能源审计部署用）

能源审计部署使用 **6 个角色 profile**：`datacollection` / `datava` / `caliber` / `author` / `editor` / `knowledger`（另常用 `default` 作为主对话入口）；每个 profile 可各自绑定飞书 bot。
profile 名单、技能安装矩阵与职责见 `kanban-energy-audit-orchestrator/references/role-definitions.md`（技能由 `scripts/sync_ea_skills.py` 单向发布，勿手工改 profile 侧技能）。

### 目录结构

```
C:\Users\<user>\AppData\Local\hermes\           # HERMES_HOME
├── .env                                         # default profile 密钥
├── config.yaml                                  # default profile 配置
└── profiles\
    └── <profile>\                               # 例如 author / caliber / datava …
        ├── config.yaml                          # 模型/工具集/技能 always_load
        ├── profile.yaml                         # 描述
        ├── SOUL.md                              # 人格与职责（由 repo _soul/ 发布）
        ├── .env                                 # 密钥（可选）
        └── skills\energy-audit\                 # 该角色已发布的技能副本
```

> profile 目录同时存在于 `HERMES_HOME/profiles/`（有效）和 `Path.home()/.hermes/profiles/`（可能残留骨架目录）。`hermes profile list` 只认完整profile。

### 常用命令

```bash
# 列出所有profile及gateway状态
hermes profile list
hermes gateway list

# 在指定profile下执行命令
hermes -p <profile> ...

# 查看/切换 profile
hermes profile show <name>         # 查看profile详情
hermes profile use <name>          # 设置默认profile

# Gateway 管理（每个profile独立）
hermes -p <profile> gateway status     # 查看状态
hermes -p <profile> gateway restart    # 重启（.env 或 SOUL.md 变更后必须重启）
hermes -p <profile> gateway start      # 启动
hermes -p <profile> gateway stop       # 停止
```

### .env 文件管理

`patch` 工具对 `.env` 文件受保护（defense-in-depth），必须用 `sed` 操作：

```bash
# 替换已有key
sed -i 's|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=sk-xxx|' .env

# 追加新key（注意 >>）
printf 'NEW_KEY=value\n' >> .env
```

**.env 修改后必须重启对应profile的gateway**才能生效（当前CLI/TUI会话不受影响）。

### 飞书bot配置

纯 `.env` 驱动，不需要改 `config.yaml`：

| 环境变量 | 必填 | 说明 |
|---------|------|------|
| `FEISHU_APP_ID` | ✅ | 飞书开放平台应用的AppId |
| `FEISHU_APP_SECRET` | ✅ | AppSecret |
| `FEISHU_DOMAIN` | ❌ | 默认 `feishu` |
| `FEISHU_CONNECTION_MODE` | ❌ | 默认 `websocket`（推荐，不需要公网IP） |
| `FEISHU_ALLOW_ALL_USERS` | ❌ | 设为 `false` |
| `FEISHU_ALLOWED_USERS` | ❌ | 留空由pairing控制 |
| `FEISHU_GROUP_POLICY` | ❌ | 设为 `open` |
| `FEISHU_HOME_CHANNEL` | ❌ | 群聊chat_id，bot必须已在该群中 |

**配对批准**：
```bash
hermes -p <profile> pairing approve feishu <code>
```
批准后用户下一条消息自动识别。

### 清理残留profile目录

`Path.home()/.hermes/profiles/` 下可能有不完整的骨架目录（只有`logs/`和`skills/`，没有配置文件的空壳）。`hermes profile list` 不显示它们，可直接删除：

```bash
rm -rf ~/.hermes/profiles/<empty-profile-name>
```

### 各profile API key 管理

更换API key后需更新每个 profile 的 `.env` 并重启对应 gateway。

- 主模型 API key 可在各 profile 间共用一把（按部署策略决定）
- 飞书各用各的 AppId/AppSecret，可驻留在同一个飞书群（不同 bot）

### SOUL.md 人格设定

每个profile可通过 `SOUL.md` 自定义对话人格。文件位于 profile 根目录下：

```bash
# 每个角色一份
C:\Users\<user>\AppData\Local\hermes\profiles\<profile>\SOUL.md
```

推荐结构（能源审计角色统一采用）：人格 → 职责边界 → 专业标准（不含具体数值）→ 权威指针 → 执行契约；
编写依据见 `energy-audit-core/references/soul-purity-principle.md`（SOUL 只写领域能力，不写 kanban 生命周期等框架指令），
源文件在 repo `skills/energy-audit/_soul/<role>.md`，由 `sync_ea_skills.py` 发布。示例：

```markdown
# <Role> — 同方德诚能源审计智能体

## 人格
（3-5 行：专业身份、工作风格、面对不确定数据时的态度）

## 职责边界
- 负责：…／不负责：…（指向其他角色）／输入 → 输出

## 专业标准（不含具体数值）
- 不编造数据；数值口径以 AUTHORITY-INDEX 指定的唯一权威为准

## 权威指针（只写路径，不抄内容）
- 本角色专属：<skill>/SKILL.md
- 总索引：energy-audit-core/references/AUTHORITY-INDEX.md

## 执行契约
（命令 / 退出码 / 产物路径——与 SKILL 保持一致，不重复解释）
```

**SOUL.md 修改后需重启对应profile的gateway**才能在新会话中生效（已有会话不受影响）。
