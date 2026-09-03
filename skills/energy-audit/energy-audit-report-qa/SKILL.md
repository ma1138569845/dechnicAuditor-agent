---
name: energy-audit-report-qa
description: Use when 对照核查能源审计报告(生成版vs正式版)。docx提取+三级数据校验+高频错误清单。
---

# Energy Audit Report QA（报告对照与数据核查）

## Overview

用户常把流水线生成版（Kanban/Agent）报告与正式交付报告对照，或要求核查报告数据真实性。本 skill 提供完整核查方法：结构对照 → 数据逐项核验 → 交叉验证判定谁对 → 分级输出差距清单。实证案例：烟台开发区法院（2026-09），发现 9 类高频错误。

DB 查询细节见 `energy-audit-pg-data` skill（版本机制、表结构陷阱已收录其中）。

## When to Use

- 用户要求对照两份能源审计报告找差距（生成版 vs 正式版）
- 用户质疑报告数据"对不上""为什么少了/错了"
- 交付前核查报告数据真实性（账单、指标、定额值）

## Workflow

### Step 1: docx 提取与结构对照

- python-docx 按文档顺序提取段落+表格：遍历 `document.element.body` 子元素（w:p→Paragraph，w:tbl→Table），表格单元格换行用 `⏎` 连接，保留样式名（Heading/表头/toc）→ 导出 txt 逐行对照。**勿用正则解析 document.xml 里的 <w:tbl>**（嵌套表格会撕裂匹配），python-docx 是唯一可靠路径
- 统计对比：段落数 / 表格数 / 图片数（zipfile 查 `word/media/`）/ 分节数（sections）/ 总字数 / 【待补充】计数
- 标题树逐章对照：章节缺失（如附录 1-5、6.5 室内环境检测）、节数划分差异、标题命名差异

### Step 2: 数据对照清单（按序核验）

1. 三年逐月账单表（附录2）→ 年度总量加总验证（权威基准）
2. 费用表：单位（元 vs 万元）、精确度
3. 指标计算表：非供暖能耗/常规电耗（**是否剔除供暖电耗**）、人均综合能耗（等价/当量口径是否混用）、人均取水量
4. 定额三档值（约束/基准/引导）来源与数值
5. 5.4 基准：依据标准（JS/T 301-2024 费用托管规程 vs 省节能量核定办法）、取法（最近一年 vs 三年均值）
6. 第 7 章问题-措施与第 2 章建筑参数/用能系统的一致性（措施不得与事实矛盾）

### Step 3: 交叉验证（判定谁对）

- 年总量 = Σ逐月（正式版附录逐月账单为权威）
- 费用 ÷ 单价 = 用量（例：热费 459,251.25÷89.61=5,125 GJ；320,355.75÷89.61=3,575；290,874.06÷89.61=3,246）
- DB 侧：`ts_institution_energy_main` 版本交叉核对（草稿 ver=None vs 正式版 PLxxxxxxxxxx）——**正式版本可能在升级时被改错/丢数据，草稿反而正确**；定额值不在 DB（ts_energy_standard 仅折标系数）。**版本机制通用于全部 ts_institution_* 业务表**（build/meter/scene/energy_saving 同构）：建筑表 3 条"相同"记录=草稿/0401/0402 三版本而非重复录入，禁止按 (build_name, build_area) 等业务属性去重（2026-09 用户明确纠正），取数一律版本归一（正式版本优先、version_code 大者优先、草稿兜底）
- 指标按公式独立重算，比对报告值（误差应 <0.01）

### Step 4: 输出差距清单

- 分级：P0 数据硬伤（影响结论）→ P1 内容缺失 → P2 事实矛盾 → P3 口径差异 → P4 格式编排
- 每项注明：位置（章号）、生成版 vs 正式版数值、根因（DB/模板/输入）、连锁影响
- 结论必须可验证（给出验证算式），不确定的标"待核实"
- **修改建议先给计划（分 Phase），经确认再执行**；DB 修改前导出原值快照、事务化执行

