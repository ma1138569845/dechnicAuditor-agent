# kanban-setup
> 本文并入 `plan-schema.md`、`examples.md`（2026-09-18 瘦身合并第 6 组，原文件已归档至 `_archive/2026-09-18/kanban-energy-audit-orchestrator/references/`）；内容逐字保留，仅统一标题层级。

---

## 环境搭建与配置规则（原 kanban-setup）

能源审计 Kanban 流水线的项目引导文档：工作区结构、Profile 配置规则、
初始任务创建模式、环境前置检查。配套脚本 `scripts/bootstrap_pipeline.py`
（输入 plan.json，见 kanban-setup.md（plan.json 结构一节）），模板 `assets/setup.sh.tmpl`。

### 项目工作区结构

一个公共机构 = 一个项目 = 一个工作区 = 一份报告：

```
~/projects/energy-audit/<slug>/
├── plan.json                      ← 项目输入（机构名/config/审计年度/角色映射，见 kanban-setup.md（plan.json 结构一节））
├── config.json                    ← 项目配置（复制进 workspace）
├── data.json                      ← Step1 采集产出（project_data.py::save_project 落盘）
├── validation.json                ← Step2 验证产出（V1 DATA_CHECK）
├── indicator_review.json          ← V2 指标复核产出
├── indicators.json                ← Step3 指标计算产出
├── chapter5.md                    ← Step3 第5章 Markdown
├── charts/                        ← Step3 图表 PNG
├── report_review.json             ← V3 报告审查产出
└── output/
    └── <单位全称>能源审计报告.docx  ← Step4 最终报告
```

**slug 规则**：项目名（机构全称）前若干字符，URL 友好。task body 中所有路径必须
**绝对路径**（如 `C:/Users/<user>/projects/energy-audit/<slug>/data.json`），
禁止用 shell 变量/相对路径——kanban worker 看不到主会话的环境变量（历史事故）。

### setup.sh 流程（assets/setup.sh.tmpl）

1. **环境检查** — hermes CLI 存在、5 个 profile 存在（4 执行 + editor Director）、kanban board 已初始化
2. **创建工作区** — 按上表建目录树
3. **复制配置** — config.json 复制进 workspace
4. **创建 Kanban 任务图** — 每项目 8 步串行任务（报告环节拆 3 卡）+ 1 个 Director 汇总（见 workflow.md）
5. **完成提示** — 监控命令/报告收集路径

### Profile 配置规则

每个 profile 的 `~/.hermes/profiles/<name>/config.yaml` 需要且只需要：

| 键 | EA 要求 | 说明 |
|----|---------|------|
| `toolsets` | `[hermes-cli, energy_audit]`（hermes-cli 提供 terminal/file/web 默认工具） | **必须有 energy_audit**（9 工具：PG 查询/RAG/仿写），否则 worker 看不到 pg_query 等工具会断链自建 psycopg2 脚本（2026-08 事故）；工具详解见 tools-reference.md |
| `terminal.cwd` | 指向 dechnicAuditor-agent repo（`D:\data\pyProject\dc_agent\dechnicAuditor-agent`） | 供 `from tools.energy_audit import ...` 导入 |
| `skills` | **不配置 always_load**，技能由 sync_ea_skills.py 按角色矩阵发布到 `<profile>/skills/energy-audit/` | 角色技能矩阵权威：references/role-definitions.md |

**禁止修改**：`approvals.mode`（安全设置）。`terminal.cwd` 与视频流水线规则不同
（视频版不碰 cwd，由 dispatcher `--workspace dir:` 覆盖；EA 版 worker 必须能导入
repo 工具链，故 cwd 固定指 repo）。

配置用 **PyYAML patch**（非字符串替换），改完回读校验。

### 技能发布前置（必做，2026-09 起）

发任务前必须先跑发布器，否则 worker 拿旧技能/无技能：

```bash
cd D:\data\pyProject\dc_agent\dechnicAuditor-agent
python scripts/sync_ea_skills.py && python scripts/sync_ea_skills.py --verify
## [校验] profile 侧不一致文件: 0  → 才能发 kanban
```

### SOUL.md per profile

- SOUL.md = 权威身份（角色定位/职责/输入输出/行为边界），**不内嵌数值与规则**——
  知识引用 `energy-audit-core/references/`（防失同步，见 core 的 soul-purity-principle.md）。
- editor（Director）的 SOUL 应含反代劳铁律："不亲自执行任务；对每个具体任务创建
  kanban 任务并指派；分解、路由、评论、批准——这就是全部工作。"
  （kanban 生命周期指引由框架自动注入每个 worker 的 system prompt，无需在 SOUL 重复。）
