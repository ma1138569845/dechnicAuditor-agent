"""
能耗数据异常分析器 v2.0

升级内容:
  1. 集成 EnergyKnowledgeGraph 因果推理
  2. 异常检测后自动匹配原因+措施
  3. 诊断结果融入报告格式

作者: 马天远 | 版本: 2.0.0 | 日期: 2026-07-14
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import json, os
from pathlib import Path


# ============================================================
# 数据模型
# ============================================================

@dataclass
class AnomalyItem:
    """一条异常记录"""
    category: str           # '年度对比' / '逐月异常' / '数据缺失'
    energy_type: str        # '电'/'水'/'天然气'/'热'...
    description: str        # 异常描述
    year: int = 0
    month: int = 0
    value: float = 0
    reference_value: float = 0
    change_pct: float = 0   # 变化率（%）
    severity: str = 'warning'  # 'info'/'warning'/'critical'
    # 用户反馈
    confirmed: Optional[bool] = None  # None=待确认, True=确认, False=数据错误
    is_data_error: bool = False
    reason: str = ''        # 用户填写的原因
    # v2.0 新增: 系统推断 + KG诊断
    system: str = ''        # 推断的用能系统（用于KG匹配）
    diagnosis: Optional[dict] = None  # KG因果诊断结果 {primary_cause, confidence, measures, ...}


@dataclass
class AnalysisResult:
    """分析结果"""
    project_name: str
    years: List[int] = field(default_factory=list)
    energy_types: List[str] = field(default_factory=list)
    anomalies: List[AnomalyItem] = field(default_factory=list)
    # v2.0 新增: 诊断统计
    diagnosis_stats: Optional[dict] = None  # {diagnosed: N, undiagnosed: N}

    @property
    def pending_count(self) -> int:
        return sum(1 for a in self.anomalies if a.confirmed is None)

    @property
    def confirmed_count(self) -> int:
        return sum(1 for a in self.anomalies if a.confirmed is True)

    @property
    def error_count(self) -> int:
        return sum(1 for a in self.anomalies if a.is_data_error)

    @property
    def diagnosed_count(self) -> int:
        """有因果诊断的异常数"""
        return sum(1 for a in self.anomalies if a.diagnosis is not None)


# ============================================================
# 系统推断（用于KG匹配）
# ============================================================

SYSTEM_INFERENCE_RULES: List[Tuple[List[str], str]] = [
    # (关键词, 系统名)
    (['制冷', '冷机', 'COP', 'cop', '冷冻水', '冷却水', '冷却塔', '空调', '风机盘管', '末端', '供冷'], '中央空调系统'),
    (['供暖', '采暖', '供热', '锅炉', '热力', '换热站', '暖气'], '供暖系统'),
    (['照明', '灯光', 'LED', '荧光灯', '灯具', '路灯'], '照明系统'),
    (['用水', '水耗', '水量', '水表', '管道漏水', '灌溉', '卫生洁具', '节水'], '给排水系统'),
    (['变压器', '配电', '功率因数', '无功'], '变配电系统'),
    (['天然气', '燃气'], '供暖系统'),  # 默认天然气用于供暖
    (['汽油', '柴油', '车队', '车辆'], '办公设备'),
    (['光伏', '太阳能', '可再生'], '可再生能源'),
    (['围护', '保温', '外窗', '玻璃', '外墙'], '建筑围护结构'),
    (['监测', '计量', '平台'], '能耗监测系统'),
    (['医疗', 'CT', 'MRI', 'X光', '手术室'], '医疗设备'),
    (['厨房', '食堂', '餐厅'], '厨房系统'),
    (['机房', '数据中心', '服务器', 'UPS'], '信息机房'),
]


def infer_system(description: str, energy_type: str) -> str:
    """根据异常描述和能源类型推断用能系统"""
    desc_lower = description.lower()
    for keywords, system in SYSTEM_INFERENCE_RULES:
        for kw in keywords:
            if kw.lower() in desc_lower:
                return system

    # 兜底：按能源类型推断
    energy_system_map = {
        '电': '中央空调系统',  # 电耗异常默认空调
        '水': '给排水系统',
        '天然气': '供暖系统',
        '热': '供暖系统',
    }
    return energy_system_map.get(energy_type, '')


# ============================================================
# 核心分析
# ============================================================

def analyze_energy_data(energy_yearly: List[Dict], project_name: str = '') -> AnalysisResult:
    """
    分析能耗数据，返回异常清单（统计异常检测）。

    检测规则：
    1. 年度同比变化超过 ±30%
    2. 逐月异常值（单月偏离该年均值超过 2 倍标准差）
    3. 数据缺失检查
    """
    result = AnalysisResult(project_name=project_name)

    if not energy_yearly:
        return result

    # 收集年份和能源类型
    years = sorted(d.get('year', 0) for d in energy_yearly if d.get('year'))
    result.years = years

    energy_map = {
        'electricity_kwh': ('电', 'kWh'),
        'water_m3': ('水', 'm³'),
        'natural_gas_m3': ('天然气', 'm³'),
        'heating_energy_heat_gj': ('热', 'GJ'),
        'petrol_kg': ('汽油', 'kg'),
        'diesel_kg': ('柴油', 'kg'),
    }

    present_types = []
    for key, (cn, unit) in energy_map.items():
        if any(d.get(key, 0) and float(d.get(key, 0) or 0) > 0 for d in energy_yearly):
            present_types.append(cn)
    result.energy_types = present_types

    # === 规则1: 年度同比异常 ===
    for key, (cn, unit) in energy_map.items():
        yearly_values = []
        for d in energy_yearly:
            v = d.get(key, 0) or 0
            v = float(v) if v else 0
            yearly_values.append((d.get('year', 0), v))

        yearly_values.sort()
        for i in range(1, len(yearly_values)):
            prev_year, prev_val = yearly_values[i-1]
            curr_year, curr_val = yearly_values[i]
            if prev_val <= 0 or curr_val <= 0:
                continue
            change_pct = (curr_val - prev_val) / prev_val * 100
            if abs(change_pct) >= 30:
                severity = 'critical' if abs(change_pct) >= 50 else 'warning'
                desc = f'{cn}用量 {prev_year}→{curr_year}年变化{change_pct:+.1f}%（{prev_val:,.0f}→{curr_val:,.0f}{unit}）'
                result.anomalies.append(AnomalyItem(
                    category='年度对比', energy_type=cn,
                    description=desc,
                    year=curr_year, value=curr_val, reference_value=prev_val,
                    change_pct=change_pct, severity=severity,
                    system=infer_system(desc, cn),
                ))

    # === 规则2: 逐月异常（如果有月度数据） ===
    monthly_keys = ['monthly_electricity_kwh', 'monthly_water_m3', 'monthly_natural_gas_m3']
    monthly_names = {
        monthly_keys[0]: ('电', 'kWh'),
        monthly_keys[1]: ('水', 'm³'),
        monthly_keys[2]: ('天然气', 'm³'),
    }
    for mk, (cn, unit) in monthly_names.items():
        for d in energy_yearly:
            monthly = d.get(mk)
            if not monthly or not isinstance(monthly, list) or len(monthly) != 12:
                continue
            year = d.get('year', 0)
            values = [float(v or 0) for v in monthly]
            if max(values) <= 0:
                continue
            avg = sum(values) / 12
            if avg <= 0:
                continue
            variance = sum((v - avg) ** 2 for v in values) / 12
            std = variance ** 0.5
            if std <= 0:
                continue
            for m, v in enumerate(values):
                if v <= 0:
                    continue
                if abs(v - avg) > 2 * std:
                    pct = (v - avg) / avg * 100
                    severity = 'critical' if abs(pct) >= 50 else 'warning'
                    desc = f'{year}年{m+1}月{cn}用量异常（{v:,.0f}{unit}，偏离均值{pct:+.1f}%）'
                    result.anomalies.append(AnomalyItem(
                        category='逐月异常', energy_type=cn,
                        description=desc,
                        year=year, month=m+1, value=v, reference_value=avg,
                        change_pct=pct, severity=severity,
                        system=infer_system(desc, cn),
                    ))

    # === 规则3: 数据缺失检查 ===
    required = ['electricity_kwh', 'water_m3']
    for d in energy_yearly:
        year = d.get('year', 0)
        for rk in required:
            v = d.get(rk, 0) or 0
            if float(v) <= 0:
                cn = '电' if 'electricity' in rk else '水'
                result.anomalies.append(AnomalyItem(
                    category='数据缺失', energy_type=cn,
                    description=f'{year}年{cn}用量数据缺失或为零',
                    year=year, severity='critical',
                    system=infer_system(f'{cn}数据缺失', cn),
                ))

    return result


def analyze_with_diagnosis(energy_yearly: List[Dict],
                           project_name: str = '',
                           extra_kg_path: str = None) -> AnalysisResult:
    """
    分析 + KG因果诊断（v2.0 推荐入口）。

    1. 统计异常检测
    2. EnergyKnowledgeGraph 因果推断
    3. 结果融合
    """
    result = analyze_energy_data(energy_yearly, project_name)

    if not result.anomalies:
        result.diagnosis_stats = {'diagnosed': 0, 'undiagnosed': 0}
        return result

    # 加载 KG
    try:
        from rag.knowledge_graph.energy_kg import EnergyKnowledgeGraph
        kg = EnergyKnowledgeGraph()
        kg.load(extra_path=extra_kg_path)
    except Exception as e:
        print(f'[data_analysis] KG加载失败: {e}，仅做统计异常检测')
        result.diagnosis_stats = {'diagnosed': 0, 'undiagnosed': len(result.anomalies), 'error': str(e)}
        return result

    # 批量诊断
    anomaly_dicts = [
        {
            'description': a.description,
            'energy_type': a.energy_type,
            'system': a.system,
        }
        for a in result.anomalies
    ]

    diagnosis_report = kg.diagnose_all(anomaly_dicts, project_name)

    # 结果融合
    for i, a in enumerate(result.anomalies):
        if i < len(diagnosis_report.results):
            dr = diagnosis_report.results[i]
            if dr.has_diagnosis:
                a.diagnosis = {
                    'primary_cause': dr.primary_cause.label if dr.primary_cause else '',
                    'cause_description': dr.primary_cause.description if dr.primary_cause else '',
                    'cause_check_method': dr.primary_cause.check_method if dr.primary_cause else '',
                    'confidence': dr.confidence,
                    'matched_anomaly_type': dr.matched_chains[0].anomaly_description if dr.matched_chains else '',
                    'measures': [
                        {
                            'label': m.label,
                            'description': m.description,
                            'saving_rate': m.estimated_saving_rate,
                            'investment': m.investment_level,
                            'payback': m.payback_period,
                        }
                        for m in dr.recommended_measures
                    ],
                }

    result.diagnosis_stats = {
        'diagnosed': diagnosis_report.diagnosed,
        'undiagnosed': diagnosis_report.undiagnosed,
    }

    return result


# ============================================================
# 格式化输出
# ============================================================

def format_anomaly_report(result: AnalysisResult, show_diagnosis: bool = True) -> str:
    """生成可打印的异常报告（含诊断）"""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append(f"📊 能耗数据异常分析报告 - {result.project_name}")
    lines.append(f"{'='*60}")
    lines.append(f"审计年度: {result.years}")
    lines.append(f"用能类型: {result.energy_types}")
    lines.append(f"异常总数: {len(result.anomalies)} 项（待确认: {result.pending_count}）")
    if result.diagnosis_stats:
        d = result.diagnosis_stats
        lines.append(f"因果诊断: {d['diagnosed']} 项有推断 / {d['undiagnosed']} 项需人工分析")
    lines.append("")

    categories = {'年度对比': [], '逐月异常': [], '数据缺失': []}
    for a in result.anomalies:
        cat = a.category if a.category in categories else '年度对比'
        categories[cat].append(a)

    for cat, items in categories.items():
        if not items:
            continue
        lines.append(f"--- {cat} ---")
        for i, a in enumerate(items, 1):
            status = '⏳' if a.confirmed is None else ('✅' if a.confirmed else '❌数据错误')
            lines.append(f"  [{status}] {a.description}")
            if a.system:
                lines.append(f"      系统: {a.system}")
            if a.reason:
                lines.append(f"      原因: {a.reason}")
            # 诊断信息
            if show_diagnosis and a.diagnosis:
                d = a.diagnosis
                lines.append(f"      🔍 推断原因: {d['primary_cause']}（置信度: {d.get('confidence', 0):.0%}）")
                if d.get('cause_description'):
                    lines.append(f"         {d['cause_description'][:80]}")
                if d.get('measures'):
                    lines.append(f"      💡 建议措施:")
                    for m in d['measures']:
                        lines.append(f"         - {m['label']}（节能率: {m.get('saving_rate', '未知')} | 投资: {m.get('investment', '未知')}）")
        lines.append("")

    # 汇总：所有诊断措施（用于第7章写作参考）
    if show_diagnosis:
        all_measures = _collect_measures(result)
        if all_measures:
            lines.append(f"--- 💡 汇总建议措施（可用于第7章） ---")
            seen = set()
            for m in all_measures:
                if m['label'] not in seen:
                    seen.add(m['label'])
                    lines.append(f"  - {m['label']}: {m.get('description', '')[:60]}")
            lines.append("")

    return '\n'.join(lines)


def _collect_measures(result: AnalysisResult) -> List[dict]:
    """收集所有诊断中的建议措施"""
    all_measures = []
    for a in result.anomalies:
        if a.diagnosis and a.diagnosis.get('measures'):
            all_measures.extend(a.diagnosis['measures'])
    return all_measures


def format_diagnosis_for_chapter7(result: AnalysisResult) -> str:
    """
    生成第7章写作素材 —— 问题+原因+措施 结构化输出。
    可直接传递给 agent-xiaode 用于报告生成。
    """
    lines = []
    lines.append("## 能耗异常诊断结果（第7章写作素材）\n")

    for i, a in enumerate(result.anomalies, 1):
        if not a.diagnosis:
            continue
        d = a.diagnosis
        lines.append(f"### 问题{i}: {a.description}")
        lines.append(f"- 系统: {a.system}")
        lines.append(f"- 严重程度: {a.severity}")
        lines.append(f"- **推断原因**: {d['primary_cause']}（置信度 {d.get('confidence', 0):.0%}）")
        if d.get('cause_check_method'):
            lines.append(f"- 验证方法: {d['cause_check_method']}")
        if d.get('measures'):
            lines.append(f"- **建议措施**:")
            for m in d['measures']:
                lines.append(f"  - {m['label']}")
                lines.append(f"    - 节能率: {m.get('saving_rate', '待评估')}")
                lines.append(f"    - 投资级别: {m.get('investment', '待评估')}")
                lines.append(f"    - 回收期: {m.get('payback', '待评估')}")
                if m.get('description'):
                    lines.append(f"    - 说明: {m['description'][:100]}")
        lines.append("")

    return '\n'.join(lines)


# ============================================================
# 持久化
# ============================================================

def save_analysis_result(result: AnalysisResult, path: str):
    """保存分析结果到JSON"""
    data = {
        'project_name': result.project_name,
        'years': result.years,
        'energy_types': result.energy_types,
        'diagnosis_stats': result.diagnosis_stats,
        'anomalies': [
            {
                'category': a.category,
                'energy_type': a.energy_type,
                'description': a.description,
                'year': a.year,
                'month': a.month,
                'value': a.value,
                'reference_value': a.reference_value,
                'change_pct': a.change_pct,
                'severity': a.severity,
                'system': a.system,
                'confirmed': a.confirmed,
                'is_data_error': a.is_data_error,
                'reason': a.reason,
                'diagnosis': a.diagnosis,
            }
            for a in result.anomalies
        ]
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_analysis_result(path: str) -> AnalysisResult:
    """加载分析结果"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    result = AnalysisResult(
        project_name=data['project_name'],
        years=data.get('years', []),
        energy_types=data.get('energy_types', []),
        diagnosis_stats=data.get('diagnosis_stats'),
    )
    for a in data.get('anomalies', []):
        result.anomalies.append(AnomalyItem(
            category=a['category'], energy_type=a['energy_type'],
            description=a['description'], year=a.get('year', 0),
            month=a.get('month', 0), value=a.get('value', 0),
            reference_value=a.get('reference_value', 0),
            change_pct=a.get('change_pct', 0), severity=a.get('severity', 'warning'),
            system=a.get('system', ''),
            confirmed=a.get('confirmed'), is_data_error=a.get('is_data_error', False),
            reason=a.get('reason', ''),
            diagnosis=a.get('diagnosis'),
        ))
    return result


