---
name: ea-validation
description: 能源审计三模式数据验证审查能力（datava 专属）。对能源审计项目做数据验证、完整性检查、能耗异常检测、指标复核、报告审查。支持 V1 采集后 DATA_CHECK / V2 计算后 INDICATOR_REVIEW / V3 报告后 REPORT_REVIEW，输出 P0/P1/P2 分级结论与退出码流程裁决。口径权威源：energy-audit-core/references/（定额矩阵/折标系数/版本归一）。
version: 2.1.0
---

# Data Validation Skill

## Overview

该 Skill 提供能源审计流水线的三检查点强制验证能力。

核心逻辑：**三种审查模式**，在三个检查点分别介入，每次审查不同内容，互不替代：

```
datacollection 采集完毕
    ↓
V1 DATA_CHECK（采集后）        → validation.json
    ↓
caliber 指标计算
    ↓
V2 INDICATOR_REVIEW（计算后）  → indicator_review.json
    ↓
author 报告生成
    ↓
V3 REPORT_REVIEW（报告后）     → report_review.json
```

职责边界：本 Skill 只做**只读审查与分级裁决**。不采集数据、不计算指标、不生成或修改报告。

---

## Execution Contract

### CLI 调用

```bash
python <skill>/scripts/data_verification_agent.py <项目名> --mode DATA_CHECK
python <skill>/scripts/data_verification_agent.py <项目名> --mode INDICATOR_REVIEW
python <skill>/scripts/data_verification_agent.py <项目名> --mode REPORT_REVIEW [--report <报告.docx>]
```

模式别名 `V1` / `V2` / `V3` 与全名等价。

### 常用开关

| 开关 | 作用 |
|------|------|
| `--json` | 机器可读 JSON 输出 |
| `--quiet` | 一行摘要（供主编快速裁决） |
| `--output-dir` | 改产出目录（默认 `~/projects/energy-audit/<项目名>/`） |
| `--no-triage` | V1 保留人工判定，不做自动分诊 |
| `--skip-completeness` | V1 跳过完整性检查 |
| `--report` | V3 显式指定报告路径 |

### 退出码（流程指令）

| 退出码 | 状态 | 上游动作 |
|--------|------|----------|
| 0 | pass / warn | 汇报结论，`kanban_complete` |
| 1 | error | 输入或依赖缺失，`kanban_block(reason=<缺什么>)` |
| 2 | block | 存在 P0，`kanban_block(reason="P0: <首条 title>")` |


> **reason 字段约定**：必须包含三段——`(a) 缺什么` + `(b) 由谁补` + `(c) 怎么补`。
> 例如：`"V1 输入待补: 是否存在'X 单位'需 datacollection 通过 pg_collector 反查单位名后回传 data.json 路径或 PG project_id"`。
> 见下"V1 输入缺失回执模板"小节。


### 严重级别

- **P0 阻塞**：数据/逻辑错误，必须修正后重跑
- **P1 待修**：影响报告质量，建议修正
- **P2 提示**：可接受，记录备查

### 环境变量

- `EA_TOOLS_ROOT` — 含 `tools/energy_audit` 的项目根（本技能 `scripts/datava/bootstrap.py` 读取；缺省逐级向上探测）
- `HERMES_PROJECTS_ROOT` — 项目数据根（本技能 `scripts/datava/common.py::projects_root()` 读取；缺省 `~/projects/energy-audit`）

