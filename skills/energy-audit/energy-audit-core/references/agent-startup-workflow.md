# 能源审计报告 — Agent 启动流程

当用户说"帮我生成XX单位的能源审计报告"时，按以下流程执行：

## Step 1: 加载技能，走标准流水线（一键）**

```
skill_view('energy-audit')
→ 确认项目类型和参数
→ 准备 config.json（参考 config_shenxian.json）
→ 触发 Hermes 工具（energy_audit_*_tool，模型自主）或 CLI：
  python tools/energy_audit/data_collection_cli.py <项目名>
```

## Step 1b: 纯手动模式（无 JSON 配置）

```python
from tools.energy_audit.project_data import AuditProject, ProjectBase, EnergyYearly, BuildingInfo, save_project

proj = AuditProject(base=ProjectBase(name='项目', unit_name='被审计单位', ...))
# 补充 proj.energy_yearly, proj.buildings, proj.equipment 等...
save_project(proj)  # 持久化
# 报告正文由 author 按 ea-authoring 技能逐章写作 + office_editor 组装，
# 脚本不生成正文（report_generator 正文生成已于 2026-09-04 退役）。
```

## Step 2: 小数 — 项目数据初始化（新流程）

```
skills=["agent-xiaoshu"] 或 手动收集
生成 ~/projects/energy-audit/<单位名>/data.json（project_data.py::save_project）
包含: 基本信息/建筑/能耗/设备/计量/管理/照片
字段追溯: 每个数据记录 source (DB/Excel/用户)
```

## Step 3: 确认项目信息

从用户获取：
- 被审计单位全称、简称、地址、等级
- 审计类型（公共机构/公共建筑/工业企业）
- 机构类别（医疗/教育/党政机关/…）
- tags: {audit_type, institution_category, specific_type}

## Step 4: 数据库查询

```
pg_query.py → ts_energy_audit_project (项目信息)
            → ts_institution_project (机构信息)
            → ts_institution_energy_main/data (能耗/费用, data_type=1/2/3/4/5)
            → ts_building_info (建筑, 通过 project_id)
            → ts_energy_standard (折标系数)
            → ts_limit_config (定额标准)
```

## Step 4: 指标计算

```
indicators.py:
  calc_unit_area_non_heating_energy()  → 单位面积非供暖能耗 + DB37对标
  calc_unit_area_electricity()          → 常规用能系统单位面积电耗 + 对标
  calc_per_capita_energy()              → 人均综合能耗 + 对标
  calc_water_indicator()             → 取水指标（医院=床日/机关教育=人均/场馆=面积）+ 对标
  calc_baseline()                       → 5.4建筑能耗基准

三级兜底: DB → 用户提供 → 内置GB/DB37默认
```

## Step 5: RAG 检索同类参考

```
rag/rag_search.py（rag/rag_search.py）:
  search_for_chapter(chapter_key, tags, context) / search_reports(query, tags, top_k)
  → 返回同类机构同章节参考文本
  → 嵌入LLM prompt作为写作参考
```

## Step 6: 逐章生成（多数已自动化）

各章 build 方法现在优先从 project_data 自动生成文本/表格，仅在数据不足时回退到手动文本：

```
✅ 第1章 → 模板替换（从 audit_period 解析年份，energy_types 映射中文）
✅ 第2章 → 从 buildings + base 自动生成 2.1/2.2/2.3 文本 + 建筑参数表
⚠️ 第3章 → management.* 自动填充（内容仍需管理信息数据）
⚠️ 第4章 → metering 数据自动填充
✅ 第5章 → 从 energy_data 自动生成表5.1~5.8 + 对标（完全结构化）
⚠️ 第6章 → equipment 自动生成基础设备段（详细描述需用户补充）
✅ 第7章 → 从 chapter4/6 数据推断问题→建议（用户仍可覆盖，summary 表需用户）
⚠️ 第8章 → 用户提供聚合文本（或 LLM 生成后传入）
```

✅ = 全自动 / ⚠️ = 半自动（可自动大部分，细节需补充）

## Step 7: 输出

```
ea-authoring（author 技能）:
  load_project() → 逐章按 chapterX-guide 写作 → office_editor 组装
  → 首行缩进 + 水印 + 目录页码 → 【单位名】能源审计报告.docx
```

## 关键路径

```
项目根: D:\data\pyProject\dc_agent\dechnicAuditor-agent
工具包: tools/energy_audit/
  chapter5_agent.py     — 第5章计算/图表（caliber）
  ea-authoring skill     — 正文写作 + Word 组装（author，主入口）
  indicators.py         — 5项指标计算 + 三级兜底
  chapter5_agent.py     — 第5章子Agent
  rag/rag_search.py     — RAG检索（search_reports / search_for_chapter）
  pg_query.py           — 数据库查询
  project_data.py       — 项目数据模型 & 持久化（小数Agent核心）
  ingest_reports.py     — 报告向量化入库（DEPRECATED → rag.ingestion.ingest_reports）

数据持久化: ~/projects/energy-audit/<单位名>/data.json
DB:     10.10.1.165:5432, dc_energy_audit2
Qdrant: 10.10.2.55:6333, collection=energy_audit_reports (286 chunks, 22份报告)
Key:    DASHSCOPE_API_KEY + DEEPSEEK_API_KEY in ~/.hermes/.env
```

## 格式速查

```
一级标题: 宋体 小三号(15pt) 居中 加粗
二级标题: 宋体 四号(14pt) 加粗
正文:     12pt 宋体+TNR, 1.5倍行距, 首行缩进2字符, 两端对齐
表格标题: 12pt 宋体 加粗 居中
表格内容: 12pt 宋体 居中, 行高1.01cm, 垂直居中
表格列宽: 不限制（自动适配）
封面:     36pt/14pt 宋体 加粗 居中, space_before=420pt
图片:     12cm宽 居中, 图注10pt 居中
列表:     ● 无序列表, 12pt 宋体
```
