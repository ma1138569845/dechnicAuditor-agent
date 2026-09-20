# 跨项目经验库（教训索引）— 2026-09-18 建

> 用途：把散落在各技能/修复文档里的**踩坑结论**集中成一份**索引式**清单（每条 = 现象 → 铁律 → 详见）。
> 原则：**本文件只写结论与指针，不复制细节**（细节留在权威文件/根因链文档里，避免再制造副本）。
> 维护：新踩坑先写进对应权威文件，再在本表登记一行。

## 一、数据源与取数

| # | 现象（踩过的坑） | 铁律 | 详见 |
|---|---|---|---|
| D1 | 用 project_id 关联业务表，取到空/错行 | 机构业务数据一律按 **customer_id** 关联；`ts_institution_project` 只用于定位项目与取 customer_id | `energy-audit-pg-data/SKILL.md` |
| D2 | 同一单位并存测试行与正式行，取到"测试公司" | 多项目行时选 `audit_dept_name` 为正式机构、`audit_year` 覆盖审计期者；**机构名含"测试"必须回退 `ts_register_dept` 正式名** | `pg_collector._official_auditor_org`；事故见本文 D3 |
| D3 | 生成报告盖章出现"同方德诚测试公司-1"、机构地址是"<单位名>-<地址>"拼接串 | 机构名称/地址必须过滤"测试"并回退正式注册记录；负责人/联系方式以项目表 `audit_dept_person/tel` 为准 | `conventions.md`《审计基本信息三张表》、`energy-audit-report-qa/references/fixes.md` |
| D4 | 建筑表里混进**别的项目**的楼与地址（省立医院东院区名下出现岚山区 6 栋楼 + 地址"岚山区岚山西路566号"） | 建筑地址与项目地址不一致 → **采集侧告警**（`detect_building_address_mismatch`）；报告建筑表地址一律取 `proj.base.address` | `ea-authoring/references/chapter2-guide.md`（建筑地址口径） |
| D5 | 多版本并存时用"多数投票"消解冲突 → 选中错值（热力 2024/2025 颠倒） | 版本归一：**草稿优先 → version_code 大者 → id 大者**；指定 `--version-code` 只取该正式快照；**禁多数投票**，冲突输出告警 | `version-normalization.md` |
| D6 | 费用 `energy_unit` 标"万元"实为"元"，量级差 1 万倍 | 费用单位字段不可信 → 用**单价反验**（电≈0.7 元/kWh、水≈5 元/m³、气≈4.2~4.6 元/m³、热≈89.6 元/GJ） | `energy-audit-pg-data/SKILL.md`（费用单位陷阱） |
| D7 | 费用取到 0（旧版本 `real_value=0`） | 取费用用 `unit_total_value/10000`（元→万元）；实物量 dt=1/4/5 用 total 即可 | 同上（费用字段取数） |
| D8 | 建筑面积口径含地下车库导致指标偏低 | 分母用 `build_area − garage_area`；采暖面积取 `build.heat_area`（不在 scene 表） | `conventions.md`、`energy-audit-pg-data/SKILL.md` |

## 二、标准与取值

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| S1 | 电力折标误用当量值 0.1229（差 2.5 倍） | 山东口径一律 **0.31 kgce/kWh（等价）**；气 1.2143（DB 里的 1.33 是错值）；**水不折算** | `coefficient-caliber.md`（唯一权威） |
| S2 | 定额取值拿错气候区（法院本应 A 区 20.0/11.9/6.5，却取了 B 区 20.8/12.6/6.9 并标"来源：DB"） | 取值必须**机构分档 × 气候区**双维度匹配；报告引用须写**标准号+表号**（原文锚点）；跑 `verify_benchmark_sources.py` 自检 | `standards-values.md`（17 条 ★来源锚点）、`ea-calculation/scripts/verify_benchmark_sources.py` |
| S3 | 把用水两档（通用/先进）与能耗三档（约束/基准/引导）混用 | 能耗=三档；用水=两档；评价短语用固定词表 | `energy-audit-style/references/rules.md`（评价短语） |
| S4 | 未剔除供暖电耗，非供暖能耗/常规电耗偏高约 15% | 从总电耗中剔除供暖循环泵/风机电耗后再算非供暖类指标 | `coefficient-caliber.md`、`ea-calculation/SKILL.md` |
| S5 | 教育类项目（DB37/T 2671）暂无定额矩阵 | 未收录标准时**标【待核验】**，禁止套用其它机构标准 | `standards-values.md`（其他机构类型待补充） |