### Step 5: 修复后复验（六类验收项）

修完数据/链路后必须跑端到端复验，六类验收项缺一不可（法院 D3 实证：修复过程又暴露 10 个链路 bug，详见 `references/collector-chain-fixes.md`）：

1. **能耗 30 项**：三年 ×（电/水/气/热/汽油 实物量 + 费用），逐项对照正式版权威值
2. **逐月明细 36 行**：12 月值、年合计与附录2 一致
3. **定额 9 项 + 评价结论**：三档值（约束/基准/引导）与评价方向（达标/整改）与正式版一致
4. **建筑参数**：逐字段对照（窗型/保温/末端形式等）
5. **图片落地**：本地文件存在且 size 与 DB `attach_size` 一致（验证 URL 用本项目真实文件路径，勿用其他日期目录的旧文件——会 404 误判）
6. **人员/机构**：审计组+配合人员名单、用能人数、审计机构名（过滤"测试"值）

## 高频错误模式（烟台法院实证）

| 错误 | 表现 | 根因 |
|---|---|---|
| 月度数据错位 | 2025年12月写成10月值 51,105（应为 79,305），年总量差 28,200，伪造"12月同比-34.7%"假异常 | DB 正式版本录入错误 |
| 年度数据颠倒 | 热力 2024/2025 互换（3,575/3,246），趋势分析方向反 | DB 正式版本录入错误 |
| 实物量缺失 | 2023/2024 用水量正式版本缺失（草稿有 8,985/9,164 m³） | 版本升级丢数据 |
| 定额值错误 | 生成版 20.80/12.60/6.90 vs 正式 20.0/11.9/6.5，标注"来源：DB"不实 | 标准原文已核验（2026-09-02）：20.8/12.6/6.9、75.8/45.9/26.2、1293.4/828.9/478.0 **是 DB37/T 2672-2019 表内"市级以下 B 区"的值**，正式版 20.0/11.9/6.5 等是"市级以下 A 区"——错误本质是**拿错气候区**（烟台属半岛 A 区），不是无源捏造。修复=按机构等级+气候区选行 |
| 未剔除供暖电耗 | 非供暖能耗/常规电耗偏高约 15% | 生成逻辑漏扣供暖循环泵电耗 |
| 水计入综合能耗 | 人均综合能耗偏高 | 附录B 无水折标系数，综合能耗=电+热+气+油，不含水 |
| 折标系数污染/单位混用 | 供暖能耗年偏差 65~103 kgce；热系数 34.12 被当 0.03412 或反之 | 系数 Layer1 全局查询跨项目（实证拿到别家 0.0341/0.7143）；DB 气系数 1.33 错（标准 1.2143）；heat 须 kgce/GJ→tce/GJ 归一 |
| 功率单位放大 | 设备清单 W→kW（150.00 kW×105 台电脑等） | 模板字段单位错误 |
| 模板误用 | 厨房炊事用气被诊断成"燃气锅炉效率下降" | 措施库套用与项目事实矛盾（项目无锅炉） |
| 建筑参数矛盾 | 外墙保温"有" vs"实心黏土砖（其它）"；供暖末端风机盘管 vs 散热器 | 数据源不一致 |
| 委托方/时间错误 | 委托方写成被审计单位；审计时间/封面日期不符 | 输入配置错误 |
| 交付占位 | 封面人员表/表2-1 等约 20 处【待补充】 | 输入数据未补全即交付；基本信息三张表完整根因链见下节 |

## 现场照片缺失根因链（烟台法院实证 2026-09：生成版 11 图 vs 正式版 40 图）

现象：生成版报告只有图表、无任何现场照片（建筑外观/计量器具/设备照片全缺）。图片**在 DB 里存在**，根因是采集链路四层断点，不是数据缺失：

