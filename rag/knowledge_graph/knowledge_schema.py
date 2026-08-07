"""
能源审计知识Schema —— 因果推理数据模型

定义能耗异常、因果链、设备画像、定额规则的统一数据结构。
这是 GraphRAG 的地基：普通RAG查文本，KnowledgeSchema做推理。

用法:
    from rag.knowledge_graph.knowledge_schema import (
        EnergyAnomaly, CauseNode, MeasureNode, CausalChain,
        EquipmentProfile, BenchmarkRule,
    )

作者: 马天远 | 版本: 1.0.0 | 日期: 2026-07-14
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum


# ============================================================
# 枚举
# ============================================================

class EnergyType(Enum):
    ELECTRICITY = "电"
    WATER = "水"
    NATURAL_GAS = "天然气"
    HEAT = "热"
    PETROL = "汽油"
    DIESEL = "柴油"

class SystemType(Enum):
    HVAC = "中央空调系统"
    HEATING = "供暖系统"
    LIGHTING = "照明系统"
    WATER_SUPPLY = "给排水系统"
    POWER_DIST = "变配电系统"
    OFFICE = "办公设备"
    KITCHEN = "厨房系统"
    MEDICAL = "医疗设备"
    IT_ROOM = "信息机房"
    BUILDING_ENVELOPE = "建筑围护结构"
    RENEWABLE = "可再生能源"
    MONITORING = "能耗监测系统"

class InstitutionType(Enum):
    MEDICAL = "医疗"
    EDUCATION = "教育"
    GOVERNMENT = "党政机关"
    SPORTS = "体育场馆"
    OTHER = "其他"

class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ============================================================
# 因果链核心模型
# ============================================================

@dataclass
class CauseNode:
    """原因节点"""
    id: str                          # 唯一标识，如 'cause_cop_low_cooling_water'
    label: str                       # 人类可读标签，如 '冷却水温度偏高'
    description: str                 # 详细描述，1-3句话
    energy_type: EnergyType          # 关联能源类型
    system: SystemType               # 关联用能系统
    probability: float = 0.5         # 先验概率（来源：案例频次统计）
    check_method: str = ""           # 检测/验证方法


@dataclass
class MeasureNode:
    """节能措施节点"""
    id: str                          # 唯一标识
    label: str                       # 措施名称
    description: str                 # 详细描述
    estimated_saving_rate: str = ""  # 预估节能率，如 "5-10%"
    investment_level: str = ""       # 投资级别: '零投资'/'低'/'中'/'高'
    payback_period: str = ""         # 回收期，如 "2-3年"
    references: List[str] = field(default_factory=list)  # 引用的标准/案例


@dataclass
class CausalChain:
    """一条完整的因果链：异常 → 原因 → 措施"""
    anomaly_description: str         # 异常现象描述模板（可为模糊匹配）
    anomaly_keywords: List[str]      # 关键词列表，用于自动匹配，如 ['COP', '偏低', '下降']
    energy_type: EnergyType
    system: SystemType
    causes: List[CauseNode]          # 可能原因（按概率降序排列）
    measures: List[MeasureNode]      # 建议措施
    sources: List[str] = field(default_factory=list)  # 知识来源: ['DB37/T 2673-2019', '省立医院东院-2024']

    def __post_init__(self):
        """确保causes按概率降序"""
        self.causes.sort(key=lambda c: c.probability, reverse=True)


# ============================================================
# 设备画像模型
# ============================================================

@dataclass
class EquipmentProfile:
    """设备画像 —— 额定参数 + 常见问题 + 节能空间"""
    equipment_type: str              # 设备类型：'离心式冷水机组'/'螺杆式冷水机组'/'冷却塔'...
    system: SystemType
    typical_rated_params: dict       # 典型额定参数：{cop: 6.5, flow: 300, power: 200}
    common_issues: List[str]         # 常见问题描述
    common_causes: List[str]         # 常见原因
    energy_saving_potential: List[str]  # 节能潜力


# ============================================================
# 定额对标规则模型
# ============================================================

@dataclass
class BenchmarkRule:
    """定额对标规则"""
    institution_type: InstitutionType
    indicator: str                   # 指标名称，如 '单位面积非供暖能耗'（必填）
    specific_type: str = ""          # 子类型，如 '二级A'/'二级'
    indicator_unit: str = ""         # 单位
    constraint: Optional[float] = None   # 约束值
    baseline: Optional[float] = None     # 基准值
    leading: Optional[float] = None      # 引导值
    source: str = ""                 # 标准来源，如 'DB37/T 2673-2019 附录A'


# ============================================================
# 诊断结果模型
# ============================================================

@dataclass
class DiagnosisResult:
    """单条异常的诊断结果"""
    anomaly_description: str
    matched_chains: List[CausalChain]  # 匹配到的因果链（可能多条）
    primary_cause: Optional[CauseNode] = None     # 最可能原因
    recommended_measures: List[MeasureNode] = field(default_factory=list)
    confidence: float = 0.0           # 综合置信度 0-1

    @property
    def has_diagnosis(self) -> bool:
        return len(self.matched_chains) > 0


@dataclass
class DiagnosisReport:
    """整体诊断报告"""
    project_name: str
    total_anomalies: int
    diagnosed: int                    # 有因果推断的异常数
    undiagnosed: int                  # 无因果推断的异常数（需人工分析）
    results: List[DiagnosisResult] = field(default_factory=list)