## 三、报告与写作

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| W1 | 后一章数值与前章不一致（从上下文"记忆"里抄数） | 数值**只从** `data.json` / `indicators.json` / `chapter5.md` 读；禁从上下文或前序章节文本提取 | `ea-authoring/SKILL.md` 三批铁律 |
| W2 | 第5章出现三份稿，装配读了旧的一份 | 权威划分：`chapter5.md`=计算产物（只读）→ `chapter_md/ch5_import.md`=装配唯一输入（由 `prepare_chapter_md.py` 就位，不覆盖作者稿）；`ch5.md`/`segA-C`=中间物 | `ea-calculation/SKILL.md`（第5章产物权威说明） |
| W3 | 数据缺失如实标【待补充】却被 V3 判 P0 阻塞交付 | 已登记的数据缺失写入 `<项目>/missing_items.json` → V3 记 **P1 放行**；未登记占位仍 P0 | `ea-validation/SKILL.md`、`_changes/T2-直跑验证记录.md` |
| W4 | 图注段落被当作正文判"两端对齐偏离" | 图注/表题单独成段、居中 12pt；V3 已按 `caption` 段型校验 | `ea-authoring/references/chapter6-guide.md`、`docx-techniques.md` |
| W5 | 空话式结论（"能耗较高，节能潜力较大"） | 结论必须带数值与对照基准；禁词表见 rules.md | `rules.md`（禁词/句法骨架） |
| W6 | 分批写章后措辞/术语漂移 | 每批开工先读 `<项目>/chapter_md/_context.md`（接续契约，`prepare_writing_context.py` 生成），术语与口径以它为准 | 本文件 W6 指针：`ea-authoring/scripts/prepare_writing_context.py` |

## 四、装配与交付

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| P1 | 用 office_editor 逐段插入 → 单份 30~60 分钟、公式压平 | 主链固定为 `build_energy_audit_docx.py → finalize_energy_audit_pdf.py → ea_docx_asserts.py`；office_editor 仅用于存量 docx 定点修改 | `energy-audit-report/references/script-assembly-chain.md` |
| P2 | 交付前未跑断言，目录/水印/页码缺失 | 每份必跑断言器 10 项（zip/TOC/updateFields/水印/分隔线/页码/无 VML/无残留标记…），失败不得报"完成" | 同上 |
| P3 | Word COM 用相对路径报"找不到您的文件"；Word 保存剥离 `updateFields` | COM 一律**绝对路径**；收尾脚本 zip 级补写 `updateFields` | 同上 |
| P4 | 交付件与正本混放 | 正本在 `output/_script_build/`，对外交付**复制**到 `output/交付件/`（复制不移动） | 同上 |

## 五、协作与流程

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| C1 | 非交互模式（`hermes chat -q/-Q`、kanban worker）里等用户敲 `/compact`，任务卡住 | 批间**压缩上下文**：交互会话用 `/compact`；非交互模式改为**每批一个独立会话/任务**（或 `--resume` 分次），批边界即任务边界 | `energy-audit-routing/SKILL.md` 直跑铁律 2 |
| C2 | 长会话上下文膨胀、跨项目串味 | 一会话一项目；单会话上下文保持轻量（参考 <10 万 token） | 同上 + `lessons`（本表 C2） |
| C3 | 手工改 profile 侧技能，下次 sync 被覆盖 | 只改 repo `skills/energy-audit/`，然后 `scripts/sync_ea_skills.py` 发布 + `--verify` 校验 | `soul-purity-principle.md`、`deployment-ops.md` |
| C4 | 重大改动未确认就执行 | 先给方案 → 用户确认 → 再改；**不改已交付文件**，修订走"问题台账→逐项确认" | 本表 C4 指针：团队协作约定 |
