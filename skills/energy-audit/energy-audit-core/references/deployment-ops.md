# deployment-ops
> 本文由 3 个文件合并而成（2026-09-18 瘦身合并第 2 组，原文件已归档至 `_archive/2026-09-18/energy-audit-core/references/`）：`deployment-prerequisites.md`、`hermes-operations.md`、`auxiliary-vision-config.md`；内容逐字保留，仅统一标题层级，引用请一律指向本文件对应小节。

---

## 部署前提清单（新机/换机自检；原 deployment-prerequisites）

> 适用：直跑轨（default）与 kanban 轨（editor）全部角色。任一失败先修复再开工，勿在断链环境上启动流水线。
> 首次核对：2026-09-17（逐条实跑验证）。

### 一、必须项

| 项 | 要求 | 自检锚点 |
|---|---|---|
| 仓库 | `D:\data\pyProject\dc_agent\dechnicAuditor-agent`（含 `tools/energy_audit/` 全套工具链；命令从 repo 根执行） | `tools/energy_audit/` 存在 |
| Python | repo 自带 `.venv`（Python 3.11.14）；依赖：psycopg2 / python-docx / lxml / numpy / pandas / requests / graphviz / PyMuPDF(fitz) / Pillow / pywin32 | 自检 ② |
| PostgreSQL | `10.10.1.165:5432 / dc_energy_audit2`；密码解析链：显式参数 → `EA_PG_*`（旧 `DB_*`）环境变量 → `{HERMES_HOME}/config.yaml` → 包内 config.yaml 默认（密码无内置默认值，缺失即报错） | 自检 ① |
| Microsoft Word | **桌面版**（COM 自动化，收尾器导出 PDF 用）；渲染字体：宋体 / 黑体 / Cambria Math / Wingdings / Times New Roman | 自检 ⑤ |
| Graphviz | 已安装于 `C:\Program Files\Graphviz\bin`；`energy_flow_chart.py` 会自动将常见路径注入 PATH（无需系统级配置）。**2026-09-24 起图5.1 主引擎改为纯 matplotlib 的 `energy_flow_chart_v3.py`，本项只在旧图兜底时用到** | `"C:/Program Files/Graphviz/bin/dot.exe" -V` |
| Hermes 侧 | `HERMES_HOME`（profiles / config.yaml / rag）；技能已发布并校验对齐 | 自检 ③ |
| 项目数据根 | `~/projects/energy-audit/<单位全称>/`（`HERMES_PROJECTS_ROOT` 可覆盖） | 目录存在 |

### 二、自检命令（逐条可复制，从 repo 根运行）

```bash
## ① PG 连通（走 db_config 解析链，无需手写密码）
.venv/Scripts/python.exe -c "from tools.energy_audit.db_config import get_pg_config; import psycopg2; c=get_pg_config(); psycopg2.connect(host=c['host'], dbname=c['database'], user=c['user'], password=c['password'], connect_timeout=5); print('PG OK')"
## ② venv 依赖 + 工具链导入
.venv/Scripts/python.exe -c "import psycopg2, docx, fitz, win32com, graphviz, numpy, pandas, requests, lxml; import tools.energy_audit.pg_collector; print('DEPS+TOOLS OK')"
## ③ 技能发布对齐（只读；「总变更 0 文件，删除 0 文件」= 已对齐，非 0 走 sync 发布流程）
.venv/Scripts/python.exe scripts/sync_ea_skills.py --dry-run | tail -2
## ④ file base_url（建筑照片下载，缺失时自动回退 DB 主机）
.venv/Scripts/python.exe -c "from tools.energy_audit.db_config import get_file_base_url; print(get_file_base_url())"
## ⑤ Word COM 可用
.venv/Scripts/python.exe -c "import win32com.client as w; app=w.DispatchEx('Word.Application'); print('Word COM OK'); app.Quit()"
```

> 备注：`--dry-run` 与 `--verify` 均为只读（2026-09-17 修复 verify 误写盘问题）；`--verify` 以退出码报告一致性：非 0 = 存在待发布差异或 profile 不一致。

### 三、说明

- kanban 轨的 workspace / 租户前置另见 `kanban-energy-audit-orchestrator/references/kanban-setup.md`（环境前置检查节）。
- 环境变量（`EA_TOOLS_ROOT` / `HERMES_PROJECTS_ROOT` / `EA_REFERENCE_DIR` 等）均为可选覆盖；缺省按三级降级自动解析。
- 技能发布为单源：repo `skills/energy-audit/` → `scripts/sync_ea_skills.py` → 主库 + 6 角色 profile；勿手工复制。

