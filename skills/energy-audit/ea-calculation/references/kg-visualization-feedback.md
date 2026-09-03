# KG可视化与置信度反馈

## 可视化 (kg_visualizer.py)

生成三种图谱，支持嵌入报告或独立调试。

```python
from tools.energy_audit.kg_visualizer import visualize_kg, visualize_system, visualize_diagnosis
from tools.energy_audit.energy_kg import create_default_kg

kg = create_default_kg()

# 全图谱（暗色主题，概览）
visualize_kg(kg, "output/kg_full")

# 单系统详图（白底，适合嵌入报告第6章各系统分析）
visualize_system(kg, "中央空调系统", "output/hvac")

# 单条诊断推理图（高亮最可能原因路径）
visualize_diagnosis(kg, "冷机COP偏低", energy_type="电", output_path="output/cop_diag")
```

三色编码：🟥异常 → 🟧原因(概率%) → 🟩措施(节能率)

依赖：Graphviz（`C:\Program Files\Graphviz\bin\dot.exe`）+ `pip install graphviz`

## 置信度反馈 (energy_kg.py v4.0)

每次用户确认/否认诊断结果，自动更新因果链概率。贝叶斯平滑。

```python
kg = EnergyKnowledgeGraph()
kg.load_builtin()

# 确认诊断正确
kg.record_feedback("冷机COP偏低/下降", "冷却水温度偏高", was_correct=True)
# 冷却水温度偏高: 0.65 → 0.68 (确认1次)
# ...
# 冷却水温度偏高: 0.90 → 0.94 (确认6次)

# 否认诊断
kg.record_feedback("冷机COP偏低/下降", "制冷剂不足或泄漏", was_correct=False)
# 制冷剂不足或泄漏: 0.20 → 0.18 (下降)

# 持久化
kg.save_feedback("kg_feedback.json")
kg.load_feedback("kg_feedback.json")  # 下次启动恢复
```

pipeline 4.0a 自动集成：用户确认 anomaly + 填写 reason → 自动反馈。反馈文件路径：`~/projects/energy-audit/<项目>/kg_feedback.json`（注：实际落盘位置以调用方为准）
