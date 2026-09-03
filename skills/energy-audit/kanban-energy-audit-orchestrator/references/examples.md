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
    "reporter": "author"
  },
  "kanban": {
    "max_concurrent_projects": 3,
    "max_runtime_per_task_seconds": 1800
  }
}
```

### 任务图
```
Director: [汇总] 全1个项目审查
  └─ T001: 采集→验证→计算→报告
```
总任务数: 1×4+1 = 5

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
    "reporter": "author"
  },
  "kanban": {
    "max_concurrent_projects": 2
  }
}
```

### 任务图
```
Director: [汇总] 全3个项目审查
  ├─ 省立: T001_C→T001_V→T001_A→T001_R ─┐
  ├─ 人民: T002_C→T002_V→T002_A→T002_R ─┤
  └─ 中医: T003_C→T003_V→T003_A→T003_R ─┘
```
总任务数: 3×4+1 = 13

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

### 性能估算
- 单项目 4 步: 采集5min + 验证3min + 计算3min + 报告8min ≈ 20min
- 并行10个: 100÷10×20min ≈ 200min (3.3h)
- 并行20个: 100÷20×20min ≈ 100min (1.7h)

### 执行
```bash
python scripts/bootstrap_pipeline.py plan.json --out setup.sh
bash setup.sh
hermes kanban list               # 查看进度
python scripts/monitor.py --once  # 快照
```
