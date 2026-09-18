# 部署前提清单（新机 / 换机 / 换人自检）

> 适用：直跑轨（default）与 kanban 轨（editor）全部角色。任一失败先修复再开工，勿在断链环境上启动流水线。
> 首次核对：2026-09-17（逐条实跑验证）。

## 一、必须项

| 项 | 要求 | 自检锚点 |
|---|---|---|
| 仓库 | `D:\data\pyProject\dc_agent\dechnicAuditor-agent`（含 `tools/energy_audit/` 全套工具链；命令从 repo 根执行） | `tools/energy_audit/` 存在 |
| Python | repo 自带 `.venv`（Python 3.11.14）；依赖：psycopg2 / python-docx / lxml / numpy / pandas / requests / graphviz / PyMuPDF(fitz) / Pillow / pywin32 | 自检 ② |
| PostgreSQL | `10.10.1.165:5432 / dc_energy_audit2`；密码解析链：显式参数 → `EA_PG_*`（旧 `DB_*`）环境变量 → `{HERMES_HOME}/config.yaml` → 包内 config.yaml 默认（密码无内置默认值，缺失即报错） | 自检 ① |
| Microsoft Word | **桌面版**（COM 自动化，收尾器导出 PDF 用）；渲染字体：宋体 / 黑体 / Cambria Math / Wingdings / Times New Roman | 自检 ⑤ |
| Graphviz | 已安装于 `C:\Program Files\Graphviz\bin`；`energy_flow_chart.py` 会自动将常见路径注入 PATH（无需系统级配置） | `"C:/Program Files/Graphviz/bin/dot.exe" -V` |
| Hermes 侧 | `HERMES_HOME`（profiles / config.yaml / rag）；技能已发布并校验对齐 | 自检 ③ |
| 项目数据根 | `~/projects/energy-audit/<单位全称>/`（`HERMES_PROJECTS_ROOT` 可覆盖） | 目录存在 |

## 二、自检命令（逐条可复制，从 repo 根运行）

```bash
# ① PG 连通（走 db_config 解析链，无需手写密码）
.venv/Scripts/python.exe -c "from tools.energy_audit.db_config import get_pg_config; import psycopg2; c=get_pg_config(); psycopg2.connect(host=c['host'], dbname=c['database'], user=c['user'], password=c['password'], connect_timeout=5); print('PG OK')"
# ② venv 依赖 + 工具链导入
.venv/Scripts/python.exe -c "import psycopg2, docx, fitz, win32com, graphviz, numpy, pandas, requests, lxml; import tools.energy_audit.pg_collector; print('DEPS+TOOLS OK')"
# ③ 技能发布对齐（只读；「总变更 0 文件，删除 0 文件」= 已对齐，非 0 走 sync 发布流程）
.venv/Scripts/python.exe scripts/sync_ea_skills.py --dry-run | tail -2
# ④ file base_url（建筑照片下载，缺失时自动回退 DB 主机）
.venv/Scripts/python.exe -c "from tools.energy_audit.db_config import get_file_base_url; print(get_file_base_url())"
# ⑤ Word COM 可用
.venv/Scripts/python.exe -c "import win32com.client as w; app=w.DispatchEx('Word.Application'); print('Word COM OK'); app.Quit()"
```

> 备注：`--dry-run` 与 `--verify` 均为只读（2026-09-17 修复 verify 误写盘问题）；`--verify` 以退出码报告一致性：非 0 = 存在待发布差异或 profile 不一致。

## 三、说明

- kanban 轨的 workspace / 租户前置另见 `kanban-energy-audit-orchestrator/references/kanban-setup.md`（环境前置检查节）。
- 环境变量（`EA_TOOLS_ROOT` / `HERMES_PROJECTS_ROOT` / `EA_REFERENCE_DIR` 等）均为可选覆盖；缺省按三级降级自动解析。
- 技能发布为单源：repo `skills/energy-audit/` → `scripts/sync_ea_skills.py` → 主库 + 6 角色 profile；勿手工复制。
