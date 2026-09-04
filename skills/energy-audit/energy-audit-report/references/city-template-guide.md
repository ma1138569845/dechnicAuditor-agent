---
name: energy-audit-report-city-template-guide  # 原 energy-audit-reports SKILL.md 内容，2026-09 并入 energy-audit-report
description: 能源审计报告/模板编写：结构、自洽示例数据、按用户格式生成Word。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [能源审计, 公共机构, 报告模板, 数据自洽, docx]
    category: productivity
    related_skills: [docx]
---

# 能源审计报告（Energy Audit Reports）Skill

编写公共机构能源审计报告及模板：按《市州公共机构能源审计报告模板参考》的 0–11 章骨架，适配具体单位类型（学校/医院/党政机关/场馆等），编造**自洽**的示例数据，并按用户格式规范生成 Word。用户对数据不一致零容忍——示例数据必须程序化校验。

## When to Use

- 用户要求编写能源审计报告模板（学校、医院、机关、监狱、场馆等公共机构）
- 需要填充自洽示例数据的审计报告正文
- 把审计报告 markdown 转 Word（必须符合用户格式规范）
- 用户教学模式：先出模板确认 → 再落地代码/正式报告

## Prerequisites

- python-docx 在本机 **anaconda** python（`D:/develop/anaconda3/python.exe`）；项目 `.venv` 的 python 无 pip、无 python-docx（`pip`→3.13 anaconda，`python`→3.11 项目venv）。运行 docx 脚本一律用 anaconda 解释器。
- 转换脚本：`scripts/md_to_docx_energy_audit.py`（本技能自带，通用化参数）
- 学校模板参考：`references/examples/school-audit-template.md`；源文件在 `~/AppData/Local/hermes/attachments/学校能源审计报告模板（示例数据）.md`（md+docx 均已生成）
- 原始市州模板：用户附件 `市州公共机构能源审计报告模板参考.pdf`（结构化内容已提炼进本 SKILL.md）

## 市州模板 0–11 章骨架（所有单位类型通用）

0.摘要 → 1.能源审计执行概要（目的/范围边界/审计期/依据[法规·政策·标准]/内容/方法过程/结论）→ 2.单位概况（基本情况/面积人数业务量表2-1/建筑物表2-2/能源总体/用能特点）→ 3.能源管理概况（组织架构图/制度清单表3-1/目标方针/成效问题）→ 4.能源计量及统计（计量网络图/器具配备符合性表4-1/检定管理/统计制度/数据质量核查表4-2/成效问题）→ 5.主要用能设备（设备清单表5-1/通用设备能效评价/淘汰落后与提升计划）→ 6.主要用能系统（暖通空调/照明/供配电/电梯热水锅炉/水资源/室内环境抽测/现场检测）→ 7.能耗指标（品种来源用途表7-1/流向/近三年消费表7-2/月度异常/结构/指标汇总表7-3/定额对标）→ 8.碳排放（边界方法/核算表8-1/结构图/趋势）→ 9.成本（近三年成本表9-1/费用结构表9-2/趋势/管理评价）→ 10.节能潜力（已实施改造表10-1/影响因素/问题/三类措施/潜力经济性表10-2/实施计划表10-3）→ 11.结论与整改意见 + 附件（10项：资质/流向图/统计表/设备清单/测算报告/照片/票据/整改清单/改造项目清单/备案表）+ 备案表（5张）+ 资料真实性承诺函

## 单位类型适配要点

