# 应用示例

## 示例 1：单项目（7栋楼的综合医院 → 1份报告）

**项目**: 山东省省立医院东院区
**场景**: 1个 config.json 包含7栋楼全部数据，生成1份报告

### plan.json（单项目模式）
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

### 任务图
```
Director: [汇总] 全1个项目审查（editor 专职终审）
  └─ T001: 采集→验证(数据)→计算→验证(指标)→报告卡1→报告卡2→报告卡3→验证(报告)
```
总任务数: 1×8+1 = 9

> 报告环节拆 3 张串行卡：卡1 基础章（封面+第1~4章）→ 卡2 数据章（第5~7章）→ 卡3 收尾章（第8章+附录+PDF）。三卡 assignee 固定为 reporter（author），Director 仅做汇总审查，不参与写作。

---

## 示例 2：批量模式（3个项目）

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

### 任务图
```
Director: [汇总] 全3个项目审查
  ├─ 省立: T001_C→T001_V1→T001_A→T001_V2→T001_R1→T001_R2→T001_R3→T001_V3 ─┐
  ├─ 人民: T002_C→T002_V1→T002_A→T002_V2→T002_R1→T002_R2→T002_R3→T002_V3 ─┤
  └─ 中医: T003_C→T003_V1→T003_A→T003_V2→T003_R1→T003_R2→T003_R3→T003_V3 ─┘
```
总任务数: 3×8+1 = 25

---

## 示例 3：百级批量

某地市100个公共机构同时编制。

### plan.json（批量模式）
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

### 性能估算（8 步三卡制，md 整章导入工艺）

- 单项目 8 步: 采集 5min + V1 3min + 计算 3min + V2 3min + 报告卡1~卡3 各 15min + V3 5min + Director 2min ≈ 65min
- 并行10个: 100÷10×65min ≈ 650min (10.8h)
- 并行20个: 100÷20×65min ≈ 325min (5.4h)

> 报告环节耗时与章节量正相关，多栋楼/多系统项目单卡会超出 15min。上线后以实际运行数据校准。

### 执行
```bash
python scripts/bootstrap_pipeline.py plan.json --out setup.sh
bash setup.sh
hermes kanban list               # 查看进度
python scripts/verify_bootstrap_dryrun.py  # 任务图结构回归验证（也可先 dry-run 再生成）
```