### 四、技能包 ↔ repo 的同步（**唯一入口 `deploy_ea_skills.py`**）

> **权威源（2026-09-20 决定 A）**：技能内容的**唯一权威源是技能包镜像**
> —— `E:\杂\chatgpt技能包\energy-audit-v2\repo\skills\energy-audit\`。
> 发布是**两级单向链**，任一级都不许手工复制：
>
> ```
> 技能包镜像（权威，人工编辑）
>    └─ deploy_ea_skills.py ──► repo  skills/energy-audit/   （D 盘，git 管理）
>                                   └─ sync_ea_skills.py ──► 主库 + 6 角色 profile
> ```
>
> 要改技能内容 → **只改镜像** → 跑 `deploy_ea_skills.py`（它内部会接着跑 sync 并 `--verify`）。
> 反过来（repo 侧被改、镜像落后）→ 跑 `deploy_ea_skills.py --backport --yes` 回流，
> 再回到正常链路。**不要在 repo 侧直接改技能**，否则镜像与 repo 立刻分叉。

> **镜像已纳入 git（2026-09-22 起）**：`repo/` 目录本身是独立 git 库（分支 `main`，**纯本地、无远端**）。
> 此前镜像是"不在任何 VCS 内"的状态——出现并行写入者后，改完未发布就出事故**没有 diff 可回滚**
> （只能靠发布到 D 盘 repo 的那一跳留痕）。现行标准四步：
> **改镜像 → 在镜像里 commit → 跑 `deploy_ea_skills.py` → 在 D 盘 repo commit（必要时 push）**。
> 镜像库的 `.gitignore` 有意排除 `__pycache__/`、`*.pyc`、`_deploy/last_deploy.json`（每次发布重写的机器状态）；
> 位于 `repo/` 之外的 `_changes/`（草稿区：备份与临时产物）、`profiles/`（sync 生成物）、
> `_sandbox_*/`、`_snapshot_原文/`、`_包外附件/` **均不在**该库内。
> **草稿区已于 2026-09-23 清空**（原 465 文件 / 128.1 MB）：其中 200 个页面渲染 PNG（86 MB，
> 可由 PDF 再生）与缓存直接删除；13 个标准 PDF + 脚本/记录/JSON（265 项 / 41.7 MB）打包成
> `energy-audit-v2/_archive_drafts_20260923.zip`（36.2 MB）；`_changes/` 现为空目录（脚本仍可写入）。
> 包内文档引用过的草稿区脚本/记录（`audit_checks.py`、`audit_overlap_detail.py`、`pdf_to_text.py`、
> `T2-直跑验证记录.md`、`test_deploy_guard*.py`、`probe_bed_fields.py`、`verify_bed_chain.py` 等）
> **都在该 zip 里**，恢复：`Expand-Archive -LiteralPath <zip> -DestinationPath <_changes> -Force`。
> 取回历史里的已删文件：`git -C <镜像> show <commit>:<path>`（例：`1a30ad0:_deploy/backport_backup_manifest.md`）。

> **背景（2026-09-20 事故）**：此前用 `robocopy /MIR` 把技能包镜像**整体**覆盖到
> repo `skills/energy-audit`，抹掉了目标侧未提交的文件改动，git 层面无法恢复。
> 同日还发现 repo 有**第二个写入者**（另一会话在同分支连续提交），
> 因此"目标可能既脏、又领先于镜像"。`/MIR` 从此**禁用**。

**唯一入口**是 `scripts/deploy_ea_skills.py`（技能包 `repo/scripts/` 下，与 `sync_ea_skills.py` 同目录）：

```bash
# 1) 先看差异与阻挡项（只读，永远先跑这一步）
python scripts/deploy_ea_skills.py --check

# 2) 正常发布：只复制有差异的文件，发布后自动 sync 到 profiles 并 --verify
python scripts/deploy_ea_skills.py

