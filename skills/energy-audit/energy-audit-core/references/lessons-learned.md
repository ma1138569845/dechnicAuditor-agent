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
| D4 | 建筑表里混进**别的项目**的楼与地址（省立医院东院区名下出现岚山区 6 栋楼 + 地址"岚山区岚山西路566号"） | 建筑地址与项目地址不一致 → **采集侧告警**（`detect_building_address_mismatch`）；报告建筑表地址一律取 `proj.base.address` | `ea-authoring/references/chapter-guides-1-4.md`（建筑地址口径） |
| D5 | 多版本并存时用"多数投票"消解冲突 → 选中错值（热力 2024/2025 颠倒） | 版本归一：**草稿优先 → version_code 大者 → id 大者**；指定 `--version-code` 只取该正式快照；**禁多数投票**，冲突输出告警 | `version-normalization.md` |
| D6 | 费用 `energy_unit` 标"万元"实为"元"，量级差 1 万倍 | 费用单位字段不可信 → 用**单价反验**（电≈0.7 元/kWh、水≈5 元/m³、气≈4.2~4.6 元/m³、热≈89.6 元/GJ） | `energy-audit-pg-data/SKILL.md`（费用单位陷阱） |
| D7 | 费用取到 0（旧版本 `real_value=0`） | 取费用用 `unit_total_value/10000`（元→万元）；实物量 dt=1/4/5 用 total 即可 | 同上（费用字段取数） |
| D8 | 建筑面积口径含地下车库导致指标偏低 | 分母用 `build_area − garage_area`；采暖面积取 `build.heat_area`（不在 scene 表）；**2026-09-20 代码已实现**（indicators.calc_unit_area_* 扣减 garage_area；chapter5_agent/caliber 注入） | `conventions.md`、`energy-audit-pg-data/SKILL.md` |