1. **工具链断链（根因）**：kanban worker profile（datacollection）config.yaml 的 `toolsets` 只有 `hermes-cli`，未加载 energy_audit toolset；`terminal.cwd` 指向不存在/错误的仓库目录 → worker 看不到也 import 不到 `tools/energy_audit/*`（pg_collector/photo_manager/file_resolver 全部失效）→ agent 现场手写 psycopg2 直连脚本（collect_final.py 等）自建劣化链路，`images: []` 硬编码空数组
2. **采集不查图**：劣化脚本只查业务数据表，未查图片字段——而 DB 里都有：`ts_institution_build.build_img`（建筑外观）、`ts_institution_energy_meter.device_img`（电/水表照片）、meter.ledger_files/year_files/month_files（计量台账）、设备分类表 ledger_files
3. **file id 解析缺失**：build_img/device_img 存的是 `ts_attachment.group_id`（**列名是 group_id 不是 id**，按 id 查直接 UndefinedColumn）；attach_url 为相对路径（/20260207/xxx.png），需 `get_file_base_url()` 拼 base_url
4. **base_url 未配置**：config.yaml 的 energy_audit 段只有 database 无 file 段 → `file_resolver` 静默跳过下载（不报错）

修复模式：①profile config 修 toolsets+cwd（datacollection/datava/caliber/author 四个 worker 都要查）；②skill/SOUL.md 加硬规则"采集必须走 repo 工具链，import 失败停下来报告断链，禁止手写直连脚本";③pg_collector 采集 build_img/device_img → file_resolver 解析下载 → ImageItem(category=建筑外观/计量器具) 写入 proj.images；④photo_manager.check_photos 按 PHOTO_CATEGORIES 校验各章照片。落地细节见 energy-audit-pg-data skill 与 repo `tools/energy_audit/photo_manager.py`。

## 基本信息三张表【待补充】根因链（烟台法院实证 2026-09）

现象：正式版三张表（能源审计机构信息表/审计组成员/配合人员）数据完整，Agent 生成版只有机构名称有值，地址/负责人/联系方式/人员全【待补充】。根因是**四层链路全部断点**，不是单点漏填：

1. **数据层**：真实值（审计机构地址/负责人/审计组名单）只存在于正式报告，DB 从未录入。实测 PG：`ts_project_audit_user`/`ts_project_audited_user` 全库仅其他项目 1 条测试数据；`ts_customer_info` 的 contact/mobile 为空；`ts_institution_project` 只有测试值（audit_dept_name=同方德诚测试公司-1、audit_dept_person=吕晓晗）
2. **模型层**：datacollection 采集模型（ProjectBase）无审计机构地址/负责人/电话、无审计组/配合人员字段 → data.json 永远不会携带这些数据
3. **生成层**（report_generator.py `load_from_project` ≈L3216）：team_members/cooperation **硬编码【待补充】占位**，从不查 `ts_project_audit_user`；institution 取被审计单位字段（b.unit_name/b.address/b.contact_person/b.contact_phone），与"能源审计机构信息表"语义错位。pg_collector 虽查了 audit_users，但字段映射对不上（DB position/degree/qualifications → 生成器要 role/education/certification），且未接入 report_data
4. **校验层**：data_check 只查 team_members 非空（占位恒通过）；V1 `mode_data_check.py` 把 team_members 映射到不存在的 `base.project_manager`（恒缺失但"审计组人员"仅 P2 不阻塞）、institution 只映射 name；V3 `mode_report_review.py` 与 report_qa.py 残留占位符扫描**只扫段落（kind=="p"）不扫表格单元格** → 表内【待补充】必然漏检；必备三表检查也只查标题段落

排查方法：docx 表格反查 → `energy_audit_get_project` 看工具层返回 → 直连 PG 查四张表（ts_project_audit_user/ts_project_audited_user/ts_customer_info/ts_institution_project.audit_dept_name|person|tel）→ 对照 report_generator 装配代码。修复治本：数据补录 + 模型加字段 + 装配查库 + 校验扫单元格。

