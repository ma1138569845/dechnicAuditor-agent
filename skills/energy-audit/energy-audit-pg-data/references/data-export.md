# PG 全量数据导出（dc_energy_audit2 → 中文 md）

将某客户/项目的全部能源审计数据从同方德诚 PG 库导出为中文 Markdown 的方法。
2026-08 省立医院东院区全量导出实战验证。

## 连接信息

- 主机: 10.10.1.165:5432，库: dc_energy_audit2，用户: postgres，密码: `1qaz@WSX`
  （密码可从 `tools/energy_audit/pg_query.py` / `indicators.py` 源码中找到）
- psycopg2 直连；**必须 `conn.autocommit = True`** —— 否则一条查询报错
  （如字段不存在）会 abort 整个事务，后续所有查询返回
  `当前事务被终止, 事务块结束之前的查询被忽略`
- 注意：`energy_audit_get_*` MCP 工具 handler 可能报
  `TypeError: _handle_get_equipment() got an unexpected keyword argument 'task_id'`
  —— 这是工具注册 bug，遇到时直接 psycopg2 直连即可

## 表结构速查（ts_ 前缀为业务表）

| 域 | 表 | 关联键 |
|---|---|---|
| 客户 | ts_customer_info, ts_customer_users | id / customer_id |
| 审计项目 | ts_institution_project（含 status/年度/人员） | customer_id |
| 建筑 | ts_institution_build, ts_institution_build_exception | customer_id |
| 能耗年度 | ts_institution_energy（value1..12 月度） | customer_id |
| 能耗主数据 | ts_institution_energy_main（折标系数/is_alone/总量） | customer_id |
| 能耗明细 | ts_institution_energy_data（period_code 逐月） | main_id |
| 独立能耗 | ts_institution_energy_alone | main_id |
| 能耗异常 | ts_institution_energy_exception | main_id |
| 计量表具 | ts_institution_energy_meter（电/水/气/热 表数量） | customer_id |
| 节能管理 | ts_institution_energy_saving | customer_id |
| 发票 | ts_institution_energy_invoice + invoice_image | customer_id / record_id |
| 设备总表 | ts_institution_device（可能为空！） | customer_id |
| 设备分类 | ts_institution_device_{air,hotwater,hygiene,light,office,other,power,special,steam,substation,td,terminal} | customer_id |
| 附属设备/维护/建筑关联 | device_attached / device_maintenance / device_build_ref | device_id |
| 场景 | ts_institution_scene + scene_mode | customer_id / scene_id |
| 环境 | ts_institution_environment（温湿度/照度/CO₂）, indoor_environment | customer_id |
| 用水 | water_greening / water_other / water_road | customer_id |
| 太阳能 | ts_institution_solar（常空） | customer_id |
| 能源品种/流向 | ts_customer_energy（重复行多，需去重）, ts_energy_flow | customer_id |
| 用能人数 | ts_annual_energy_user（常空） | project_id |
| 审计报告 | ~~ts_energy_audit_report（不存在，旧设计已删）~~；报告内容在 `ts_institution_project.report_text`，参考报告走 RAG | project_id/customer_id |
| 附件 | ts_attachment（attach_id/attach_url/attach_initial_name） | group_id=attach_id |

## 关键流程

1. **定位客户**：`ts_institution_project` / `ts_customer_info` 按名称模糊
   `WHERE audited_name LIKE '%省立%'` 或 `customer_name LIKE '%省立%'`；
   注意区分 `audit_dept_name='省立医院'`（是审计机构名，会误命中）与
   `audited_name='山东省立医院东院区'`（被审计单位）
2. **逐表拉取**：先 `SELECT * FROM t WHERE customer_id=%s` 主表，
   再按返回的 main_id / device_id / scene_id 列表 `IN (...)` 查子表
   —— 用 id 列表二次查询，不要跨表 JOIN（表多且字段名不统一）
3. **错误容忍**：每个表单独 try/except，单表失败返回
   `[{"error": ...}]` 继续其他表，最后统计错误表数
4. **组装中文 md**：按 客户→项目→建筑→能耗(年度/主/明细/异常/计量)→设备(12类)→
   场景/环境→用水→能源品种/流向→附件→导出说明 十二章组织
