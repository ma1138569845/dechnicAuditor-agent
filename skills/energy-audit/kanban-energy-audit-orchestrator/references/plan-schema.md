# plan.json 结构定义

`bootstrap_pipeline.py` 的输入。支持两种模式。

## 单项目模式

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

## 批量模式

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

## 校验规则

| 字段 | 规则 |
|------|------|
| slug | `[a-z0-9][a-z0-9_-]*`，自动生成时取项目名前30字符 |
| config | 文件必须存在 |
| profiles.* | collector/validator/calculator/reporter 必须指定；director 可选（缺省回退 reporter） |

## 任务粒度

每个项目生成 **8 个 kanban 任务**（父子链）+ 1 汇总 Director：
1. 采集 → 2. V1 验证 → 3. 计算 → 4. V2 指标复核 → 5. 报告卡1（基础章） → 6. 报告卡2（数据章） → 7. 报告卡3（收尾章） → 8. V3 报告审查

不同项目之间无依赖，完全并行。
