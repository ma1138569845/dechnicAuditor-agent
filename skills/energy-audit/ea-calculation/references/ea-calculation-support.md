# ea-calculation-support
> 本文由 3 个文件合并而成（2026-09-18 瘦身合并第 1 组，原文件已归档至 `_archive/2026-09-18/ea-calculation/references/`）：`energy-flow-diagram-spec.md`、`kg-visualization-feedback.md`、`reports-vector-db.md`；内容逐字保留，仅统一标题层级，引用请一律指向本文件。

---

## 能源流向图生成规范（原 energy-flow-diagram-spec）

### 原理

用 **graphviz** (dot engine) 生成三层能源流向图，替代 matplotlib 版本。

### 架构

```
能源输入(圆角矩形) → 用能系统(直角矩形) → 终端设备(直角矩形)
    实线 = 主能源流   虚线 = 辅助/间接能源流
    颜色: 电=橙/水=蓝/气=绿/热=红/汽油=琥珀/柴油=褐
```

### 动态适配

`draw_energy_flow_diagram(energy_types, equipment, unit_name)` 完全由数据驱动：

| 参数 | 影响 |
|------|------|
| energy_types | 决定源节点数量和种类 |
| equipment 列表 | 终端设备名称从 equipment.name 生成 |
| equipment 为空 | 内置默认终端兜底 |
| unit_name | 标题变化 |

### 安装

- Windows: `winget install Graphviz.Graphviz`
- macOS: `brew install graphviz`
- 代码自动将 `C:\Program Files\Graphviz\bin` 加入 PATH

### 5.1 规范

1. 一句话概述: "{unit_name}主要用能类型包括{能源列表}。"
2. 图5.1 能源流向图
3. 饼图/趋势图/结构表/对比表 → 已全部移除

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
