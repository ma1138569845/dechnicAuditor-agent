"""
能源审计知识图谱可视化

用法:
    from rag.knowledge_graph.kg_visualizer import visualize_kg, visualize_system

    kg = create_default_kg()
    visualize_kg(kg, "output/kg_full")          # 全图谱 → kg_full.png
    visualize_system(kg, "中央空调系统", "output/hvac")  # 单系统 → hvac.png

作者: 马天远 | 版本: 1.0.0 | 日期: 2026-07-14
"""

import os, sys
from pathlib import Path
from typing import Optional, List

import graphviz

# ---- 自动探测 Graphviz 可执行文件路径 ----

def _ensure_graphviz_path():
    """探测并注册 Graphviz bin 目录到 PATH"""
    # 常见安装路径
    candidates = [
        r'C:\Program Files\Graphviz\bin',
        r'C:\Program Files (x86)\Graphviz\bin',
        '/usr/bin',
        '/usr/local/bin',
    ]
    # 环境变量
    env_home = os.environ.get('GRAPHVIS_HOME', '')
    if env_home:
        candidates.insert(0, os.path.join(env_home, 'bin'))
        candidates.insert(0, env_home)

    for cand in candidates:
        dot_path = os.path.join(cand, 'dot.exe' if sys.platform == 'win32' else 'dot')
        if os.path.exists(dot_path):
            if cand not in os.environ.get('PATH', ''):
                os.environ['PATH'] = cand + os.pathsep + os.environ.get('PATH', '')
            return cand
    return None

_ensure_graphviz_path()

# ============================================================
# 配色方案
# ============================================================

COLORS = {
    'anomaly': {'fill': '#FF6B6B', 'font': '#8B0000', 'border': '#CC0000', 'shape': 'box'},
    'cause':   {'fill': '#FFB347', 'font': '#8B4513', 'border': '#CC7000', 'shape': 'ellipse'},
    'measure': {'fill': '#77DD77', 'font': '#006400', 'border': '#228B22', 'shape': 'note'},
    'system':  {'fill': '#AEC6CF', 'font': '#2F4F4F', 'border': '#5F9EA0', 'shape': 'folder'},
    'edge_cause':   '#CC7000',
    'edge_measure': '#228B22',
    'edge_related': '#999999',
    'bg':      '#1A1A2E',
}

# 节点标签最大长度
MAX_LABEL_LEN = 25


def _short(s: str, maxlen: int = MAX_LABEL_LEN) -> str:
    """截断过长标签"""
    return s if len(s) <= maxlen else s[:maxlen-2] + '…'