# 3) 镜像落后于目标（目标领先且已提交）→ 反向回流，先备份镜像侧
python scripts/deploy_ea_skills.py --backport --yes
```

**它守两条线**（任一命中即停止，不做任何改动）：

| 守卫 | 判据 | 说明 |
|---|---|---|
| 脏文件守卫 | 将被覆盖/删除的目标文件在 git 里是脏的 | 未提交 = 覆盖即永久丢失 |
| 部署基线守卫 | 目标文件内容 ≠ 上次发布时记下的哈希 | 说明目标侧被**别人**改过（可能已提交） |

基线记在技能包 `repo/_deploy/last_deploy.json`（不在发布范围内，不进 skills 目录）。
两条出路：确认可覆盖 `--force`；确认目标领先是正常的 `--adopt`（把现状登记为新基线）。

> 铁律：**镜像与 repo 谁都不是"永远权威"**——`--check` 先说话。发布前若 `--check` 报阻挡，
> 先弄清差异归属（谁的改动、提没提交），再决定 `--force` / `--backport` / `--adopt`。

---

## Hermes 会话/Token/多 profile 运维（原 hermes-operations）

能源审计报告编制通常是长时间多轮对话，需要关注 Token 消耗。以下操作通过 `state.db` 管理会话。

### state.db 位置

```
~/AppData/Local/hermes/state.db   # Windows — HERMES_HOME 目录
~/.hermes/state.db                # macOS/Linux
```

> **Windows 上注意**：`HERMES_HOME` = `C:\Users\<user>\AppData\Local\hermes`，而 `~/.hermes`（`C:\Users\<user>\.hermes`）是另一个独立目录。profile 实际有效路径在 `HERMES_HOME/profiles/<name>/`，而非 `~/.hermes/profiles/<name>/`。旧 `~/.hermes/profiles/` 下的空壳目录可安全删除。

### 查询所有会话及 Token 消耗

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

### sessions 表关键字段

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

### 删除指定会话

```python
import sqlite3
conn = sqlite3.connect(os.path.expanduser('~/AppData/Local/hermes/state.db'))
sid = '20260626_121305_ef9ff053'  # 替换为实际ID
conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
conn.commit()
conn.close()
```

### 清空所有会话

```bash
rm ~/AppData/Local/hermes/state.db  # 重启 Hermes 自动重建
```

### Token 管理建议

- 长会话（>500条）每次对话都发送完整历史，token 消耗线性增长
- 使用 `/new` 或开新会话开始新主题
- session_search 可以在不加载历史的情况下回顾此前内容
- 关注 `input_tokens` 远大于 `output_tokens` 是正常的（历史上下文 + tool schemas）

### 多Profile运维（能源审计部署用）

能源审计部署使用 **6 个角色 profile**：`datacollection` / `datava` / `caliber` / `author` / `editor` / `knowledger`（另常用 `default` 作为主对话入口）；每个 profile 可各自绑定飞书 bot。
profile 名单、技能安装矩阵与职责见 `kanban-energy-audit-orchestrator/references/role-definitions.md`（技能由 `scripts/sync_ea_skills.py` 单向发布，勿手工改 profile 侧技能）。

#### 目录结构

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

#### 常用命令

```bash
## 列出所有profile及gateway状态
hermes profile list
hermes gateway list

## 在指定profile下执行命令
hermes -p <profile> ...

## 查看/切换 profile
hermes profile show <name>         # 查看profile详情
hermes profile use <name>          # 设置默认profile

## Gateway 管理（每个profile独立）
hermes -p <profile> gateway status     # 查看状态
hermes -p <profile> gateway restart    # 重启（.env 或 SOUL.md 变更后必须重启）
hermes -p <profile> gateway start      # 启动
hermes -p <profile> gateway stop       # 停止
```

#### .env 文件管理

`patch` 工具对 `.env` 文件受保护（defense-in-depth），必须用 `sed` 操作：

```bash
## 替换已有key
sed -i 's|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=sk-xxx|' .env