- 其他 profile 的 SOUL 简短：你是谁、读什么、产什么、用哪些技能工具、写到哪里。

### 初始 kanban 任务

```bash
hermes kanban create "<机构全称> 能源审计 — 数据采集" \
    --assignee datacollection \
    --workspace dir:"$HOME/projects/energy-audit/<slug>" \
    --tenant <slug> \
    --priority 2 \
    --max-runtime 30m \
    --body "使用 ea-datacollection 技能采集 PG 数据。
必须使用绝对路径：
  项目数据目录: C:/Users/<user>/projects/energy-audit/<slug>/
  输入 config.json: C:/Users/<user>/projects/energy-audit/<slug>/config.json
  产出 data.json 后 kanban_complete(metadata={'data_path': '<绝对路径>'})"
```

- `--workspace dir:<绝对路径>` **关键**：所有子任务共享该工作区；漏配或误用 worktree
  会隔离 profile、阻断产物共享。
- **tenant**：每个项目一个 tenant，任务板隔离，防止多项目交叉污染。

### 环境前置检查

```bash
## 1) PG 连通（worker 会直连取数）
python -c "import psycopg2; psycopg2.connect(host='10.10.1.165', dbname='dc_energy_audit2', user='postgres', password='<DB密码>', connect_timeout=5); print('PG OK')"
## 2) repo venv 依赖
cd D:\data\pyProject\dc_agent\dechnicAuditor-agent && .venv/Scripts/python.exe -c "import tools.energy_audit.pg_collector; print('tools OK')"
## 3) 技能已发布（见上）
## 4) file base_url（建筑照片下载，缺失时自动回退 DB 主机）
python -c "from tools.energy_audit.db_config import get_file_base_url; print(get_file_base_url())"
```

任一失败则中止，不发出会中途失败的 kanban。全量前提清单（新机/换机）见 `energy-audit-core/references/deployment-ops.md`（部署前提一节）。

### Critical rules

1. **workspace_kind="dir" + workspace_path="<绝对路径>"** 写进每个 kanban_create。
2. **tenant 每个任务**（`--tenant <slug>`）。
3. **幂等**：setup 类任务用 idempotency_key 或先检查存在性，防止重跑重复创建。
4. **max_runtime_seconds 按步设置**：采集 1800s / 验证 900s / 计算 1200s / 报告 1800s（默认）。
5. **心跳**：>5min 的任务周期性 `kanban_heartbeat`（progress 字段写阶段名+完成项数）。
6. **config.json 在任务发出前复制进 workspace**，不要让采集任务自行寻找。
7. **DB 写操作只在数据修复环节做**（带备份），kanban worker 默认只读 DB；
   worker 遇到 DB 数据错误 → V1 记 P0 block，不自行改库（改库由主会话执行并备份）。

---

## plan.json 结构定义（原 plan-schema）

`bootstrap_pipeline.py` 的输入。支持两种模式。

### 单项目模式

一个公共机构 = 一个项目 = 一份能源审计报告。

```json
{
  "project_name": "string — 公共机构全称",
  "slug": "string — URL 友好的标识符（可选，自动生成）",
  "config": "string — config.json 路径（含全部建筑数据）",
  "audit_type": "string — 'public_institution' | 'public_building' | 'industrial'",
  "institution_category": "string — '医疗' | '党政' | '教育' | '政务服务中心' | '场馆'（缺失时默认按医疗泛化基线处理，与 indicators.py 一致）",
  "audit_years": "number[] — 审计年度，如 [2022, 2023, 2024]",
  
  "profiles": {
    "collector": "string — 数据采集 Profile 名",
    "validator": "string — 数据验证 Profile 名",
    "calculator": "string — 指标计算 Profile 名",
    "reporter": "string — 报告生成 Profile 名",
    "director": "string — 汇总审查 Profile 名（推荐 editor 专职；缺省回退 reporter）"
  },

  "kanban": {
    "max_concurrent_projects": "number — 同时并行最大项目数（默认 5）",
    "max_runtime_per_task_seconds": "number — 单任务超时秒（默认 1800）",
    "failure_limit": "number — 失败重试上限（默认 2）"
  }
}
```

### 批量模式

多个公共机构同时编制报告。

```json
{
  "projects": [
    {
      "name": "string — 机构名称",
      "slug": "string — 标识符",
      "config": "string — config.json 路径",
      "audit_type": "string",
      "institution_category": "string",
      "audit_years": "number[]"
    }
  ],
  "profiles": { ... },
  "kanban": { ... }
}
```

