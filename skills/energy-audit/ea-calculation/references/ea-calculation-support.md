# ea-calculation-support
> 本文由 3 个文件合并而成（2026-09-18 瘦身合并第 1 组，原文件已归档至 `_archive/2026-09-18/ea-calculation/references/`）：`energy-flow-diagram-spec.md`、`kg-visualization-feedback.md`、`reports-vector-db.md`；内容逐字保留，仅统一标题层级，引用请一律指向本文件。

---

## 能源流向图生成规范（原 energy-flow-diagram-spec）

> **2026-09-24 改版**：图5.1 由"graphviz 彩色三层推断图"改为
> **横式层级黑白图**（引擎 `tools/energy_audit/energy_flow_chart_v3.py`），
> 样式与参照包 `skills/productivity/energy-audit/scripts/make_flow_figs_v3.py`
> + 其 `references/energy-flow-diagrams.md` 一致（用户 2026-09-24 拍板：**只保留 1 张综合图、
> 只换风格**；旧 graphviz 实现保留为兜底，不删依赖）。

### 5.1 规范

1. 一句话概述: "{unit_name}主要用能类型包括{能源列表}。"
2. 图5.1 能源流向图
3. 饼图/趋势图/结构表/对比表 → 已全部移除

### 新版样式规范（`energy_flow_chart_v3.py`）

| 项 | 定值 |
|----|------|
| 图幅方向 | **横式分层**：最左=能源品种，向右逐级流向；同一层一列，同层**等宽** |
| 节点 | 白底、黑色直角细框（lw 0.9）、单行居中、无圆角；框高 0.34 in |
| 连线 | 正交主线走线：父框右缘中点 → 列间正中竖主线 → 各子水平引入；箭头 `-|>` |
| 字号 | L1 14pt / L2 12pt / L3 10pt（跨图一致） |
| 字体 | **宋体 SimSun**（Windows 自带，公文同源） |
| 配色 | **纯黑白灰**（无彩色） |
| 输出 | dpi=300、`bbox_inches='tight'`、pad 0.10；**图内不画标题**（标题由 Word 图注承担） |
| 画到第几层 | 默认 3 层（能源品种 → 用途分类 → 用能系统）；**设备明细留给第6章**，避免超宽被缩印 |

### 数据来源（2026-09-24 起：库树优先）

```
PG ts_energy_flow（客户树清单，一棵树=一个能源品种）
 + ts_energy_flow_level（节点：level/parent_id/sort）
   → pg_query.get_energy_flow_trees(customer_id)   # 拼成嵌套树
   → pg_collector 落 data.json 键 energy_flow_trees
   → caliber_agent 传 config['energy_flow_trees']
   → chapter5_agent._generate_flow_diagram() 调用 draw_energy_flow_forest(trees)
   → charts/energy_flow.png（产物路径不变，装配链/图号断言不感知）
```

⚠️ **能源代码不统一**（汽油：某机关 `300301` / 某医院 `31`），一律按"该客户有几棵树"驱动，
**不得按 energy_code 硬编码**。

### 降级链（三级，逐级兜底）

| 级别 | 触发条件 | 结果 |
|------|----------|------|
| 1 库树 | `energy_flow_trees` 非空 | 画平台登记的实际流向树（含各项目真实子系统） |
| 2 两层简化 | 库无登记 | 能源品种 → 用能系统（同平台模板口径分类，**不编造设备名**） |
| 3 旧 graphviz | 新引擎异常 / 无能源类型 | 旧实现 `energy_flow_chart.py`（保留）；连能源类型都没有才不画图 |

### 旧版 graphviz 实现（保留为兜底）

`draw_energy_flow_diagram(energy_types, equipment, unit_name)` —— 彩色三层推断图
（能源输入圆角矩形 → 用能系统 → 终端设备）。**仅在新引擎失败时调用**。
依赖：Graphviz 二进制（`winget install Graphviz.Graphviz` / `brew install graphviz`），
代码自动将 `C:\Program Files\Graphviz\bin` 加入 PATH。

历史缺陷（已不再是主路径，但兜底命中时仍存在）：
终端设备名来自 `equipment.name`，而 2026-09-24 之前**整条链没人给 config 传 equipment**，
于是恒退到内置默认设备名（烟台法院被写成"分体式空调"）；本次已在 caliber_agent 补传真实设备清单。

---

## KG 可视化与置信度反馈（原 kg-visualization-feedback）

### 可视化 (kg_visualizer.py)

生成三种图谱，支持嵌入报告或独立调试。

```python
from tools.energy_audit.kg_visualizer import visualize_kg, visualize_system, visualize_diagnosis
from tools.energy_audit.energy_kg import create_default_kg

kg = create_default_kg()

## 全图谱（暗色主题，概览）
visualize_kg(kg, "output/kg_full")

## 单系统详图（白底，适合嵌入报告第6章各系统分析）
visualize_system(kg, "中央空调系统", "output/hvac")

## 单条诊断推理图（高亮最可能原因路径）
visualize_diagnosis(kg, "冷机COP偏低", energy_type="电", output_path="output/cop_diag")
```

三色编码：🟥异常 → 🟧原因(概率%) → 🟩措施(节能率)

依赖：Graphviz（`C:\Program Files\Graphviz\bin\dot.exe`）+ `pip install graphviz`

### 置信度反馈 (energy_kg.py v4.0)

每次用户确认/否认诊断结果，自动更新因果链概率。贝叶斯平滑。

```python
kg = EnergyKnowledgeGraph()
kg.load_builtin()

## 确认诊断正确
kg.record_feedback("冷机COP偏低/下降", "冷却水温度偏高", was_correct=True)
## 冷却水温度偏高: 0.65 → 0.68 (确认1次)
## ...
## 冷却水温度偏高: 0.90 → 0.94 (确认6次)

## 否认诊断
kg.record_feedback("冷机COP偏低/下降", "制冷剂不足或泄漏", was_correct=False)
## 制冷剂不足或泄漏: 0.20 → 0.18 (下降)

## 持久化
kg.save_feedback("kg_feedback.json")
kg.load_feedback("kg_feedback.json")  # 下次启动恢复
```

pipeline 4.0a 自动集成：用户确认 anomaly + 填写 reason → 自动反馈。反馈文件路径：`~/projects/energy-audit/<项目>/kg_feedback.json`（注：实际落盘位置以调用方为准）

---


## 报告参考库与 RAG 检索

> **入口、目录与降级链的唯一定义在 `energy-audit-core/references/WORKFLOW.md` 第六节**
> （参考/知识三层 + 目录 + 检索入口 + 降级链 + "何时读哪层"决策表）。本文件**不复述**这些内容。
>
> 2026-09-22 清理说明：本节原内容（三层兜底 / `search_reports`·`search_for_chapter` /
> Obsidian `E:/data/wiki` / 21 份报告的标签统计）**已过期**——现行第一入口是本地成稿库
> `reference_library.search_local_references(chapter, tags)`（离线永远可用），跨库召回与
> 标准条文见第六节 6.2；`E:/data/wiki` 在本机**并不存在**；库内报告份数请以
> `energy-audit-core/scripts/verify_knowledge_assets.py` 的实测为准，勿在文档里写死。
>
> 写作时**每查一次**都要往 `<项目>/chapter_md/_retrieval_log.md` 登记一行（S14 闸门，
> 必需章：第3、6、7章），自检 `ea-validation/scripts/verify_retrieval_evidence.py <项目名>`。
