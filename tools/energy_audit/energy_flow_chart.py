"""
能源流向图 — Graphviz 动态版本
根据实际用能类型 + 设备清单，自动生成三层流向图
"""
import graphviz
import os
import platform
from typing import List, Dict, Optional


# 能源类型 → 颜色
_SRC_STYLE = {
    'electricity_kwh': ('电力', '#FFF3CD', '#FFC107', '#E65100'),       # 名称, 填充色, 边框色, 箭头色
    'water_m3':        ('水',   '#D1ECF1', '#0D6EFD', '#1565C0'),
    'natural_gas_m3':  ('天然气','#D4EDDA', '#28A745', '#2E7D32'),
    'heating_energy_heat_gj': ('市政供暖','#FFE0E0','#C62828','#C62828'),
    'petrol_kg':       ('汽油', '#FFF8E1', '#FF8F00', '#FF8F00'),
    'diesel_kg':       ('柴油', '#EFEBE9', '#5D4037', '#5D4037'),
}

# 能源 → 它驱动的系统
_ENERGY_TO_SYSTEMS = {
    'electricity_kwh': ['照明插座系统', '空调系统', '办公设备系统'],
    'water_m3':        ['用水系统'],  # 还以虚线供给空调
    'natural_gas_m3':  ['厨房系统'],
    'heating_energy_heat_gj': ['供暖系统'],
    'petrol_kg':       ['公务用车'],
    'diesel_kg':       ['公务用车'],
}

# 设备类别 → 所属系统
_CATEGORY_SYSTEM = {
    '空调':   '空调系统',
    '照明':   '照明插座系统',
    '办公':   '办公设备系统',
    '热水器': '照明插座系统',  # 电热水器归照明插座
    '厨房':   '厨房系统',
}

_SYS_COLORS = {
    '照明插座系统': ('#D4EDDA', '#28A745'),
    '空调系统':     ('#D4EDDA', '#28A745'),
    '办公设备系统':  ('#D4EDDA', '#28A745'),
    '用水系统':     ('#D1ECF1', '#0D6EFD'),
    '厨房系统':     ('#D4EDDA', '#28A745'),
    '供暖系统':     ('#FFE0E0', '#C62828'),
    '公务用车':     ('#EFEBE9', '#5D4037'),
}


