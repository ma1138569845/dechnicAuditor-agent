# 基本信息三张表修复落地记录（2026-09，烟台法院实证）

修复完成态：Agent 生成 docx 的三张表与正式版逐字段一致（机构信息 4 字段 / 审计组 4 人 / 配合 1 人）。

## 数据层（DB）

- 审计组/配合人员直接插表（不依赖 system_users）：
  - `ts_project_audit_user`：name/position(组内职务)/degree/qualifications/major/project_id
  - `ts_project_audited_user`：name/position(职务)/department/sex/group_position(组内职务)/project_id
  - project_id 取 `find_project_by_name` 命中的记录（get_institution_project 过滤 deleted=0、ORDER BY create_time DESC → rows[0]）。烟台法院有效记录 2087807622972936194；同单位 3 条记录里 deleted=1 的是旧测试记录，勿挂
  - id 生成：查 `COALESCE(MAX(id),0)` 后 +1..N 递增即可（应用层雪花 ID 不会冲突）
- 审计机构真实信息不补录（用户决策）：每次生成走提问流程

## 模型层（tools/energy_audit/project_data.py）

- `ProjectBase` 新增：audit_org_name / audit_org_address / audit_org_contact / audit_org_phone / audit_org_contact_hint / audit_org_phone_hint
- 新 dataclass：`TeamMember`（role/name/education/certification/major）、`CoopMember`（role/dept/name/gender/position）
- `AuditProject` 新增：audit_team: List[TeamMember]、cooperation: List[CoopMember]

## 采集层（pg_collector.py / pg_query.py / energy_audit_tool.py）

- `PgDataQuery.get_register_info(credit_code=None, dept_name=None)`：ts_register_dept 按 credit_code 精确 / dept_name ILIKE，ORDER BY update_time DESC
- `_collect_from_pg_impl`：项目装配后按 project_id 查 get_project_dept（ts_project_dept）→ audit_org_name/address/contact/phone；名称/地址缺省时兜底 get_register_info(dept_name=audit_dept_name)；负责人/联系方式仅 ts_project_dept 一源（2026-09-03）_hint/audit_org_phone_hint；无注册记录时 audit_org_name 兜底取 audit_dept_name
- 人员映射（对齐 report_generator 取值键）：
  - audit_user: position→role、name→name、degree→education、qualifications→certification、major→major
  - audited_user: group_position→role、department→dept、name→name、sex→gender、position→position
- `build_and_save_project`：base 装配 audit_org_*（contact/phone 只从 Excel/用户侧 resolve，PG 无最终值）；audit_team/cooperation 用 `_dataclass_from_dict` 构造
- energy_audit_tool 展示键：team=name/role/certification，audited=name/role/dept/position（旧键 qualification 已废）

## 生成层（report_generator.py load_from_project）

```python
'institution': {
    'name': b.audit_org_name or b.auditor,   # 审计机构，非被审计单位！
    'address': b.audit_org_address,
    'contact': b.audit_org_contact,
    'phone': b.audit_org_phone,
},
'team_members': [{'role': m.role, 'name': m.name, 'education': m.education,
                  'certification': m.certification, 'major': m.major} for m in project.audit_team],
'cooperation': [{'role': c.role, 'dept': c.dept, 'name': c.name,
                 'gender': c.gender, 'position': c.position} for c in project.cooperation],
```

删除硬编码占位 `[{'role':'待补充',...}]` 与 `{'role':'配合人员',...}`。

## 校验层

- `tools/energy_audit/data_check.py` check_completeness：
  - institution 逐字段查空/占位（address/contact/phone → "审计机构信息表：xxx（缺失或占位）"）
  - team/coop 改为**逐人检查 name 非空非【待补充】**（不再只查列表非空——占位列表恒通过）
- datava V1 `mode_data_check.py`：
  - project_to_report_data 的 team_members 取 `raw['audit_team']`（原错映射 `base.project_manager`——该字段不存在，恒缺失）
  - institution 补 address/contact/phone 映射
  - 严重级别："审计组人员" P2→**P1**；新增 "审计机构名称" P0、"审计机构" P1、"配合人员" P1（关键词优先匹配，长词在前）
- datava V3 `mode_report_review.py` check_tables_and_placeholders：占位符扫描 full_text 合并表格单元格文本（`b.obj.rows[].cells[].text`，Block 的表格对象在 `.obj` 不在 `.table`）→ 表内【待补充】报 P0
- `tools/energy_audit/report_qa.py` 同样把 doc.tables 单元格并入 full_text

## 验证方法

- 采集冒烟：`collect_from_pg("烟台经济技术开发区人民法院")` → found.team_members 4 人 / audited_users 1 人 / project.audit_org_name 有值、address None（提问触发点）
- 装配冒烟：`load_project` → `ReportGenerator(...).load_from_project(proj)` → audit_info_tables 三张表有值；模拟用户补全 audit_org_* 后 generate_word → docx 表#0-2 与正式版逐字段一致
- V1 校验：project_to_report_data + check_completeness → 有人员时只报审计机构 3 项 P1（人员不再误报）；构造占位 team_members → 报"审计组人员名单"
- V3 校验：对含表内【待补充】的 docx → 报 V3.STRUCT.PLACEHOLDER P0（计数含单元格）
- 回归：repo `tests/tools/energy_audit/`（123 passed）；datava `scripts/tests/test_datava.py`（73 passed，**断言已更新**：审计组人员缺失 SEV_P2→SEV_P1，新增审计机构/配合人员 P1 断言）

## 同步注意

- datava skill 双副本：`~/AppData/Local/hermes/profiles/datava/skills/data_validation/` 与 `D:\所有的Agent\正式\datava\skills\data_validation\`（pytest 实际跑后者，两处都要同步）
- datacollection SOUL.md 数据模型说明已加 audit_org_*/audit_team/cooperation 与采集规则（ts_register_dept 提问兜底）
- energy-audit-imitate SKILL.md spec 示例已加 audit_info_tables 字段说明（repo 权威源 → 同步各 profile）