先列"供能方式 + 运行日历 + 专属标准"，再写正文。学校版已跑通：
- 供能：无集中冷站（分体空调为主）、空气源热泵宿舍热水、天然气仅食堂、屋顶光伏自用
- 日历：寒暑假双谷、开学月（9月）高峰、教学日 6:30–22:30、宿舍热水晚高峰、食堂燃气与教学日历同步
- 标准：GB/T 36876 教室照明、GB/T 17225 教室温度、建科〔2008〕89号 节约型校园导则
- 对标修正：寄宿制学校运行时间长，定额对标需注明"寄宿制修正"或横向对比同类校
- 医院（已跑通 2026-08：二级=日照岚山区人民医院、三级=山东省立医院东院区）：全天候运行、消毒供应/净化空调/医疗设备特殊用能；定额对标 DB37/T 2673-2019（数值需核验，拿不到用【待核验】占位，已确认三级电耗引导值 76.4）、用水定额 DB37/T 4452-2021（二级 540/340、三级 804/440 L/(床·d)）；第4项指标用单位开放床日用水量；测试数据/复制数据判别见“真实数据核验”。详见 `references/examples/hospital-audit.md`
- **党政机关/法院版已跑通**（2026-08 烟台经开区法院，参考日照岚山区法院报告）：
  8 章结构（非市州 0–11 章）：1 执行概要 → 2 公共机构概况 → 3 能源资源管理 → 4 计量统计 →
  5 消耗指标分析（5.2 消耗数据/5.3 五项指标/5.4 能耗基准）→ 6 用能系统分析 → 7 节能潜力 → 8 结论 + 
  5.3 节指标：单位建筑面积非供暖能耗 / 常规用能系统单位建筑面积电耗 / 人均综合能耗 / 取水指标（医院=床日、机关=人均、场馆=单位面积） / 供暖能耗（有供暖项目）
  对标 DB37/T 2672-2019（山东党政机关，约束/基准/引导三级）
  供能：风冷冷水机组+多联机、市政供暖按热量表缴费、散热器采暖、厨房天然气、公务车汽油
  用能人数来自 ts_institution_scene.work_staff（351 人），不是编造
  完整工作流（结构/指标口径/数据中心要点/Word参数）见 `references/examples/court-agency-audit.md`；定额数值见 `references/quota-supplement.md`

## 示例数据自洽规则（用户零容忍不一致）

- 折标系数（学校示例用）：电 0.1229 kgce/kWh（当量值）、天然气 1.33 kgce/m³、汽油 1.4714 kgce/kg、柴油 1.4571 kgce/kg
- **山东公共机构审计报告折标系数**（DB37/T 2672-2019/2671/2673/3780 系列附录 B，已 web_search 验证原文）：
  天然气 **1.2143** kgce/m³、电力 **0.31**（供电煤耗）、热力 0.03412 kgce/MJ、汽油 1.4714、柴油 1.4571。
  ⚠ DB 系统配置的天然气系数是 1.33，与山东标准（1.2143）不同——写山东公共机构报告按 DB37/T 系列系数，
  并在附录 10 折标系数表列出 1.2143；两种系数对综合能耗影响约 0.1 tce/5000m³，勿混用
- 排放因子：外购电力 0.5703 kgCO₂/kWh（须按最新发布年度核验）、天然气 2.1622 kgCO₂/m³、汽油 2.9251、柴油 3.0959 kgCO₂/kg
- 口径决策：光伏自用计入总用电并折标，碳排放按**外购电量**扣减；公务车/应急发电机用油按公共机构统计口径**单独统计、不计入综合能耗**（在表注和7.3.4注明）
- 派生值必须全部程序化重算比对（execute_code）：折标、指标（人均/单位面积/单位业务量）、费用（含用量/价格因素分解）、碳排放（各源+合计+占比+增幅）、月度/结构占比
- 已知陷阱：油品碳排放曾算错 10 倍（0.9万L汽油×0.725kg/L×2.9251≈19 tCO₂ 而非 1.9）；表内四舍五入与精确值差 0.1 万时以精确值为准；设备型号与投运年份要匹配（SCB13 不存在于 2012 年 → SCB11）；单位面积碳排放、光伏减排量随口径修正联动全文（摘要/1.7/7.3/8章/10章/11章/备案表）
- 省级规章/定额标准编号与约束值**必须 web_search 核验，不编造**，未核验前用占位【示例：DB43/T ××××】并显式提示

## 数据来源：PG 全量导出

需要把真实客户数据（非示例）导出为中文 md 时，见
`energy-audit-pg-data/references/data-export.md`（已移入 pg-data 技能）——连接信息、表结构速查、能源代码映射（01=水/25=天然气，勿信表头）、
autocommit 陷阱、附件体系（WebUI 文件服务，外部不可直接下载）、
表序→报告逻辑重组（14 章结构 + 数据质量说明章节）。

**真实数据核验（写报告前必做）**：
- **单价交叉验证**：费用÷用量=单价，各能源逐一验（电价≈0.7元/kWh、水价≈5元/m³、燃气≈4.2元/m³、油≈10.6元/kg）。
  供热按计量表缴费时，从 ts_institution_scene 的 heat_pay_type/heat_price 取单价，费用÷单价=用量反推——
  烟台案例用此法发现 2024/2025 年供热量与费用**交叉录入**（89.61 元/GJ 验证三年吻合），报告中注明修正。
- **version_code 多版本**：is_draft=0 AND deleted=0 的记录可能新旧版并存（PL2026080401/0402），
  同一指标数值可能不同（如 2025 电量 1040085 vs 1011885），一律取 version_code 最大者。
