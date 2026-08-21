# 能源审计知识库优化计划 v1.0

> 2026-07-14 | 基于当时系统现状 + 三方案对比分析
>
> **流水线现状（2026-08 更正）**：`run_pipeline.py` / `agent_xiaocheng()` 已不存在。
> 现行入口是 `energy_audit_tool.rest_generate_energy_audit_report` → `build_and_save_project` → `load_from_project` → `generate_word`。
> `search_for_chapter()` 仍是 RAG 库函数，**不写入第1/3章**。第3章走 PG 节能管理表 + 制度文件 LLM 提炼。

---

## 一、现状诊断

### 已有资产

| 组件 | 现状 | 评级 |
|------|------|------|
| **普通RAG** | Qdrant 向量检索（286 chunks），3层兜底（标签→向量→本地wiki） | ⭐⭐⭐⭐ 够用 |
| **数据结构** | project_data.py dataclass（ProjectBase/BuildingInfo/EnergyYearly/EquipmentInfo） | ⭐⭐⭐⭐ 基础好 |
| **规则引擎** | indicators.py 三级兜底（DB→用户→GB默认），定额对标，折标系数 | ⭐⭐⭐⭐ 核心资产 |
| **知识沉淀** | Obsidian wiki（E:/data/wiki）+ references/*.md（章节写作指南） | ⭐⭐⭐ 有但散 |
| **流水线** | `rest_generate_energy_audit_report` → `build_and_save_project` → `generate_word`（旧 `run_pipeline.py` 9步已移除） | ⭐⭐⭐⭐ 工程化成熟 |
| **数据源** | PostgreSQL（dc_energy_audit2）+ config.json + Excel | ⭐⭐⭐⭐ 结构化 |

### 缺失项

| 组件 | 缺失程度 | 影响 |
|------|---------|------|
| **GraphRAG** | 完全没有 | 故障诊断、因果推理、节能措施推荐全靠LLM临场发挥 |
| **LLM Wiki** | 半成品 | Obsidian有笔记但未被Agent系统化调用 |
| **知识Schema** | 隐性存在 | dataclass有结构但"能耗异常→原因→措施"的因果关系未建模 |
| **案例推理** | 缺失 | 历史报告只做相似度检索，不做结构化案例匹配 |

---

## 二、三方案定位（结合你的分析）

```
         ┌──────────────────────────────────────────┐
         │            能源审计知识体系               │
         ├──────────────┬──────────────┬────────────┤
         │   普通RAG     │   GraphRAG   │  LLM Wiki  │
         │   已经有了     │   长期目标    │  半成品    │
         ├──────────────┼──────────────┼────────────┤
         │ 查规范条文     │ 因果推理链    │ 专家方法论  │
         │ 找相似案例     │ 故障诊断树    │ 审计流程    │
         │ 引标准依据     │ 措施推荐图    │ 写作模板    │
         │ 政策法规检索   │ 能耗异常溯源  │ 经验沉淀    │
         └──────────────┴──────────────┴────────────┘
```

**结论：不是三选一，是三合一。建设顺序：巩固RAG → 建立Wiki → 构建Graph。**

---

## 三、分阶段优化计划

### 阶段1（当前~2周）：巩固普通RAG + 建立知识Schema

**目标：让现有RAG从"能用"到"好用"**

#### 1.1 知识分类入库（替换当前286 chunks的粗放模式）

当前问题：所有报告混在一个collection里，检索精度靠运气。

改造方案 —— 四库分离：

```
Qdrant Collections:
├── policy_library       # 标准规范（GB/DB37/条例）
│   └── 每条带: doc_name, article_no, effective_date, province
├── report_library       # 优秀报告章节（按chapter分chunk）
│   └── 每条带: institution_category, specific_type, chapter, province
├── equipment_library    # 设备参数与运行特征
│   └── 每条带: equipment_type, brand, model, rated_params
└── experience_library   # 专家经验（问题→原因→措施）
    └── 每条带: problem_type, system_type, cause, measure, case_ref
```

#### 1.2 知识Schema定义（这是GraphRAG的前置条件）

当前 project_data.py 的 dataclass 只有"是什么"，缺少"为什么"和"怎么办"。

新增 `knowledge_schema.py`：

```python
@dataclass
class EnergyAnomaly:
    """能耗异常 → 原因 → 措施 因果链"""
    anomaly_type: str        # COP下降 / 温差异常 / 负荷率低 / ...
    system: str              # 中央空调 / 照明 / 给排水 / ...
    possible_causes: List[CauseChain]  # 原因链
    detection_rules: List[DetectionRule]  # 检测规则
    recommended_measures: List[Measure]   # 建议措施

@dataclass
class CauseChain:
    cause: str               # 直接原因
    upstream: Optional[str]  # 上游原因
    downstream: List[str]    # 下游影响
    confidence: float        # 置信度（来自案例频次）

@dataclass
class EquipmentProfile:
    """设备画像 —— 额定参数 + 常见问题 + 节能空间"""
    equipment_type: str
    rated_params: dict       # {cop: 6.5, flow: 300, power: 200}
    common_issues: List[str]
    energy_saving_potential: List[str]

@dataclass
class BenchmarkRule:
    """定额对标规则"""
    institution_type: str    # 医疗/教育/机关
    indicator: str           # 单位面积非供暖能耗 / 人均综合能耗 / ...
    constraint: float        # 约束值
    baseline: float          # 基准值
    leading: float           # 引导值
    source: str              # DB37/T 2673-2019 附录A
```

#### 1.3 检索策略升级

当前：单次向量检索 → 返回top_k。

改造为**多路召回 + 重排序**：

```python
def smart_retrieve(query: str, context: AuditContext) -> List[KnowledgeItem]:
    # 路1: 向量语义检索（policy + report）
    # 路2: 标签精确过滤（同类型机构 + 同章节）
    # 路3: 关键字匹配（设备型号、标准编号）
    # 路4: 规则引擎匹配（定额对标、折标系数）
    # 重排序: 按 relevance + recency + authority 加权
    return rerank(results, context)
```

---

### 阶段2（2~4周）：LLM Wiki 体系化

**目标：把散落的专家知识变成Agent可调用的结构化页面**

#### 2.1 基于 Obsidian 的知识树

利用现有 `E:/data/wiki`，建立能源审计知识体系：

```
能源审计/
├── 审计流程/
│   ├── 公共机构审计流程.md
│   ├── 工业企业审计流程.md
│   └── 公共建筑审计流程.md
├── 用能系统/
│   ├── 中央空调系统/
│   │   ├── 冷源（冷水机组）.md     ← 含: 原理、常见问题、COP标准、节能措施
│   │   ├── 冷却塔.md
│   │   ├── 冷冻水泵.md
│   │   └── 末端（风机盘管）.md
│   ├── 照明系统.md
│   ├── 给排水系统.md
│   └── 变配电系统.md
├── 指标解读/
│   ├── 单位建筑面积非供暖能耗.md
│   ├── 人均综合能耗.md
│   └── 常规用能系统电耗.md
├── 标准规范/
│   ├── DB37-T-2673-2019.md       ← 关键条文摘录 + 审计应用场景
│   ├── GB-50189-2015.md
│   └── GB-T-17166-2019.md
├── 审计方法/
│   ├── COP测算方法.md
│   ├── 水平衡测试.md
│   └── 负荷率分析.md
└── 案例库/
    ├── 医院/
    │   ├── 省立医院东院.md        ← 标注: 发现的问题、采取的措施、效果
    │   └── ...
    └── 机关/
```

**每个知识页的结构模板：**

```markdown
---
tags: [中央空调, 冷水机组, COP]
system: HVAC
equipment: 离心式冷水机组
related_standards: [GB 50189-2015, DB37/T 2673-2019]
---

# 冷水机组节能分析

## 基本原理
（2-3段概述）

## 关键参数
| 参数 | 正常范围 | 关注阈值 | 报警阈值 |
|------|---------|---------|---------|
| COP | ≥5.0 | 4.0-5.0 | <4.0 |
| 冷冻水供回水温差 | 5-6℃ | 3-5℃ | <3℃ |
| 冷却水进出水温差 | 5-6℃ | ... | ... |

## 常见异常
1. **COP偏低**
   - 可能原因: ...
   - 检测方法: ...
   - 节能措施: ...

## 审计检查清单
- [ ] 核对额定COP与实际运行COP
- [ ] 检查运行时间与负荷率
- [ ] ...
```

#### 2.2 Agent-Wiki 集成

```python
# 对话侧 RAG 工具（energy_audit_rag_search）可扩展 wiki；
def search_wiki(topic: str, system: str = None) -> dict:
    """从 Obsidian wiki 检索结构化知识页"""
    # 1. 搜索 frontmatter tags 匹配
    # 2. 搜索标题/小标题匹配
    # 3. 返回: {title, content, frontmatter, related_pages}
```

---

### 阶段3（4~8周）：GraphRAG —— 核心差异化能力

**目标：让Agent具备因果推理能力，而不是只做文本匹配**

#### 3.1 知识图谱建模

基于 knowledge_schema.py 的实体关系，构建：

```
能源审计知识图谱

实体类型:
  - Building（建筑）
  - System（用能系统）
  - Equipment（设备）
  - Parameter（运行参数）
  - Anomaly（异常现象）
  - Cause（原因）
  - Measure（节能措施）
  - Standard（标准规范）
  - Case（审计案例）

关系类型:
  - Building --[has_system]--> System
  - System --[contains]--> Equipment
  - Equipment --[has_parameter]--> Parameter
  - Parameter --[deviates_to]--> Anomaly
  - Anomaly --[caused_by]--> Cause
  - Cause --[mitigated_by]--> Measure
  - Measure --[references]--> Standard
  - Case --[similar_to]--> Case
```

#### 3.2 实现路径

**方案A（推荐启动方案）：轻量图谱 —— NetworkX + JSON**

```python
# 不引入Neo4j，用NetworkX内存图谱 + JSON持久化
import networkx as nx

class EnergyKG:
    def __init__(self):
        self.G = nx.MultiDiGraph()

    def add_causal_chain(self, anomaly, cause, measure, confidence):
        """添加 异常→原因→措施 推理链"""
        self.G.add_edge(anomaly, cause, relation='caused_by')
        self.G.add_edge(cause, measure, relation='mitigated_by')
        self.G.nodes[cause]['confidence'] = confidence

    def diagnose(self, anomaly: str, system: str) -> List[dict]:
        """故障诊断：给定异常，输出原因树 + 建议措施"""
        # BFS遍历因果链
        causes = list(self.G.successors(anomaly))
        return [
            {'cause': c, 'measures': list(self.G.successors(c)),
             'confidence': self.G.nodes[c].get('confidence', 0.5)}
            for c in causes
        ]
```

**初始知识图谱内容（手工构建核心链，约50-100条）：**

| 异常 | 原因 | 措施 | 来源 |
|------|------|------|------|
| 冷机COP<4.0 | 冷却水温度偏高 | 清洗冷却塔填料 | 案例库 |
| 冷机COP<4.0 | 冷冻水出水温度过低 | 提高设定温度至7℃以上 | 标准 |
| 冷冻水温差<3℃ | 冷冻水流量过大 | 降低水泵频率 | 专家经验 |
| 供暖能耗同比+30% | 建筑围护结构保温差 | 增加外墙保温 | 案例库 |
| 照明电耗偏高 | 未使用LED灯具 | 更换LED | 标准 |
| ... | ... | ... | ... |

#### 3.3 Agent调用方式

```python
# 挂到 energy_kg / data_analysis（库函数）；当前 rest_generate 入口未调用
def causal_diagnosis(anomalies: List[str], building_context: dict) -> dict:
    """
    输入: ["冷机COP偏低", "冷冻水温差小"]
    输出: {
        "冷机COP偏低": {
            "causes": [
                {"cause": "冷却水温度偏高", "probability": 0.7, "check": "实测冷却水温"},
                {"cause": "负荷率长期<50%", "probability": 0.3, "check": "查运行记录"}
            ],
            "measures": ["清洗冷却塔", "优化群控策略"],
            "case_references": ["省立医院东院-2024"]
        },
        ...
    }
    """
```

#### 3.4 何时升级到 Neo4j

NetworkX 方案的瓶颈：
- 图谱节点 > 10,000 时内存告警
- 无持久化查询语言（全靠Python遍历）

**触发升级条件（任一满足即升级）：**
- 因果链数量 > 500 条
- 需要跨项目图谱推理（"这个医院的问题，其他同类医院怎么解决的"）
- 需要可视化展示推理路径给用户

---

### 阶段4（长期）：知识工程完整形态

```
                        Hermes Agent（DechnicAuditor）
                              │
                    ┌─────────┼─────────┐
                    │         │         │
              Knowledge Router（知识路由）
                    │         │         │
            ┌───────┼────┬────┼────┬────┼───────┐
            │       │    │    │    │    │       │
         普通RAG  Graph  Rule  Wiki  Case  Standard
         (查)     (推)  (算)  (教)  (比)   (引)
            │       │    │    │    │    │       │
            └───────┴────┴────┴────┴────┴───────┘
                              │
                      Report Generator
                      （小德 + author）
```

各模块职责：
- **普通RAG**：查规范条文、找相似报告段落、政策法规检索
- **GraphRAG**：故障诊断因果链、节能措施推荐、能耗异常溯源
- **Rule Engine**：指标计算、定额对标、折标系数（已有，继续增强）
- **LLM Wiki**：专家方法论、审计流程指导、写作规范
- **Case DB**：结构化案例匹配（同类型机构+同系统+同问题）
- **Standard DB**：标准条款细粒度检索（精确到条、款、项）

---

## 四、与当前流水线的集成点

```
现行生成管线中的知识调用时机：

build_and_save_project
  collect_from_pg          → 不使用知识库
  enrich_management_info   → LLM：制度文件提炼第3章 3.1/3.2（不是 RAG 仿写）
  compute_project_indicators → Rule Engine: 指标计算 + 定额对标

load_from_project / generate_word
  第3章  → PG energy_saving + management + 模板兜底（不调用 search_for_chapter）
  第1章  → 固定模板 + province_regulations
  第5章  → indicators.py

库函数（未接入 rest_generate 入口）：
  search_for_chapter / energy_audit_rag_search → 对话检索 Qdrant
  analyze_with_diagnosis / energy_kg          → GraphRAG 因果推理
  check_report                                → report_qa 格式校验
```

**最优先升级：把 `data_analysis.py` + GraphRAG 因果推理接到生成入口（若需要）。**
这是当前流水线中最大的价值洼地——自动生成路径只做 PG 取数 + 模板/指标填充，不做因果推断。`analyze_with_diagnosis()` 存在但未被 `rest_generate_energy_audit_report` 调用。

---

## 五、技术选型总结

| 组件 | 阶段1-2 | 阶段3 | 阶段4+ |
|------|---------|-------|--------|
| 向量库 | Qdrant ✅ | Qdrant ✅ | Qdrant / Milvus |
| 图谱 | 无 | NetworkX + JSON | Neo4j（条件触发） |
| Wiki | Obsidian MD | Obsidian + frontmatter | 可能迁移到专用KB |
| 嵌入模型 | Qwen text-embedding-v3 | 同左 | 按需评估BGE/M3E |
| LLM | DeepSeek | DeepSeek | 不变 |
| 规则引擎 | indicators.py | 同左 + Graph增强 | DSL化 |
| 数据模型 | dataclass | dataclass + KG schema | 统一Schema |

---

## 六、立即行动项（本周可做）

1. **[1天]** 创建 `knowledge_schema.py` —— 定义 Anomaly/CauseChain/EquipmentProfile/BenchmarkRule
2. **[2天]** 手工构建初始因果链（从省立医院报告 + 已有案例提取20-30条）
3. **[1天]** 实现 `EnergyKG` 基础类（NetworkX + diagnose() 方法）
4. **[1天]** 改造 `data_analysis.py`，在异常检测后调用 `causal_diagnosis()` 输出原因推断
5. **[1天]** 在 Obsidian wiki 建立 `能源审计/` 知识树根节点 + 2-3个核心页面