## 二、标准与取值

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| S1 | 电力折标误用当量值 0.1229（差 2.5 倍） | 山东口径一律 **0.31 kgce/kWh（等价）**；气 1.2143（DB 里的 1.33 是错值）；**水不折算** | `coefficient-caliber.md`（唯一权威） |
| S2 | 定额取值拿错气候区（法院本应 A 区 20.0/11.9/6.5，却取了 B 区 20.8/12.6/6.9 并标"来源：DB"） | 取值必须**机构分档 × 气候区**双维度匹配；报告引用须写**标准号+表号**（原文锚点）；跑 `verify_benchmark_sources.py` 自检 | `standards-values.md`（24 条 ★来源锚点）、`ea-calculation/scripts/verify_benchmark_sources.py` |
| S7 | **气候区不再从 DB 取**：`ts_customer_info.climate_type` 大面积误填为 A（济南的省立医院、聊城的莘县县政府在 DB 里都是 A，按 DB37/5026 应为 **B 区**）；已交付的省立医院东院区 indicators.json 用的是二级 **A 区** 22.6/15.3/9.4 | 气候区**一律以 `standards-values.md`《山东省气候区划》表为准**（代码单点 `tools/energy_audit/climate_zone.py`）；地市判定优先用**行政区划代码**（district_id 前 4 位），DB 的 climate_type 仅作交叉校验并提示复核 | `standards-values.md`《山东省气候区划》、`tools/energy_audit/climate_zone.py` |
| S8 | 平台字典码 `ts_customer_info.customer_func / children_func`（一级单位类型 + 二级分档）长期**没被采集使用**，机构类型改为按单位名分类器猜 | 机构类型与档位**优先取平台字典码**（教育 8 档 / 医疗一~三级 / 党政省~市级以下 / 场馆 5 类），分类器只作兜底；字典码在 `tools/energy_audit/dept_dict.py`（可 `--check-db` 自检） | `tools/energy_audit/dept_dict.py`、`energy-audit-pg-data/SKILL.md` |
| S9 | 跨标准借表 + 误记：① 医疗机构 表2 曾借用**党政机关 2672** 的供暖定额（12.7/11.1/8.3，应为 2673 自己的 13.4/10.0/7.9）② 医疗 表5 EUE 误记为 2.2/2.0/1.6（原文是 **2.3/1.8/1.4**） | 每个机构类**只用本标准的表**；四类 EUE（党政 2.2/1.8/1.4、教育 2.2/1.6/1.3、医疗 2.3/1.8/1.4、场馆 2.2/1.7/1.4）各不相同，禁止互相借用；改内置值必须回 `standards-values.md` 同改并跑 `verify_default_benchmarks.py` | `standards-values.md`（医疗表2/表5）、`ea-calculation/scripts/verify_default_benchmarks.py` |
| S10 | 定额**取值链**口径不清：DB `ts_limit_config` 曾写进取值链，但维度参数写死（field_type 传 20/30、limit_type/climate 恒 A）导致从未命中，实际全靠内置默认，却让人以为"来源：DB" | **取值链 = 用户显式值 > 内置默认（唯一权威）**；DB **退出取值链**，只由 `audit_db_benchmark()` 交叉校验并告警"请复核平台数据"；`来源` 字段如实写 User/Default | `tools/energy_audit/indicators.py::resolve_benchmark / audit_db_benchmark`、`ea-calculation/SKILL.md` |
| S11 | ① 曾以为"4452 无场馆面积口径定额"→ 场馆取水统一不对标，实际 4452 表2 **有**图书馆/档案馆 1.3/1.8、博物馆 1.5/1.8、纪念馆 0.62/1.26 m³/(m²·a)；② `_SUBTYPE_DEFAULT` 若给"部分子类型才有定额"的表设默认键，会把该定额错套到无定额的子类型上（如给 `venue/water_per_area` 设默认"图书馆"→ 剧院/体育馆也被对标） | 有定额就启用对标（2026-09-20 启用图书馆/博物馆）；**"仅部分子类型有定额"的表不得设默认键**，查不到即 (0,0,0) 不对标；实测 L/(m²·a) 与定额 ×1000 比较 | `standards-values.md`（4452 面积口径）、`tools/energy_audit/indicators.py`（`_SUBTYPE_DEFAULT`、`calc_water_indicator` 场馆分支） |
| S12 | **幽灵层**：文档长期宣称定额"三级兜底（DB → 用户提供 → 内置默认）"，实际 `resolve_benchmark(..., user_values)` / `resolve_coefficient(..., user_value)` 这两个"用户提供"参数**从来没有调用方传值**（全仓 grep 复核），`来源='User'` 永远走不到；`conventions.md` / `chapter5-spec.md` / `ea-calculation/SKILL.md` 都按它写了文档 | **写完机制要回头验证它是否真的可达**：参数/配置项若无人传值就不是能力，是误导。2026-09-20 删除两个参数；项目级系数覆盖的真实路径是 `EnergyYearly.coefficients`（data.json 持久化），定额无覆盖层。**再要"人工核定定额"必须连项目级 `benchmark_overrides` + 依据文字 + 报告标注 + V2 校验一起建**，不许只加参数 | `tools/energy_audit/indicators.py`（`resolve_benchmark` / `resolve_coefficient` 签名）、`ea-calculation/SKILL.md` Capability 3/4、`conventions.md`、`chapter5-spec.md` |
| S3 | 把用水两档（通用/先进）与能耗三档（约束/基准/引导）混用 | 能耗=三档；用水=两档；评价短语用固定词表 | `energy-audit-style/references/rules.md`（评价短语） |
| S4 | 未剔除供暖电耗，非供暖能耗/常规电耗偏高约 15% | 从总电耗中剔除供暖循环泵/风机电耗后再算非供暖类指标 | `coefficient-caliber.md`、`ea-calculation/SKILL.md` |
| S5 | 教育类项目（DB37/T 2671）曾无定额矩阵，运行时兜底还写错标准号（写成不存在的 DB37/T 2674）并带编造的电耗/人均值 | 教育类定额**已全档收录**（原文核验 2026-09-20）；取值必须按**机构类型+二级分档**（不分气候区），禁止跨机构类型借用 EUE 等同类值 | `standards-values.md`《教育机构能源消耗定额标准》一节、`tools/energy_audit/indicators.py` `_DEFAULT_BENCHMARKS['education']` |
| S6 | 教育类报告自相矛盾：同一份报告**表里写约束值 16.5**、**正文写 25.5** kgce/(m²·a)（济南大学 0620 稿） | 表格与正文的定额值必须**同源**（都从 `standards-values.md` 取）；25.5 是党政机关省级约束值，属**跨标准串档**，教育类无此值 | `standards-values.md`（教育类表1）、`ea-validation/scripts/datava/mode_indicator_review.py` |

## 三、报告与写作

| # | 现象 | 铁律 | 详见 |
|---|---|---|---|
| W1 | 后一章数值与前章不一致（从上下文"记忆"里抄数） | 数值**只从** `data.json` / `indicators.json` / `chapter5.md` 读；禁从上下文或前序章节文本提取 | `ea-authoring/SKILL.md` 三批铁律 |
| W2 | 第5章出现三份稿，装配读了旧的一份 | 权威划分：`chapter5.md`=计算产物（只读）→ `chapter_md/ch5_import.md`=装配唯一输入（由 `prepare_chapter_md.py` 就位，不覆盖作者稿）；`ch5.md`/`segA-C`=中间物 | `ea-calculation/SKILL.md`（第5章产物权威说明） |
| W3 | 数据缺失如实标【待补充】却被 V3 判 P0 阻塞交付 | 已登记的数据缺失写入 `<项目>/missing_items.json` → V3 记 **P1 放行**；未登记占位仍 P0 | `ea-validation/SKILL.md`、`_changes/T2-直跑验证记录.md` |
| W4 | 图注段落被当作正文判"两端对齐偏离" | 图注/表题单独成段、居中 12pt；V3 已按 `caption` 段型校验 | `ea-authoring/references/chapter-guides-6-8.md`、`docx-techniques.md` |
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