- **费用单位混乱**：energy_unit 标'万元'但 total_value 实为元（703973.04=70.40 万），按数值量级判断，
  三年单位可能不一致（2023 标'元'、2024/2025 标'万元'）。
- 数据缺失（如 2023/2024 水量只有费用无计量）→ 报告标【数据缺失，待补充】，不编造、不按费用反推冒充真实值。
- **测试/复制数据判别（省立医院案例）**：① 同一客户新表旧表并存时交叉比对——energy_main 31条数值与另一家医院完全相同、热费 1200000.00 元整数×3年 → 全是复制测试数据，真实数据在旧表 ts_institution_energy；② 不同客户 2022 年数据完全相同（电 5090273/水 163107.7/气 57207）也是模板复制迹象；③ 历史导出 `projects/energy-audit/<单位>/data.json` 可能是测试包（buildings=妇幼楼/岚山地址）——盲信历史文件会错，地址+数值交叉验证；④ scene 两组矛盾记录用“缴费面积×单价=年热费”反推选组（省立：54523.3×22=119.95万 与热费精确吻合 → 取正式组）；⑤ 环境实测取 deleted=0 且 room_name 合理（剔除“治疗室测试”/“房间2”/数值全 33 的假记录）
- 山东定额标准数值速查（已验证）：`references/quota-supplement.md`（含 DB37/T 2672-2019 党政机关、DB37/T 2673-2019 三级医院基准值、折标系数、用水定额）
- 仿写路径（energy-audit-imitate 技能，bundled 不可改）：章节正文支持 markdown 表格——`表X.Y 标题` 行 + `| a | b |` 行（首行表头），report_generator._write_imitated_body 自动渲染为规范表格（12pt 居中、1.01cm 行高），组装无需手工建表。
- **skill 双副本同步方向**：energy-audit-imitate 存在 repo `skills/productivity/`（权威源，bundled 只读）与 profile 副本两处；repo 若被 profile 旧版覆盖，其自带验收测试（tests/skills/test_energy_audit_imitate_skill.py）会立刻红（resolve_unit_name/format-spec 引用）——改 repo 后必须同步回 profile，反之会把测试打回 0.1.0 时代。
- **仿写模式图表（2026-08 新能力）**：正文插 `[[图:类型|图注]]` 标记行即可嵌入图表，类型含 flow/trend/pie/cost_pie/monthly_electricity_kwh/monthly_water_m3/monthly_natural_gas_m3；数据来自 spec 的 `chart_data` 块（cost_pie 需各年费用字段 `*_cost_wan`）。不加标记 → 报告无任何图（用户会问"图表怎么没了"）。chart_data JSON 形状与渲染细节见 `references/word-finishing.md`
- **组装收尾工作流（2026-09 烟台法院实测）**：spec.json → assemble_report.py（生成 8 章）→
  officecli 追加附录（assemble 不支持附录；`office_cli_command` add/set 实现，禁用 python-docx）→
  40+ 项数值断言（与 DB 计算值比对）+ 占位符扫描（"测试"命中先确认是否"水平衡测试"术语）。
  ⚠ 图表口径：trend/pie 内部用 0.1229 折标，与正文 0.31 等价口径矛盾，指标展示图勿用；
  cost_pie 仅电/水/气/热 4 项（无油费）。⚠ indicators.py 内置 `_DEFAULT_BENCHMARKS['government']`
  =(12.8/8.8/6.0...) 为错误兜底值，定额以 `references/quota-supplement.md` 为准。
  完整链路见 `references/assembly-workflow.md`

## Word 生成（用户格式规范，硬性）

- H1 宋体 15pt 居中加粗 / H2 宋体 14pt 加粗 / H3 宋体 12pt 加粗
- 正文 宋体+Times New Roman 12pt 两端对齐、首行缩进 2 字符（Pt(24)）、1.5 倍行距
- 表格 12pt 居中、行高 1.01cm（AT_LEAST）、垂直居中、表头加粗、Table Grid 边框
- 表注（`>` 引用块）灰色 12pt 无缩进；表题（**表X-X**）居中加粗
- 页脚居中页码域（PAGE）、目录 TOC 域（`TOC \o "1-3" \h \z \u` + outlineLvl），打开 Word 后 Ctrl+A → F9 更新
- **报告收尾三件套（assemble 自动完成，用户视作必有项）**：① 目录自动刷新——`word/settings.xml` 写 `<w:updateFields w:val="true"/>`，Word/WPS 打开即刷目录，不再依赖手动 F9；② 页眉 DrawingML 水印——由 `scripts/add_watermark.py` 注入（被审计单位全称 unit_name，behindDoc=1，浅灰宋体约45°；**禁止 VML textpath**，VML 曾用 468pt/opacity 0.15 被批"不明显"，后按 repo 规范改为 DrawingML）；③ 页脚页码——"第 X 页 共 Y 页"（PAGE+NUMPAGES 域）10.5pt 居中。用户报"没有目录/水印/页码"时先 zip 检查这三部件，勿盲目重跑
- 封面：单位名 22pt + "能源审计报告" 26pt 居中 + 报告信息表（md 第一个表格）
- 运行：`D:/develop/anaconda3/python.exe scripts/md_to_docx_energy_audit.py <in.md> <out.docx> [单位名] [审计期]`