def visualize_kg(kg, output_path: str = "kg_full", fmt: str = "png",
                 max_nodes: int = 200, rankdir: str = "LR") -> str:
    """
    可视化完整知识图谱。

    Args:
        kg: EnergyKnowledgeGraph 实例
        output_path: 输出文件路径（不含扩展名）
        fmt: 输出格式 (png/svg/pdf)
        max_nodes: 最大节点数（防止图谱过大）
        rankdir: 布局方向 LR(左→右) / TB(上→下)

    Returns:
        输出文件完整路径
    """
    dot = graphviz.Digraph(
        name='energy_audit_kg',
        format=fmt,
        engine='dot',
    )
    dot.attr(
        rankdir=rankdir,
        bgcolor=COLORS['bg'],
        fontname='SimHei',
        fontsize='10',
        label=f'能源审计因果知识图谱 ({len(kg.chains)}条因果链)',
        labelloc='t',
        fontcolor='#FFFFFF',
        nodesep='0.5',
        ranksep='1.0',
    )

    # 按系统分组（子图）
    system_chains = {}
    for chain in kg.chains:
        sys = chain.system or '其他'
        system_chains.setdefault(sys, []).append(chain)

    node_count = 0
    for sys_name, chains in system_chains.items():
        if node_count >= max_nodes:
            break

        with dot.subgraph(name=f'cluster_{sys_name}') as sub:
            sub.attr(
                label=sys_name,
                style='filled',
                fillcolor='#2A2A3E',
                fontcolor='#FFFFFF',
                fontname='SimHei',
                fontsize='11',
            )

            for chain in chains:
                if node_count >= max_nodes:
                    break

                # 异常节点
                a_id = f"a_{hash(chain.anomaly_description) % 100000}"
                a_label = _short(chain.anomaly_description)
                sub.node(a_id, a_label,
                         shape=COLORS['anomaly']['shape'],
                         style='filled',
                         fillcolor=COLORS['anomaly']['fill'],
                         fontcolor=COLORS['anomaly']['font'],
                         color=COLORS['anomaly']['border'],
                         fontname='SimHei', fontsize='10')
                node_count += 1

                # 原因节点（最多3个）
                for cause in chain.causes[:3]:
                    c_id = f"c_{hash(cause.label) % 100000}"
                    c_label = _short(cause.label)
                    sub.node(c_id, c_label,
                             shape=COLORS['cause']['shape'],
                             style='filled',
                             fillcolor=COLORS['cause']['fill'],
                             fontcolor=COLORS['cause']['font'],
                             color=COLORS['cause']['border'],
                             fontname='SimHei', fontsize='9')
                    node_count += 1

                    # 异常→原因边（标注概率）
                    sub.edge(a_id, c_id,
                            label=f'{cause.probability:.0%}',
                            color=COLORS['edge_cause'],
                            fontcolor=COLORS['edge_cause'],
                            fontsize='8')

                    # 措施节点（最多2个/原因）
                    for measure in chain.measures[:2]:
                        m_id = f"m_{hash(measure.label) % 100000}"
                        m_label = _short(measure.label)
                        # 去重
                        sub.node(m_id, m_label,
                                 shape=COLORS['measure']['shape'],
                                 style='filled',
                                 fillcolor=COLORS['measure']['fill'],
                                 fontcolor=COLORS['measure']['font'],
                                 color=COLORS['measure']['border'],
                                 fontname='SimHei', fontsize='8')
                        node_count += 1

                        sub.edge(c_id, m_id,
                                label=_short(measure.estimated_saving_rate, 12) if measure.estimated_saving_rate else '',
                                color=COLORS['edge_measure'],
                                fontcolor=COLORS['edge_measure'],
                                fontsize='7')

    out_path = dot.render(output_path, cleanup=True)
    if os.path.exists(out_path):
        size_kb = os.path.getsize(out_path) / 1024
        print(f"[可视化] 全图谱: {out_path} ({size_kb:.0f}KB, {node_count}节点)")
    return out_path


def visualize_system(kg, system: str, output_path: str, fmt: str = "png") -> str:
    """
    可视化单个系统的因果链（适合嵌入报告章节）。

    Args:
        kg: EnergyKnowledgeGraph 实例
        system: 系统名称（如 '中央空调系统'）
        output_path: 输出路径（不含扩展名）
        fmt: 格式

    Returns:
        输出文件路径
    """
    chains = [c for c in kg.chains if c.system == system]
    if not chains:
        print(f"[可视化] 未找到系统 '{system}' 的因果链")
        return ""

    dot = graphviz.Digraph(
        name=f'kg_{system}',
        format=fmt,
        engine='dot',
    )
    dot.attr(
        rankdir='TB',
        bgcolor='#FFFFFF',
        fontname='SimHei',
        fontsize='12',
        label=f'{system} — 能耗异常诊断图谱',
        labelloc='t',
        fontcolor='#333333',
        nodesep='0.4',
        ranksep='0.8',
    )

    for chain in chains:
        a_id = f"a_{hash(chain.anomaly_description) % 100000}"
        dot.node(a_id, chain.anomaly_description,
                 shape='box', style='filled',
                 fillcolor='#FFF0F0', fontcolor='#8B0000',
                 color='#CC0000', fontname='SimHei', fontsize='10')

        for cause in chain.causes[:3]:
            c_id = f"c_{hash(cause.label) % 100000}"
            dot.node(c_id, cause.label,
                     shape='ellipse', style='filled',
                     fillcolor='#FFF8E7', fontcolor='#8B4513',
                     color='#CC7000', fontname='SimHei', fontsize='9')
            dot.edge(a_id, c_id,
                    label=f'{cause.probability:.0%}',
                    color='#CC7000', fontcolor='#CC7000', fontsize='8')

            for measure in chain.measures[:2]:
                m_id = f"m_{hash(measure.label) % 100000}"
                dot.node(m_id, measure.label,
                         shape='note', style='filled',
                         fillcolor='#E8F5E9', fontcolor='#006400',
                         color='#228B22', fontname='SimHei', fontsize='8')
                dot.edge(c_id, m_id,
                        color='#228B22', fontsize='7')

    out_path = dot.render(output_path, cleanup=True)
    if os.path.exists(out_path):
        size_kb = os.path.getsize(out_path) / 1024
        print(f"[可视化] {system}: {out_path} ({size_kb:.0f}KB)")
    return out_path


