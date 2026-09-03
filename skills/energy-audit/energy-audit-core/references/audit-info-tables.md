# 审计基本信息三张表

位置：封面后、目录前。

## 能源审计机构信息表

4行 × 2列，键值对格式。第一列加粗居中。

| 项目 | 数据来源（权威链路，2026-09-03 用户确认） |
|------|----------|
| 机构名称 | ① `ts_project_dept.dept_name`（按 project_id 查，审计机构信息id表）；② 兜底：按 project 的 `audit_dept_name` 查 `ts_register_dept.dept_name`（**勿用 ts_register_info**；名称含"测试"字样时过滤，取同品牌"德诚"不含"测试"的最新记录） |
| 地址 | ① `ts_project_dept.address`；② 兜底：`ts_register_dept.address`（同上） |
| 负责人 | **仅** `ts_project_dept.contact`；无值则空，**不查其他表** |
| 联系方式 | **仅** `ts_project_dept.mobile`；无值则空，**不查其他表** |

## 能源审计组人员名单

N行 × 5列。表头行自动生成。数据源 `ts_project_audit_user`。

| 列 | 数据来源 |
|----|----------|
| 组内职务 | `position` |
| 姓名 | `name` |
| 学历 | `degree` |
| 所获资质 | `qualifications` |
| 专业 | `major` |

## 能源审计配合人员名单

N行 × 5列。表头行自动生成。数据源 `ts_project_audited_user`。

| 列 | 数据来源 |
|----|----------|
| 组内职务 | `group_position` |
| 部门 | `department` |
| 姓名 | `name` |
| 性别 | `sex` |
| 职务 | `position` |

## 生成方式

```python
gen.set_report_data({
    'audit_info_tables': {
        'institution': {'name': '...', 'address': '...', 'contact': '...', 'phone': '...'},
        'team_members': [{'role': '组长', 'name': '...', 'education': '...', 'certification': '...', 'major': '...'}, ...],
        'cooperation': [{'role': '...', 'dept': '...', 'name': '...', 'gender': '...', 'position': '...'}, ...],
    },
    ...
})
```

缺失字段标 `【待补充】`，不捏造数据。审计组/配合人员缺失时记 P1 问题，V3 审查与 report_qa 扫表格占位。