## Procedure

1. 读模板 PDF（read_file 自动提取文本），提炼 0–11 章骨架 + 表格清单
2. 选定虚拟单位（避免真实校名/院名），先定基础量：建筑面积、人数、电/气/水三年量 → 由基础量推导一切派生值
3. 按骨架写 markdown：每章【示例】正文（LLM 自然文本，非模板腔）+ 表格；【填写】留给单位实际信息；【图表填报说明】保留
4. **程序化校验**（execute_code）：重算全部派生值与文档比对，不一致立即修，修正后全文联动检查
5. 转 Word（见上），XML 验证（zipfile 统计 outlineLvl/eastAsia/trHeight/vAlign/sz 数量 + docx_validate.py）

## Pitfalls

- **energy_audit_* 工具全报 TypeError: unexpected keyword argument 'task_id'**：
  handler 签名若只写 `(args: dict)` 会炸——registry.dispatch 会透传
  `task_id/session_id/enabled_tools` 等 kwargs。修复：签名改 `(args: dict, **kwargs)`，
  涉及 tools/energy_audit_tool.py（6 个 handler）、energy_audit_rag_tool.py（1 个）、
  energy_audit_imitate_tool.py（2 个）。改文件后当前会话旧模块仍生效，
  用 execute_code 直接 import 调 handler 验证或重启后端。
- **仿写/组装输出 docx 被占用**（Permission denied）：目标文件被 Word/预览打开时
  assemble 报 `[Errno 13]`，改用新文件名（如 `_v2.docx`）重新生成，不覆盖在用的文件。
- 项目 `.venv` python 没有 python-docx：必须用 `D:/develop/anaconda3/python.exe`（anaconda 有）
- 目录/页码是 Word 域：python-docx 不计算，占位文本提示用户更新域
- 备案表（综合能耗/其他能源/人均指标）与报告正文口径必须一致（本项目：其他能源=车用油 14.6 tce，不计入综合能耗）
- 碳排放在 8.2 表合计、8.3、8.4、11.1 多处出现，改因子/口径必须全文联动；摘要和 1.7.1 也带碳排放数字
- 费用口径：电费按**外购量**×均价（光伏自用不付费），用量/价格因素分解要能对账回费用差
- **仿写图表输出文件被占用**（Permission denied on charts/*.png）：用户打开旧图时文件锁；flow 已用时间戳文件名（energy_flow_<ts>.png），其余 chart_*.png 同目录冲突时清理或改 output_dir
- **仿写图表缺 matplotlib 静默跳过**：图表渲染 try/except ImportError 返回 None，报告无图且不报错；matplotlib 已入 pyproject energy extra（>=3.9,<4），.venv 需 `uv pip install` 装上（2026-08 实测 uv lock 在本机 uv 0.9.16 因仓库新版 lock 格式解析失败，属环境限制非本次改动）
- **无 LibreOffice 时无法渲染 PNG 目检**，用 XML 字符串统计 + docx_read --structure/--text + docx_validate 替代
- **往现有 docx 插入新段落**：deepcopy 模板段落再插 `addnext()` 会复制出双份 rPr，
  `run.font.bold` 读出来是 None、加粗不生效——插入后用 python-docx API 直接
  `run.font.bold = True` 重新设置一遍即可（2026-08 省立医院 6.5 节实战验证）
- 编辑用户报告模板 docx 前先备份（`cp 源.bak.docx`），写回后复验格式

## Verification

- 数据：execute_code 重算 2025 全部派生值，逐项与文档数字一致（含增幅、占比、四舍五入临界值）
- docx：`docx_read.py --structure`（表格数=md 表格数，如学校版 23 张）、`--text` 抽查、`docx_validate.py` 输出 ok
- 格式：XML 检查 `w:eastAsia="宋体"`、`trHeight`、`w:vAlign`、`w:sz w:val="24"/"30"`、outlineLvl、footer 中 PAGE 域