---

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/kg-architecture.md` | 因果知识图谱架构（knowledge_schema.py / energy_kg.py / data_analysis.py，V1 因果诊断用） |
| `references/kg-keyword-pitfalls.md` | KG 关键词匹配规范（anomaly_keywords 只用领域专有词，禁泛化词） |

## Capability 1: V1 DATA_CHECK（采集后）

### 检查项

1. **完整性检查** — 封面/建筑/能耗/设备/人员 15+ 字段逐项检查，缺失项按关键词映射 P0/P1/P2
2. **配置/Schema 校验** — `check_config_schema()`：base 标量类型、建筑面积/用能人数正数范围、机构类别与审计起止必填、能耗年数建议（<3 年 P2）。类型错误→P1，负值→P0。与完整性检查分工：完整性管"缺不缺"，本项管"格式/语义对不对"（源自早期 `config_validator.py`，已适配 AuditProject 结构）
3. **异常检测** — 年度同比 ≥±30%、月度离群 >2σ、关键能源（电/水）缺失，三项统计规则
4. **月度一致性** — 月度明细与年度合计偏差 >5%、月份数不足 12（月度不存在则跳过，不计缺失）
5. **KG 因果诊断** — 30 条因果链（12 系统）推理异常原因+措施，纯本地执行
6. **自动分诊** — 负值 / 变化 ≥200% / 电水缺失 → `is_data_error`；其余 `confirmed=true`，原因取 KG 推断，无推断写"待现场核实"
7. **质量评级** — A/B/C/D 四级

### 质量等级

| 等级 | 条件 | 含义 |
|------|------|------|
| A ✅ | 无 P0/P1 且异常均为 warning | 可直接进入指标计算 |
| B ⚠️ | 有 P1 或 critical 异常 ≤2 | 可接受，建议处理异常 |
| C 🔶 | P1 >2 或 critical ≥3 | 建议补充数据后重验 |
| D ❌ | 存在 P0 | 不满足基本要求，需修正后重验 |

### 用户确认语义

- `confirmed=True` — 异常存在且原因属实
- `is_data_error=True` — 数据录入错误，需修正原始数据后重跑
- 已确认的异常重复运行时跳过，不再提示

### 产出

- `validation.json` — 兼容 `data_analysis.load_analysis_result`，`review` 字段挂审查信封
- `validation_report.txt` — 可读报告
- `diagnosis_chapter7_material.txt` — 第7章写作素材（有异常时）


### V1 输入缺失回执模板

**何时触发**：在 `~/projects/energy-audit/<项目名>/` 下未找到 `data.json`，或项目名与现有项目无法匹配（同名歧义、机构类型不符等）。

**datava 自身动作**（**只读**，不连 PG / 不采集）：

1. 扩大排查：`~/projects/energy-audit/*`、`~/Documents` / `~/Desktop`、`D:\agent\…`、其他盘符
2. 向用户确认项目名称是否正确
3. 读 `tools/energy_audit/db_config.py` 检查 PG 配置**是否就绪**（host/port/db/user 是否存在），但**不发起连接**
4. 检查 `apps/desktop/` 下 Electron 端 `state.db`（如可读）—— 这是诊断，不是采集
5. 仍 0 命中 → 按"用户口述 ≠ 数据存在"原则，**用 `clarify` 让用户补一条可验证线索**（绝对路径 / PG project_id / 截图），证据不能来自口述

**给主编（editor）的回执模板**（reason 字段三段式）：

```text
kanban_block(reason="V1 输入待补: <缺什么>; 由 <agent 名> 通过 <具体工具/动作> <怎么做>; 补完后回传 <data.json 路径 | PG project_id>")
```

**典型场景模板**：

| 场景 | 回执 |
|------|------|
| 项目目录不存在 | `kanban_block(reason="V1 输入待补: 是否存在'<X 单位>'需 datacollection 通过 pg_collector 反查单位名后回传 data.json 绝对路径或 PG project_id")` |
| `data.json` 已存在但读不出 | `kanban_block(reason="V1 输入待补: '<项目名>/data.json' 存在但 JSON 解析失败; 由 datacollection 复核原始文件后回传可解析版本")` |
| 依赖 `tools.energy_audit.data_analysis` 缺失 | `kanban_block(reason="V1 依赖待补: tools/energy_audit/data_analysis.py 缺失, 30 条 KG 因果链不可执行; 由开发者恢复模块后重跑 V1")` |
| 同名歧义（机构类型不符） | `kanban_block(reason="V1 输入待补: 用户指 '<X 单位>' 但现存 '<Y 单位>' 机构类型 <不匹配, 例如 医院 vs 公共机构>; 由用户确认正确单位名后再跑")` |

**datava 的硬约束**：

- ❌ 不连 PG / 不调 `pg_collector.collect_from_pg` —— 那是 datacollection 的活
- ❌ 不修改 data.json / 不替用户"猜测"单位名
- ❌ 不把"用户口述"等同于"数据存在"
- ✅ 仅产出 `error="依赖导入失败: …"` 或 `error="项目 '<X>' 的 data.json 不存在…"` 的 ReviewResult
- ✅ reason 字段必须可机读、可被 editor 转派工单

---

## Capability 2: V2 INDICATOR_REVIEW（计算后）

### 三条主线

1. **年际对比** — 指标变化 ≥15% P2 / ≥30% P1 / ≥50% P0；基数为 0 单独报 `V2.YOY.ZERO_BASE`
2. **对标合理性**
   - 三值序关系：约束值 ≥ 基准值 ≥ 引导值 > 0（颠倒为 P0）
   - 用水定额语义还原：默认表存（先进值， 通用值， 0)，位置映射后字段名与语义错位，按数值大小还原
   - 标准名与机构类型匹配（医疗/党政机关/教育）
   - 用水指标不得引用能耗类标准名
   - 定额来源：DB > User > Default 三级兜底，Default/User 来源记 P2 提示
   - **评价文字复核**：按阈值重算评价并与记录值比对，不一致为 P0
3. **数据一致性** — 面积（三处口径互校）/ 人数 / 床位 / 供暖电排除 / 指标量级合理性（超出 PLAUSIBLE_RANGE 多为分母口径错误）

### 输入加载优先级

```
indicators.json → data.json 内嵌 indicators → compute_project_indicators() 现算
```

### 产出

- `indicator_review.json` + `indicator_review.txt`

---

## Capability 3: V3 REPORT_REVIEW（报告生成后）

### 三条主线

1. **跨章数据一致性**
   - 各章建筑面积互校 + 与 data.json 互校（偏差 >1% 为 P0）
   - 第4章 vs 第5章综合能耗最大值比对
   - 审计年份在第4/5章的覆盖检查
2. **章节完整性**
   - 第1~8章齐备且非空（正文 ≥80 字或含表格）
   - 1.6 省级规章 ≥3 条
   - 第6章动态 H3 ≥3 个（按实际用能系统展开）
   - 第8章指标汇总表 ≥1 张
   - 必备三表：能源审计机构信息表 / 审计组人员名单 / 配合人员名单
   - 残留占位符检测（【待补充】/【XX/YYYY年M月/待LLM生成/TODO → P0）
3. **格式规范** — 字体/字号/加粗/对齐/行距/首行缩进/表格行高，全部对齐 `tools/energy_audit/format_spec.py` 的 `FormatSpec`（格式规范权威单点）；仅显式设置且偏离时判违规，继承样式不误报

### 报告定位

`--report` 显式指定 → 项目产出目录 → 当前目录，优先文件名含"能源审计报告"的最新 .docx。

### 产出

- `report_review.json` + `report_review.txt`

---

## Error Handling

### 依赖降级

- V1 依赖 `tools.energy_audit`（data_check / data_analysis / project_data），导入失败返回 error（退出码 1）
- V2/V3 可在无 `tools.energy_audit` 时基于 JSON/docx 独立运行
- V3 依赖 `python-docx`，缺失返回 error

### KG 降级

PG 连接失败时统计异常检测照常执行，KG 诊断可能部分降级；无匹配的异常标"未匹配"，不编造原因。

---

## Pitfalls

- **已确认异常不重复提示** — 重复运行跳过 `confirmed=True` 的项
- **验证结果覆盖策略** — 重新验证覆盖上一次 validation.json，历史保留到 validation_history/
- **定额逐年相同** — 结构性对标问题按指标只报一次，避免逐年刷屏
- **用水定额字段错位** — `indicators._DEFAULT_BENCHMARKS` 用水三元组顺序与能耗口径不同，必须按语义还原后评价

---

## 与现有 Agent 的分工

| Agent | 分工 | 与 datava 的关系 |
|-------|------|------------------|
| datacollection | 数据采集 | datava 消费其产出的 data.json（V1） |
| caliber | 指标计算+第5章 | datava 在其后运行 V2 复核指标 |
| author | 报告文本生成 | datava 在其后运行 V3 审查报告；V1 的 KG 诊断素材注入第7章 |
| knowledger | 知识库/因果诊断 | datava 调用其 KG 做因果推理 |
| editor | 主编总控 | 按检查点派发 datava，依据退出码裁决流程；**将 datava 的 `kanban_block(reason)` 转派回对应上游 Agent**（如 reason 指 datacollection 则转 datacollection，指开发者则转开发工单） |

### 工单流转（datava 视角）

```
用户 → datava 启动审查
   ↓
datava 判退出码:
   ├─ 0 → editor: kanban_complete（汇报结论）
   ├─ 1 → editor: kanban_block(reason="缺什么+由谁补+怎么补") → editor 转派
   └─ 2 → editor: kanban_block(reason="P0: <首条 title>") → editor 阻塞当前流程
```

**reason 字段是工单契约**——必须可被 editor 机读解析，分派到正确的上游 Agent。详见"V1 输入缺失回执模板"。

---


## Rules Summary

必须：

- ✅ 只读分析，不修改原始数据
- ✅ 无证据不写结论（KG 未匹配就标"未匹配"）
- ✅ 省级规章 web_search 验证
- ✅ 分级输出 P0/P1/P2，退出码裁决流程

禁止：

- ❌ 编造异常原因或诊断结论
- ❌ 字符串替换套用他省规章
- ❌ 采集数据 / 计算指标 / 生成报告
- ❌ 把继承样式误报为格式违规
