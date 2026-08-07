"""Task 6: 重新尝试 - 修 end_pat 中的转义错误"""
import os, py_compile

file_path = "tools/energy_audit/report_generator.py"
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

EOL = chr(0x5C) + 'n'

# Sentinel: '# 共性特征' (# 共性特征)
sentinel = "            # 共性特征\n"
# End pattern: text_22 += f"各建筑{'，'.join(common_parts)}。 + EOL EOL "
end_pat = '                text_22 += f"各建筑{\'，'.__class__(chr(0xFF0C)) + chr(0x27) + '.join(common_parts)}。' + EOL + EOL + '"'

# Just use raw Chinese comma direct:
end_pat = "                text_22 += f\"各建筑{'" + chr(0xFF0C) + "'.join(common_parts)}。" + EOL + EOL + '"'

start = content.find(sentinel)
end = content.find(end_pat, start)
print(f"start={start}, end={end}")
print(f"end_pat repr tail: {end_pat[-30:]!r}")

if start >= 0 and end >= 0:
    block_old = content[start:end + len(end_pat)]
    print(f"block_old len: {len(block_old)}")

    block_lines = [
        "            # 共性特征 (扩展: 含屋面保温 / 监测 / 遮阳 / 楼层计量)",
        "            total = len(buildings)",
        "",
        "            def _rate(field, want):",
        "                cnt = sum(1 for b in buildings if b.get(field) == want)",
        "                if cnt == 0: return None",
        "                if cnt == total: return f\"全部{total}栋\"",
        "                return f\"{cnt}栋（{cnt/total*100:.0f}%）\"",
        "",
        "            structures = set(b.get('structure','') for b in buildings if b.get('structure'))",
        "            insulations = set(b.get('insulation','') for b in buildings if b.get('insulation'))",
        "            windows = set(b.get('window_type','') for b in buildings if b.get('window_type'))",
        "            sunshades = set(b.get('sunshade_type','') for b in buildings if b.get('sunshade_type'))",
        "            common_parts = []",
        "            if structures:",
        "                s = '、'.join(structures)",
        "                common_parts.append(f\"均采用{s}\" if '结构' in s else f\"均采用{s}结构\")",
        "            if insulations and '有' in str(insulations): common_parts.append(\"设有外墙保温\")",
        "            if windows and '—' not in str(windows) and '无' not in str(windows):",
        "                common_parts.append(f\"外窗采用{'、'.join(windows)}\")",
        "            # ---- 新增维度 ----",
        "            roof = _rate('roof_insulation', '有')",
        "            if roof: common_parts.append(f\"{roof}建筑设有屋面保温\")",
        "            mon = _rate('monitoring', '有')",
        "            if mon: common_parts.append(f\"{mon}建筑配备能耗在线监测系统\")",
        "            sm = _rate('storey_metrology', '是')",
        "            if sm: common_parts.append(f\"{sm}建筑实现楼层单独计量\")",
        "            if sunshades:",
        "                sun_str = '、'.join(sunshades)",
        "                common_parts.append(f\"遮阳形式为{sun_str}\")",
        "            if common_parts:",
        "                text_22 += f\"各建筑{'" + chr(0xFF0C) + "'.join(common_parts)}。" + EOL + EOL + "\"",
        "",
        "            # 面积汇总: 供冷/供热/车库",
        "            total_cool = sum(float(b.get('cooling_area') or 0) for b in buildings)",
        "            total_heat = sum(float(b.get('heating_area') or 0) for b in buildings)",
        "            total_garage = sum(float(b.get('garage_area') or 0) for b in buildings)",
        "            agg = []",
        "            if total_cool > 0: agg.append(f\"供冷面积{total_cool:g}m²\")",
        "            if total_heat > 0: agg.append(f\"供热面积{total_heat:g}m²\")",
        "            if total_garage > 0: agg.append(f\"地下车库面积{total_garage:g}m²\")",
        "            if agg:",
        "                text_22 += f\"" + EOL + EOL + "全院合计：{'" + chr(0xFF0C) + "'.join(agg)}。" + EOL + "\""
    ]
    new_block_str = "\n".join(block_lines) + "\n"

    new_content = content.replace(block_old, new_block_str)
    if len(new_content) >= 2 * len(content):
        print(f"ABORT: {len(new_content)} vs {len(content)}")
    else:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        new_size = os.path.getsize(file_path)
        print(f"OK size: {new_size} (delta {new_size - len(content)} bytes)")

try:
    py_compile.compile(file_path, doraise=True)
    print("OK Syntax")
except py_compile.PyCompileError as e:
    print(f"FAIL: {e}")
