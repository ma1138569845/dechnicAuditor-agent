# 因果知识图谱（KG）架构

> 版本: 1.0 | 日期: 2026-07-14 | 关联: knowledge_schema.py, energy_kg.py, data_analysis.py

## 架构

```
knowledge_schema.py          energy_kg.py               data_analysis.py
    (数据模型)        →       (NetworkX图)       →       (v2.0入口)
  CauseNode                   EnergyKnowledgeGraph       analyze_with_diagnosis()
  MeasureNode                 ├─ diagnose()               format_diagnosis_for_chapter7()
  CausalChain                 ├─ diagnose_all()
  DiagnosisResult             ├─ get_causes_tree()
  DiagnosisReport             └─ get_measures_for_system()
```

## 30条因果链 · 12系统覆盖

| 系统 | 链数 | 代表异常 |
|------|------|----------|
| 中央空调系统 | 10 | COP偏低、小温差、智能控制缺失、新风无热回收、水泵工频、冷却塔定频、末端无温控、冷机选型过大、夏季尖峰 |
| 供暖系统 | 5 | 供暖能耗增加、水力失衡、天然气增加、冬季电耗偏高、生活热水 |
| 照明系统 | 1 | LED占比低 |
| 给排水系统 | 2 | 用水量暴增、供水压力偏高 |
| 变配电系统 | 2 | 变压器轻载、功率因数偏低 |
| 建筑围护结构 | 2 | 外墙保温差、屋面隔热不足 |
| 能耗监测系统 | 2 | 监测平台缺失、能源管理体系缺失 |
| 可再生能源 | 1 | 光伏/太阳能未利用 |
| 信息机房 | 1 | PUE偏高 |
| 医疗设备 | 1 | CT/MRI待机 |
| 厨房系统 | 1 | 排风+灶具低效 |
| 办公设备 | 2 | 下班未断电、电梯老旧 |

## 关键词匹配规范（v3.0 语义混合匹配）

**v3.0 升级**：优先使用 DashScope Qwen embedding 做语义向量匹配（余弦相似度），关键词匹配作为辅助。混合评分权重：语义 0.5 + 关键词 0.3 + 类型/系统 0.2。

**关键词仍需遵守专有词规范**（作为语义匹配不可用时的fallback，也作为语义信号的补充）：

**禁止使用泛化词**，只允许领域专有词：

| 禁止（泛化） | 允许（专有） | 
|-------------|-------------|
| "偏高"、"偏低" | "COP"、"温差"、"负载率" |
| "增加"、"大幅" | "用水"、"供暖"、"天然气" |
| "下降"、"减少" | "PUE"、"功率因数" |
| "异常" | "水力失衡"、"近热远冷" |

**教训**：2026-07-14 扩充30条链时发现"偏高""偏低""增加"等泛化词导致跨系统错误匹配（"电梯能耗偏高"被匹配到"冬季电耗偏高"的"偏高"关键词）。全部清洗为专有词后诊断准确率 29/29。

## 诊断流程

```
异常分析流程（tools/energy_audit/data_analysis.py）
    │
    ├─ 首次运行: analyze_with_diagnosis(energy_data)
    │   ├─ analyze_energy_data()  → 统计异常检测
    │   └─ EnergyKnowledgeGraph.diagnose_all()  → 因果推断
    │       └─ 输出: AnomalyItem.diagnosis {primary_cause, confidence, measures}
    │
    ├─ 重跑（已有文件）: load_analysis_result()
    │   └─ 旧格式兼容: 无 diagnosis_stats → 自动补全 KG 诊断
    │
    └─ 用户确认异常后 → format_diagnosis_for_chapter7() → agent-xiaode
```

## 扩展因果链

在 `INITIAL_CAUSAL_CHAINS` 列表中追加新字典项：

```python
{
    "anomaly_description": "异常现象描述",
    "anomaly_keywords": ["领域专有词1", "领域专有词2"],  # 禁止泛化词！
    ...
}
```

## Obsidian Wiki 知识树（v3.2 新增）

`E:\data\wiki\energy-audit\` 包含 9 个页面，与 KG 30 条因果链双向关联：

| Wiki 页面 | KG 链数 | 内容 |
|-----------|---------|------|
| 中央空调系统.md | 10 | COP/温差/末端/新风/水泵 异常对照表 |
| 供暖系统.md | 5 | 锅炉/管网/水力失衡/生活热水 |
| 建筑围护结构.md | 2 | 外墙/屋面/外窗 热工参数 |
| 给排水系统.md | 2 | 用水异常/供水压力 措施表 |
| 照明与办公设备.md | 3 | LED/待机/电梯 |
| 变配电与信息机房.md | 3 | 变压器/PUE/功率因数 |
| 能源管理与可再生.md | 3 | 管理体系/光伏/太阳能 |
| 能耗指标解读.md | — | 5项指标/折标系数/定额对标 |
| 能源审计知识库.md | — | 总索引 |

每页含：frontmatter（title/type/tags/confidence）、异常→原因→措施对照表、节能措施按投资分级、wikilinks 交叉引用。
        {"label": "原因名称", "description": "详细描述", "probability": 0.60,
         "check_method": "验证方法"},
    ],
    "measures": [
        {"label": "措施名称", "description": "详细描述",
         "estimated_saving_rate": "5-10%", "investment_level": "低",
         "payback_period": "1年内"},
    ],
    "sources": ["标准名称", "案例来源"],
}
```