def visualize_diagnosis(kg, anomaly_description: str, energy_type: str = "",
                        output_path: str = "diagnosis", fmt: str = "png") -> str:
    """
    可视化单条诊断结果：异常→原因→措施 的高亮路径。

    适合在用户确认异常时展示推理过程。
    """
    result = kg.diagnose(anomaly_description, energy_type=energy_type)
    if not result.has_diagnosis:
        print(f"[可视化] 未匹配到诊断: {anomaly_description}")
        return ""

    dot = graphviz.Digraph(name='diagnosis', format=fmt, engine='dot')
    dot.attr(rankdir='TB', bgcolor='#FFFFFF', fontname='SimHei',
             label=f'诊断推理: {_short(anomaly_description, 40)}',
             fontsize='11', labelloc='t')

    chain = result.matched_chains[0]

    a_id = 'anomaly'
    dot.node(a_id, anomaly_description[:40],
             shape='box', style='filled',
             fillcolor='#FFE0E0', fontcolor='#8B0000',
             color='#CC0000', fontname='SimHei', fontsize='11')

    for i, cause in enumerate(chain.causes[:3]):
        c_id = f'cause_{i}'
        highlight = (result.primary_cause and cause.label == result.primary_cause.label)
        dot.node(c_id, cause.label,
                 shape='ellipse', style='filled',
                 fillcolor='#FFD700' if highlight else '#FFF8E7',
                 fontcolor='#8B4513',
                 color='#CC7000', fontname='SimHei',
                 fontsize='10' if not highlight else '11',
                 penwidth='3' if highlight else '1')
        dot.edge(a_id, c_id,
                label=f'{cause.probability:.0%}',
                color='#CC7000', fontcolor='#CC7000',
                penwidth='2' if highlight else '1')

        for j, measure in enumerate(result.recommended_measures[:2]):
            m_id = f'measure_{i}_{j}'
            dot.node(m_id, _short(measure.label, 20),
                     shape='note', style='filled',
                     fillcolor='#E8F5E9', fontcolor='#006400',
                     color='#228B22', fontname='SimHei', fontsize='9')
            dot.edge(c_id, m_id, color='#228B22', style='dashed')

    out_path = dot.render(output_path, cleanup=True)
    if os.path.exists(out_path):
        print(f"[可视化] 诊断图: {out_path}")
    return out_path


def visualize_all_systems(kg, output_dir: str = "output/systems", fmt: str = "png") -> List[str]:
    """
    为每个系统生成独立的诊断图谱。
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for system in sorted(set(c.system for c in kg.chains)):
        safe_name = system.replace('/', '_').replace(' ', '_')
        path = visualize_system(kg, system, f'{output_dir}/{safe_name}', fmt=fmt)
        if path:
            paths.append(path)
    return paths


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    # sys.path no longer needed; use absolute package imports

    from rag.knowledge_graph.energy_kg import create_default_kg

    kg = create_default_kg()
    out = "output/kg"

    if len(sys.argv) > 1:
        # 单系统模式
        system = sys.argv[1]
        visualize_system(kg, system, f"output/{system.replace(' ','_')}")
    else:
        # 全图谱 + 所有系统 + 示例诊断
        visualize_kg(kg, f"{out}/kg_full")
        visualize_all_systems(kg, f"{out}/systems")
        visualize_diagnosis(kg, "冷机COP偏低，实测4.2", energy_type="电",
                           output_path=f"{out}/diagnosis_cop")
        print("\n✅ 全部图谱生成完成")