**数据源与字段映射（2026-09 用户确认）**：
- 审计组名单 = `ts_project_audit_user`：position（职务，存"审计负责人/审计联络人/成员"）→报告"组内职务"列 role；degree→education、qualifications→certification、major→major
- 配合人员名单 = `ts_project_audited_user`：group_position（组内职务，存"组长/联系人"）→role；department→dept、sex→gender、position（职务，存"主任/科长"）→position
- 机构信息表 = `ts_register_dept`（注册单位表，dept_name=单位名称/address=详细地址；勿用 ts_register_info 被审计单位注册申请表）：名称/地址表取不到→**向用户提问**（勿静默【待补充】）；名称含"测试"字样时过滤（取 register_dept 同品牌"德诚"不含"测试"的最新记录）。负责人/联系方式**2026-09-02 用户确认"DB 数据为准"**：直接采用 `ts_institution_project.audit_dept_person/audit_dept_tel`（如吕晓晗/15628998185），不再强制向用户提问；register_info.contact/mobile 仅作提问预填参考，不覆盖 DB 项目值。audit_dept_name 常为测试值（"同方德诚测试公司-1"）→ 封面机构名须过滤"测试"字样（_resolve_auditor 回退正式名），但 audit_dept_person/tel 可能是真实人员，两者处理不同，勿一律当测试数据丢弃
- `system_users` 有审计员档案（degree/qualifications/major/is_audit）仅作学历/资质参考，**不是**名单数据源

**列名陷阱**：ts_customer_info 列是 customer_name/contact/mobile（**无 name/contact_person/contact_phone**，按旧列名查直接 UndefinedColumn）；审计机构信息在 ts_institution_project.audit_dept_name/audit_dept_person/audit_dept_tel。

修复落地细节（新字段名/函数位置/校验逻辑/验证命令/测试断言更新）见 `references/audit-info-tables-fix.md`。

## Conventions

- **剔除供暖电耗**：单位建筑面积非供暖能耗与常规用能系统电耗计算时，须从年总电量中扣除供暖耗电（供暖循环泵/供暖风机）。正式交付口径示例：烟台法院 2023-2025 供暖耗电 159,682.5/120,075/78,210 kWh，扣除后非供暖能耗 12.34/11.93/12.27 kgce/(m²·a)；不扣则偏高约 15%
- **定额值多套口径**：标准原文已核验（2026-09-02，PDF 附文本层可提取，部分页需 OCR）——DB37/T 2672-2019 表1/3/4 按"机构等级（省级/市级/市级以下）×气候区（A 半岛沿海/B 内陆）"分 5 行，表2 供暖能耗按供暖类型不分等级（市政集中供暖按热计量 12.7/11.1/8.3）。曾见"内置 25.5/16.6/9.6"=省级 B 区、"正式报告 20.0/11.9/6.5"=市级以下 A 区——都是标准内值，取值须确认机构等级+气候分区选对行，禁止标注不实的"来源：DB"。完整矩阵见 energy-audit-report skill 的 energy-audit-core/references/energy-audit-core/references/standards-values.md（权威单点）（权威单点，勿在本文件复制数值）
- **综合能耗口径统一**：5.1 与 5.3 不得混用当量/等价值（电力等价值 0.31 kgce/kWh 为省惯例）；5.1 不给数值时不要自行给出混算值。**水不折算标准煤**（附录B 无水折标系数）；综合能耗 = 电0.31 + 热0.03412kgce/MJ + 气1.2143 + 油1.4714（法院验证锚点：1559.48/1334.35/1293.60 kgce/(p·a)，351 人）。系数链坑（heat 单位归一/跨项目污染/DB 气系数错值）见 energy-audit-pg-data 的 energy-audit-core/references/energy-audit-core/references/coefficient-caliber.md（权威单点）（权威单点）
- 基准取法：正式口径按《公共机构能源费用托管实施规程》（JS/T 301-2024）4.3 条（逐年递减取最近一年；±10% 内取三年均值）