# ============================================================
# 第7章数据注入（v2.0：KG诊断 → chapter7 problems/solutions/summary）
# ============================================================

def inject_diagnosis_to_chapter7(result: AnalysisResult, rd: dict) -> dict:
    """
    将诊断结果注入诊断清单，供 author 第7章写作直接使用。

    转换规则:
      anomaly.description → problem.title + 嵌原因/验证方法
      anomaly.diagnosis.measures → solution (每个措施一条)
      anomaly.diagnosis.measures → summary rows (表7.1汇总表)

    Args:
        result: 分析+诊断结果
        rd: report_data 字典（就地修改，同时返回引用）

    Returns:
        rd (已注入 chapter7)
    """
    if not result.anomalies:
        return rd

    ch7 = rd.get('chapter7', {})
    problems = []
    solutions = []
    summary_rows = []

    for i, a in enumerate(result.anomalies, 1):
        if not a.diagnosis:
            continue
        d = a.diagnosis

        # 问题标题：提取核心异常类型
        anomaly_type = d.get('matched_anomaly_type', '') or a.description[:30]
        title = f"{a.energy_type}耗异常——{anomaly_type[:25]}"

        # 问题正文：异常描述 + 推断原因 + 验证方法
        text_parts = [a.description + "。"]
        if d.get('primary_cause'):
            text_parts.append(
                f"经能耗异常诊断系统分析，推断主要原因可能为：{d['primary_cause']}"
                f"（置信度{d.get('confidence',0):.0%}）。{d.get('cause_description','')}"
            )
        if d.get('cause_check_method'):
            text_parts.append(f"建议验证方法：{d['cause_check_method']}。")

        problems.append({
            'title': title,
            'text': ' '.join(text_parts),
        })

        # 措施：每条一个solution
        for j, m in enumerate(d.get('measures', []), 1):
            sol_title = m.get('label', f'建议{i}.{j}')
            sol_parts = [m.get('description', '')]
            extras = []
            if m.get('saving_rate'):
                extras.append(f"预计节能率{m['saving_rate']}")
            if m.get('investment'):
                extras.append(f"投资级别{m['investment']}")
            if m.get('payback'):
                extras.append(f"投资回收期{m['payback']}")
            if extras:
                sol_parts.append("（" + "，".join(extras) + "）")
            solutions.append({
                'title': sol_title,
                'text': ' '.join(sol_parts),
            })
            # 汇总表行
            summary_rows.append([
                str(len(summary_rows) + 1),
                sol_title,
                '—' if m.get('investment') == '零投资' else '待测算',
                '—',
                m.get('saving_rate', '—'),
                m.get('payback', '—'),
            ])

    # 无诊断的异常仅作为问题，不生成措施
    for a in result.anomalies:
        if a.diagnosis:
            continue
        problems.append({
            'title': f"{a.energy_type}耗异常",
            'text': f"{a.description}。该异常暂未匹配到因果诊断模型，建议人工分析原因。",
        })

    if problems:
        ch7['problems'] = problems
    if solutions:
        # 按 label 去重（多个异常可能匹配相同措施）
        seen_labels = set()
        deduped_solutions = []
        for s in solutions:
            if s['title'] not in seen_labels:
                seen_labels.add(s['title'])
                deduped_solutions.append(s)
        ch7['solutions'] = deduped_solutions
    if summary_rows:
        # solutions 去重后，summary_rows 也要同步去重
        seen_labels2 = set()
        deduped_rows = []
        for row in summary_rows:
            label = row[1]  # 改造项目名称
            if label not in seen_labels2:
                seen_labels2.add(label)
                row[0] = str(len(deduped_rows) + 1)  # 重新编号
                deduped_rows.append(row)
        ch7['summary'] = {
            'headers': ['序号', '改造项目', '预估投资(万元)', '年节能量(tce)', '节能率', '回收期(年)'],
            'rows': deduped_rows,
        }

    rd['chapter7'] = ch7
    return rd


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        # test mode
        test_data = [
            {'year': 2022, 'electricity_kwh': 495180, 'water_m3': 3980, 'natural_gas_m3': 3000},
            {'year': 2023, 'electricity_kwh': 521531, 'water_m3': 4441, 'natural_gas_m3': 6000},
            {'year': 2024, 'electricity_kwh': 517452, 'water_m3': 4810, 'natural_gas_m3': 3996},
        ]
        result = analyze_with_diagnosis(test_data, '测试项目')
        print(format_anomaly_report(result))
        print(format_diagnosis_for_chapter7(result))
    else:
        with open(_sys.argv[1], 'r', encoding='utf-8') as f:
            config = json.load(f)
        result = analyze_with_diagnosis(config.get('energy_yearly', []), config.get('unit_name', ''))
        print(format_anomaly_report(result))
