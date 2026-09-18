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

## 报告参考库与 RAG 检索（原 reports-vector-db）

### 数据概览

- 32份山东省直能源审计报告
- 按章节切分为 286 chunks
- 三级标签：audit_type → institution_category → specific_type
- 存储：Qdrant collection `energy_audit_reports` @ 10.10.2.55:6333

### 标签分布

| 类别 | 报告数 | 具体类型 |
|------|--------|----------|
| 党政机关 | 12 | 人社厅/法院/纪委监委/司法厅/市场监管局/生态环境厅/科技厅/科协/信访局/监狱局/贸促会/共青团 |
| 教育 | 4 | 济南大学/技师学院/省委党校/东营职业学院 |
| 医疗 | 2 | 省二院/省卫健委 |
| 场馆机构 | 2 | 图书馆/老干部活动中心 |
| 体育 | 1 | 体育训练中心 |

### 检索入口

```python
from rag.rag_search import search_reports, search_for_chapter
```

#### 三层兜底

```
search_reports(query, tags)
  ├─ Layer 0: Qdrant 标签直查（filter by tags，无需 API key）
  ├─ Layer 1: Qdrant 向量检索（语义匹配，需要 API key）
  └─ Layer 2: 本地知识库关键词搜索
       ├─ references/chapter*.md（能源审计章节指南）
       └─ Obsidian wiki E:/data/wiki（AI Agent/LLM 研究笔记）
```

#### Obsidian wiki 集成

`rag/rag_search.py` 的 Layer 2 额外搜素 `E:/data/wiki` 下的所有 `.md` 文件：

- 递归遍历全部子目录（entities/, concepts/, comparisons/, queries/）
- 自动排除 `_meta/`, `raw/`, `未命名.base/`, `.obsidian/` 及 `index.md`, `log.md`, `SCHEMA.md`
- 解析 YAML frontmatter 的 `title:` 字段作为章节名
- 结果标记 `source: obsidian_wiki`，与原 `local_wiki` 来源可区分
- 关键字匹配（全词命中计数排序），上限10条

#### 常用调用

```python
## 查同类机构同章节作为写作参考
ref = search_for_chapter('第2章', {'institution_category': '医疗'})

## 验证指标计算（查同类医院第5章对标）
ref = search_for_chapter('第5章', {'specific_type': '医院'}, '单位建筑面积')

## 参考节能建议
ref = search_for_chapter('第7章', {'institution_category': '教育'}, 'LED')
```

### 嵌入报告生成流程

```python
## 生成前设标签
report_data['tags'] = {'institution_category': '医疗', 'specific_type': '医院'}

## LLM生成某章前检索参考
builder = WordReportBuilder('公共机构')
builder.set_data(report_data)
ref = builder.get_chapter_reference('第2章', '公共机构概况')
## → 返回 Markdown 参考文本，嵌入 LLM prompt
```

### 入库脚本

```bash
python rag/ingestion/ingest_reports.py   # 旧 tools/energy_audit/ingest_reports.py 为 DEPRECATED 壳
```

分类规则：从文件名关键词匹配（医院/大学/法院/科技厅…）。
Embedding: DashScope `text-embedding-v3`, 1024维。
