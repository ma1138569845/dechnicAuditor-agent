# 旧表引用溯源（2026-08 省立医院会话）

用户问"为什么 agent 会查 ts_energy_audit_report / ts_energy_audit_project"，
溯源结论：这两张表是**旧版空/历史表**，但多个 skill 仍引用，会把 agent 引到
错误数据源。

## 引用来源清单

| 位置 | 引用内容 |
|---|---|
| `profiles/coder/skills/energy-audit/energy-audit/SKILL.md` L96/L128-129/L305 | 数据库速查表列出两表；审计组人员数据源指向 ts_energy_audit_project |
| `profiles/coder/skills/energy-audit/energy-audit/references/database-schema.md` L62-75 | 两表字段结构专节 |
| `profiles/author/skills/ea-authoring/references/audit-info-tables.md` L28 | "需手动提供或另行直查 PG 表 ts_energy_audit_project" |
| `dc-eau-agent/tools/energy_audit/pg_query.py` L147/L176 | get_audit_projects / get_audit_reports 实际 SQL |

## 正确数据源

真实业务数据在 `ts_institution_*` 表（ts_institution_project / energy /
build / scene / energy_meter / device_* 等），经 `energy_audit_get_*` 工具或
`PgDataQuery.get_institution_*` 方法访问。

## 修复建议（未执行）

coder profile 的 energy-audit skill 与 author profile 的 ea-authoring skill 的
表引用应更新为 ts_institution_* 系列；`dc-eau-agent` 的 pg_query.py 中
get_audit_projects/get_audit_reports 若无人使用可删或改指新表。这些是
profile/user-owned 技能，需用户确认后由前台会话修改。