def draw_energy_flow_diagram(
    energy_types: List[str],
    equipment: Optional[List[Dict]] = None,
    unit_name: str = '',
    output_path: str = 'charts/energy_flow',
) -> str:
    """
    动态生成能源流向图。
    无设备清单时使用内置默认终端设备。
    无能源类型时返回空字符串。
    """
    # 确保 graphviz 可执行文件在 PATH 中（Windows 常见路径）
    import platform
    if platform.system() == 'Windows':
        for gv_path in [r'C:\Program Files\Graphviz\bin', r'C:\Program Files (x86)\Graphviz\bin']:
            if os.path.isdir(gv_path) and gv_path not in os.environ.get('PATH', ''):
                os.environ['PATH'] = gv_path + os.pathsep + os.environ.get('PATH', '')
                break
    output_base = output_path.rsplit('.', 1)[0] if '.' in output_path else output_path
    png_path = output_base + '.png'
    equipment = equipment or []

    dot = graphviz.Digraph(name='energy_flow', format='png', engine='dot')
    dot.attr(rankdir='LR', splines='polyline', nodesep='0.5', ranksep='1.0', dpi='200', fontname='SimHei')
    dot.attr('node', fontname='SimHei', fontsize='11', shape='box', style='filled')
    dot.attr('edge', fontname='SimHei', fontsize='9')

    # ========== 1. 收集实际存在的能源源 ==========
    actual_src = {k: _SRC_STYLE[k] for k in energy_types if k in _SRC_STYLE}

    # ========== 2. 根据能源类型推断驱动的系统 ==========
    active_systems = {}
    for et in energy_types:
        if et in _ENERGY_TO_SYSTEMS:
            for sys_name in _ENERGY_TO_SYSTEMS[et]:
                sid = 'sys_' + sys_name.replace(' ', '_')
                fc, ec = _SYS_COLORS.get(sys_name, ('#F0F0F0', '#999'))
                active_systems[sid] = (sys_name, fc, ec)

    # ========== 3. 根据设备清单生成终端设备节点 ==========
    terminals = {}
    for eq in equipment:
        cat = eq.get('category', '')
        sys_name = _CATEGORY_SYSTEM.get(cat)
        if sys_name:
            eq_name = eq.get('name', '')
            qty = eq.get('quantity', 0)
            label = f"{eq_name}{qty}台" if qty else eq_name
            terminals[f'term_{cat}_{len(terminals)}'] = label

    # 确保基础终端存在（无设备清单时兜底）
    if not any(t for t in terminals):
        _defaults = {
            '空调': ['风冷冷水机组', '分体式空调'],
            '照明': ['灯具照明', '办公设备'],
            '厨房': ['厨房灶具', '燃气设备'],
        }
        for cat, names in _defaults.items():
            for name in names:
                terminals[f'term_{cat}_{name}'] = name

    # ========== 4. 画节点 ==========
    for key, (name, fc, ec, _) in actual_src.items():
        dot.node(key, name, shape='box', style='filled,rounded', fillcolor=fc, color=ec,
                 fontcolor='#333', penwidth='1.5')

    for sid, (sname, fc, ec) in active_systems.items():
        dot.node(sid, sname, fillcolor=fc, color=ec, fontcolor='#333', penwidth='1.5')

    for tid, tname in terminals.items():
        dot.node(tid, tname, fillcolor='#F8F9FA', color='#6C757D', fontcolor='#333',
                 fontsize='9', penwidth='1.0')

    # ========== 5. 连线 ==========
    # 电力→照明/空调/办公
    if 'electricity_kwh' in actual_src:
        for sn in ['照明插座系统', '空调系统', '办公设备系统']:
            sid = 'sys_' + sn.replace(' ', '_')
            if sid in active_systems:
                dot.edge('electricity_kwh', sid, style='solid', color='#E65100', penwidth='1.5')

    # 水→用水(实线) + 水→空调(虚线)
    if 'water_m3' in actual_src:
        sid_water = 'sys_用水系统'
        sid_ac = 'sys_空调系统'
        if sid_water in active_systems:
            dot.edge('water_m3', sid_water, style='solid', color='#1565C0', penwidth='1.5')
        if sid_ac in active_systems:
            dot.edge('water_m3', sid_ac, style='dashed', color='#1565C0', penwidth='1.0')

    # 天然气→厨房
    if 'natural_gas_m3' in actual_src:
        sid = 'sys_厨房系统'
        if sid in active_systems:
            dot.edge('natural_gas_m3', sid, style='solid', color='#2E7D32', penwidth='1.5')

    # 供暖→供暖系统
    if 'heating_energy_heat_gj' in actual_src:
        sid = 'sys_供暖系统'
        if sid in active_systems:
            dot.edge('heating_energy_heat_gj', sid, style='solid', color='#C62828', penwidth='1.5')

    # 汽/柴油→公务用车
    for oil in ['petrol_kg', 'diesel_kg']:
        if oil in actual_src:
            sid = 'sys_公务用车'
            if sid in active_systems:
                arrow_color = _SRC_STYLE[oil][3]
                dot.edge(oil, sid, style='solid', color=arrow_color, penwidth='1.5')

    # 系统→终端设备：按设备类别匹配
    cat_to_sys_nodes = {}  # category → [term_node_ids]
    for tid in terminals:
        cat = tid.split('_')[1]  # 'term_空调_xxx' → '空调'
        cat_to_sys_nodes.setdefault(cat, []).append(tid)

    for cat, term_ids in cat_to_sys_nodes.items():
        sys_name = _CATEGORY_SYSTEM.get(cat)
        if sys_name:
            sid = 'sys_' + sys_name.replace(' ', '_')
            if sid in active_systems:
                for tid in term_ids:
                    dot.edge(sid, tid, style='solid', color='#888', penwidth='1.0')

    # ========== 6. 层级分组 ==========
    with dot.subgraph(name='cluster_input') as c:
        c.attr(label='能源输入', style='dashed', color='#AAA', fontname='SimHei', fontsize='10')
        for key in actual_src:
            c.node(key)

    with dot.subgraph(name='cluster_systems') as c:
        c.attr(label='用能系统', style='dashed', color='#AAA', fontname='SimHei', fontsize='10')
        for sid in active_systems:
            c.node(sid)

    with dot.subgraph(name='cluster_terminals') as c:
        c.attr(label='终端设备', style='dashed', color='#AAA', fontname='SimHei', fontsize='10')
        for tid in terminals:
            c.node(tid)

    # ========== 7. 标题 ==========
    title = f"{unit_name + '能源流向图' if unit_name else '能源流向图'}"
    dot.attr(label=title, fontsize='16', fontname='SimHei', labelloc='t')

    # 生成
    os.makedirs(os.path.dirname(os.path.abspath(output_base)), exist_ok=True)
    dot.render(output_base, cleanup=True)

    if os.path.exists(png_path):
        print(f'[流向图] {png_path}')
    return png_path


if __name__ == '__main__':
    draw_energy_flow_diagram(
        energy_types=['electricity_kwh', 'water_m3', 'natural_gas_m3'],
        equipment=[
            {'name': '中央空调','category': '空调','quantity': 6},
            {'name': '柜机','category': '空调','quantity': 20},
            {'name': '照明灯具','category': '照明','quantity': 432},
            {'name': '打印机','category': '办公','quantity': 1},
            {'name': '厨房炉灶','category': '厨房','quantity': 11},
        ],
        unit_name='莘县县政府',
    )
    print('Done')