## 追加新key（注意 >>）
printf 'NEW_KEY=value\n' >> .env
```

**.env 修改后必须重启对应profile的gateway**才能生效（当前CLI/TUI会话不受影响）。

#### 飞书bot配置

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

#### 清理残留profile目录

`Path.home()/.hermes/profiles/` 下可能有不完整的骨架目录（只有`logs/`和`skills/`，没有配置文件的空壳）。`hermes profile list` 不显示它们，可直接删除：

```bash
rm -rf ~/.hermes/profiles/<empty-profile-name>
```

#### 各profile API key 管理

更换API key后需更新每个 profile 的 `.env` 并重启对应 gateway。

- 主模型 API key 可在各 profile 间共用一把（按部署策略决定）
- 飞书各用各的 AppId/AppSecret，可驻留在同一个飞书群（不同 bot）

#### SOUL.md 人格设定

每个profile可通过 `SOUL.md` 自定义对话人格。文件位于 profile 根目录下：

```bash
## 每个角色一份
C:\Users\<user>\AppData\Local\hermes\profiles\<profile>\SOUL.md
```

推荐结构（能源审计角色统一采用）：人格 → 职责边界 → 专业标准（不含具体数值）→ 权威指针 → 执行契约；
编写依据见 `energy-audit-core/references/soul-purity-principle.md`（SOUL 只写领域能力，不写 kanban 生命周期等框架指令），
源文件在 repo `skills/energy-audit/_soul/<role>.md`，由 `sync_ea_skills.py` 发布。示例：

```markdown
## <Role> — 同方德诚能源审计智能体

### 人格
（3-5 行：专业身份、工作风格、面对不确定数据时的态度）

### 职责边界
- 负责：…／不负责：…（指向其他角色）／输入 → 输出

### 专业标准（不含具体数值）
- 不编造数据；数值口径以 AUTHORITY-INDEX 指定的唯一权威为准

### 权威指针（只写路径，不抄内容）
- 本角色专属：<skill>/SKILL.md
- 总索引：energy-audit-core/references/AUTHORITY-INDEX.md

### 执行契约
（命令 / 退出码 / 产物路径——与 SKILL 保持一致，不重复解释）
```

**SOUL.md 修改后需重启对应profile的gateway**才能在新会话中生效（已有会话不受影响）。

---

## 视觉模型配置（DeepSeek V4.1-Flash 为主；原 auxiliary-vision-config）

> **2026-10-22 更新**：DeepSeek 已提供原生视觉输入。第3章荣誉证书复核统一使用
> `deepseek-flash`，不再以“DeepSeek 不支持视觉”为前提。Qwen-VL 仅作为其他图片识别
> 场景的可选备用，不参与证书的默认决策链。

### 证书核验的不变边界

数据库绑定是主判据，视觉模型只是第二层复核：

1. `prepare_report_photos.py` 先按
   `energy_saving.award_name + statistical_year + award_certificate(file_id)`
   建立数据库绑定。
2. 只有证书名称及年份能唯一确定时才配图；多候选时停止配图并要求把名称/年份写进图注。
3. 候选证书再交给 `deepseek-flash` 核对图片中的标题和受奖单位。
4. `pass` 放行；`review`、`unverified` 保留确定性候选并提示。
   `mismatch` 默认只说明“视觉读数与数据库描述不一致”，仍保留数据库候选并提示人工复核；
   只有显式传入 `--certificate-policy strict` 才排除冲突图片。这样可容纳“平台用综合荣誉名
   归并具体奖项证书”等经人工确认的故意差异。
5. 核验结果写入 `<项目>/photo_vision_checks.json`。缓存键包含图片 SHA-256、
   预期标题、受奖单位、模型名及提示词版本；`--dry-run` 不写缓存。

### DeepSeek 配置

`photo_vision.py` 从环境变量或 Hermes 本机 `.env` 读取：

```text
DEEPSEEK_API_KEY=...
```

查找顺序：

1. 当前进程环境变量 `DEEPSEEK_API_KEY`
2. `%HERMES_HOME%\.env`
3. `%LOCALAPPDATA%\hermes\.env`

默认参数：

| 项 | 值 |
|---|---|
| 模型 | `deepseek-flash` |
| 基础地址 | `https://api.deepseek.com` |
| 接口 | `/chat/completions`（OpenAI 兼容图片消息格式） |

无需在 `config.yaml` 中另建 `auxiliary.vision` 节点；证书模块直接读取
`DEEPSEEK_API_KEY`。密钥缺失、网络失败、超时或返回无法解析时，统一降级为
`unverified`，并保留数据库已唯一选出的候选。

### 冒烟测试

用实际证书图片执行一次单图核验，确认返回的是模型结果而非
“未配置 API Key / 网络异常”。运行输出和 `photo_vision_checks.json` 中不得写入密钥。

### Qwen-VL 备用

设备铭牌、仪表读数、建筑图纸等其他视觉任务仍可按需配置 DashScope
`qwen-vl-max`；这只是备用能力，不改变第3章证书的数据库绑定规则。