5. **附件**：`ts_attachment` 中 `attach_initial_name LIKE '%<单位名>%'` 过滤；
   附件存储于 WebUI 文件服务（域名 `eademo.bmscloud.top` + attach_url），
   需内网认证，**外部直连只返回 604B HTML 错误页**——不要尝试批量下载，
   在 md 中列出 名称/类型/大小/路径 清单供用户在 WebUI 内取用
   （infra_file / infra_file_content 表通常没有业务附件记录，别浪费时间查）
6. **导出位置**：`C:\Users\<user>\projects\energy-audit\<单位>_数据导出\`
   放 `raw_data.json`（原始全量）+ `<单位>_能源审计全量数据.md`（中文格式化版）

## 能源代码映射（2026-08 省立医院实战校准，勿照抄旧表！）

| 代码 | 真实能源 | 判别方法 |
|---|---|---|
| 01 | **自来水**（表头常误标"天然气"） | 数值 ≈ 用水量（如 163107.7/150110/154167 m³），费用 ≈ 水费（68.51/63.05/64.75 万元） |
| 25 | **天然气**（真实） | 数值 57207/68483/79374 m³，费用 18.50/20.24/25.96 万元 |
| 45 | 电（kWh 或 万元） | 折标系数 0.1229/0.3100 |
| 50 | 热能/热力（GJ） | 市政集中供热 13931.6 GJ/年 |
| 02/03 | 汽油/柴油 | 汽油 t + 元；柴油 2024 仅 9 月有值=测试数据 |

**判别铁律**：不要信 `energy_name` 列（01 就标着"天然气"但实为水）——
用 `total_value` 与 `ts_customer_info`/已知年度账目交叉核对数值量级。
整理报告时若发现代码含义与表头不符，在"数据质量说明"章节逐条记录。

## 表序 → 报告逻辑重组（用户要求"更合理的数据报告"时）

用户拿到按数据表顺序平铺的 md 会要求重排。重排为 14 章报告逻辑：
单位概况(客户+项目) → 建筑概况(对比表+每栋详细) → **能源消费总览**(年度消耗/费用/折标结构，核心) →
逐月明细(按能源品种分节，异常月份加粗) → 能耗异常 → 计量配置 → 用能设备(按系统 7.1-7.17) →
场景与运行 → 用水 → 环境监测 → 节能管理 → 能源品种流向 → 附件 → **数据质量说明**(新增！)

- 总览章节要主动算：三年变化率（如电 -5.0%、气 +38.7%）、2024 折标占比（电 83%+气 14.8%+油 2.2%）、费用合计
- 测试数据（2025 年度各月数值全同）**不列入总览**，仅标注
- 设备章节除摘要表外，补"设备现场详细参数"小节：每台设备全部非空字段
  （运行规则/调节水温/电机型号/阀门状态等 20+ 字段，摘要表会漏）——用
  4 列键值对逐台列出，字段名映射中文
- 设备更换记录（ts_institution_equipment_replacement）、设备-建筑关联
  （device_build_ref）、发票图片（invoice_image，多数无 file_id）容易漏，逐项核对
- 私有文件（ts_file_private）多为**其他项目测试数据**（日照三中、海洋学校等），
  核实与本客户无关后不入报告，但在数据质量说明中注明

## 已知坑

- **`ts_energy_audit_project` / `ts_energy_audit_report` 表不存在**（旧设计已删，SQL 报"关系不存在"）。审计组成员/配合人员查 `ts_project_audit_user` / `ts_project_audited_user`（按 project_id）；已有报告内容在 `ts_institution_project.report_text`；参考报告全文走 RAG。旧版 coder/author skill 曾引用这两张表，2026-08 已修正。
- `ts_customer_users` 无 customer_id 字段（按 id 查）
- `ts_institution_equipment_replacement` 无 customer_id（按 record_id 关联设备）
- `ts_annual_energy_user` / `ts_institution_solar` / `ts_institution_energy_invoice`
  常为空表——导出说明里注明"表中无记录"，不是漏查
- `ts_institution_device` 总表可能为 0 条，设备数据全在分类表中
- 客户能源品种表大量重复行，导出时按 (energy_name, unit) 去重
- 模板待补充段落在 docx 中可能不止一处（封面 docx 是整本报告骨架），
  定位要精确匹配段落文本