`project_name` 和 `projects` 不能同时出现。

### 校验规则

| 字段 | 规则 |
|------|------|
| slug | `[a-z0-9][a-z0-9_-]*`，自动生成时取项目名前30字符 |
| config | 文件必须存在 |
| profiles.* | collector/validator/calculator/reporter 必须指定；director 可选（缺省回退 reporter） |

### 任务粒度

每个项目生成 **8 个 kanban 任务**（父子链）+ 1 汇总 Director：
1. 采集 → 2. V1 验证 → 3. 计算 → 4. V2 指标复核 → 5. 报告卡1（基础章） → 6. 报告卡2（数据章） → 7. 报告卡3（收尾章） → 8. V3 报告审查

不同项目之间无依赖，完全并行。

---

## 示例项目（原 examples）

### 示例 1：单项目（7栋楼的综合医院 → 1份报告）

**项目**: 山东省省立医院东院区
**场景**: 1个 config.json 包含7栋楼全部数据，生成1份报告

#### plan.json（单项目模式）
```json
{
  "project_name": "山东省省立医院东院区",
  "slug": "shengli-dongyuan",
  "config": "D:/data/pyProject/dc_agent/dechnicAuditor-agent/config_shengliliyuan.json",
  "audit_type": "public_institution",
  "institution_category": "医疗",
  "audit_years": [2022, 2023, 2024],
  "profiles": {
    "collector": "datacollection",
    "validator": "datava",
    "calculator": "caliber",
    "reporter": "author",
    "director": "editor"
  },
  "kanban": {
    "max_concurrent_projects": 3,
    "max_runtime_per_task_seconds": 1800
  }
}
```

#### 任务图
```
Director: [汇总] 全1个项目审查（editor 专职终审）
  └─ T001: 采集→验证(数据)→计算→验证(指标)→报告卡1→报告卡2→报告卡3→验证(报告)
```
总任务数: 1×8+1 = 9

> 报告环节拆 3 张串行卡：卡1 基础章（封面+第1~4章）→ 卡2 数据章（第5~7章）→ 卡3 收尾章（第8章+附录+PDF）。三卡 assignee 固定为 reporter（author），Director 仅做汇总审查，不参与写作。

---

### 示例 2：批量模式（3个项目）

3个公共机构，每个一份报告，同时跑2个。

```json
{
  "projects": [
    {"name": "省立医院东院区", "slug": "shengli", "config": "configs/shengli.json"},
    {"name": "市人民医院", "slug": "renmin", "config": "configs/renmin.json"},
    {"name": "中医院", "slug": "zhongyi", "config": "configs/zhongyi.json"}
  ],
  "profiles": {
    "collector": "datacollection",
    "validator": "datava",
    "calculator": "caliber",
    "reporter": "author",
    "director": "editor"
  },
  "kanban": {
    "max_concurrent_projects": 2
  }
}
```

#### 任务图
```
Director: [汇总] 全3个项目审查
  ├─ 省立: T001_C→T001_V1→T001_A→T001_V2→T001_R1→T001_R2→T001_R3→T001_V3 ─┐
  ├─ 人民: T002_C→T002_V1→T002_A→T002_V2→T002_R1→T002_R2→T002_R3→T002_V3 ─┤
  └─ 中医: T003_C→T003_V1→T003_A→T003_V2→T003_R1→T003_R2→T003_R3→T003_V3 ─┘
```
总任务数: 3×8+1 = 25

---

### 示例 3：百级批量

某地市100个公共机构同时编制。

#### plan.json（批量模式）
```json
{
  "projects": [...100个...],
  "profiles": {...},
  "kanban": {
    "max_concurrent_projects": 10,
    "max_runtime_per_task_seconds": 3600,
    "failure_limit": 2
  }
}
```

#### 性能估算（8 步三卡制，md 整章导入工艺）

- 单项目 8 步: 采集 5min + V1 3min + 计算 3min + V2 3min + 报告卡1~卡3 各 15min + V3 5min + Director 2min ≈ 65min
- 并行10个: 100÷10×65min ≈ 650min (10.8h)
- 并行20个: 100÷20×65min ≈ 325min (5.4h)

> 报告环节耗时与章节量正相关，多栋楼/多系统项目单卡会超出 15min。上线后以实际运行数据校准。

#### 执行
```bash
python scripts/bootstrap_pipeline.py plan.json --out setup.sh
bash setup.sh
hermes kanban list               # 查看进度
python scripts/verify_bootstrap_dryrun.py  # 任务图结构回归验证（也可先 dry-run 再生成）
```
