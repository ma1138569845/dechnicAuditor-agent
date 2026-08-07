"""应用 Tasks 4+5+6 - 一次性完成 (临时脚本，运行后可删)"""
import os, py_compile

file_path = "tools/energy_audit/report_generator.py"
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

orig_size = os.path.getsize(file_path)
EOL = chr(0x5C) + 'n'  # literal backslash+n in source

# ============ Task 4: Building Param Table ============
table_old = (
    "            [\"生活热水系统\", bldg.get('hot_water', ''), \"能耗在线监测系统\", bldg.get('monitoring', '')],\n"
    "        ]"
)
table_new = (
    "            [\"生活热水系统\", bldg.get('hot_water', ''), \"能耗在线监测系统\", bldg.get('monitoring', '')],\n"
    "            # ============ Part B: 扩展信息 (新增字段) ============\n"
    "            [\"使用面积\", str(bldg.get('use_area', '')) + ('m\u00b2' if bldg.get('use_area') else ''),\n"
    "             \"供冷面积\", str(bldg.get('cooling_area', '')) + ('m\u00b2' if bldg.get('cooling_area') else '')],\n"
    "            [\"供热面积\", str(bldg.get('heating_area', '')) + ('m\u00b2' if bldg.get('heating_area') else ''),\n"
    "             \"外墙主体材料\", bldg.get('wall_body_material', '')],\n"
    "            [\"屋面保温\", bldg.get('roof_insulation', ''),\n"
    "             \"屋面保温材料\", bldg.get('roof_insulation_material', '')],\n"
    "            [\"遮阳形式\", bldg.get('sunshade_type', ''),\n"
    "             \"遮阳材料\", bldg.get('sunshade_material', '')],\n"
    "            [\"建筑运行时间\", bldg.get('run_time', ''),\n"
    "             \"楼层单独计量\", bldg.get('storey_metrology', '')],\n"
    "            [\"地下车库\", bldg.get('garage', ''),\n"
    "             \"地下车库面积\", str(bldg.get('garage_area', '')) + ('m\u00b2' if bldg.get('garage_area') else '')],\n"
    "        ]"
)

if content.count(table_old) == 1:
    content = content.replace(table_old, table_new)
    print("OK Task 4: table part B added")
else:
    print(f"WARN Task 4 count={content.count(table_old)}")

# ============ Task 5: Per-building prose ============
prose_old = "\n".join([
    "                if b.get('structure'):",
    "                    st = b.get('structure')",
    "                    parts.append(st if '\u7ed3\u6784' in st else f'{st}\u7ed3\u6784')",
    f"                text_22 += '\uff0c'.join(parts) + \"\u3002{EOL}\""
])

prose_new = "\n".join([
    "                if b.get('structure'):",
    "                    st = b.get('structure')",
    "                    parts.append(st if '\u7ed3\u6784' in st else f'{st}\u7ed3\u6784')",
    "                # ---- \u65b0\u589e\u5b57\u6bb5 (\u53ef\u9009\uff0c\u907f\u514d\u7a7a\u503c\u566a\u97f3) ----",
    "                if b.get('orientation'): parts.append(f\"\u671d{b.get('orientation')}\")",
    "                cooling_area = b.get('cooling_area') or 0",
    "                heating_area = b.get('heating_area') or 0",
    "                if cooling_area and float(cooling_area) > 0:",
    "                    parts.append(f\"\u4f9b\u51b7\u9762\u79ef{float(cooling_area):g}m\u00b2\")",
    "                if heating_area and float(heating_area) > 0:",
    "                    parts.append(f\"\u4f9b\u70ed\u9762\u79ef{float(heating_area):g}m\u00b2\")",
    "                if b.get('roof_insulation') == '\u6709':",
    "                    mat = b.get('roof_insulation_material', '')",
    "                    parts.append(f\"\u5c4b\u9762\u4fdd\u6e29\uff08{mat}\uff09\" if mat else \"\u8bbe\u6709\u5c4b\u9762\u4fdd\u6e29\")",
    "                if b.get('sunshade_type'):",
    "                    parts.append(f\"\u91c7\u7528{b.get('sunshade_type')}\")",
    "                if b.get('run_time'):",
    "                    parts.append(f\"\u8fd0\u884c\u65f6\u95f4\u4e3a{b.get('run_time')}\")",
    "                if b.get('monitoring') == '\u6709':",
    "                    parts.append(\"\u914d\u5907\u80fd\u8017\u5728\u7ebf\u76d1\u6d4b\u7cfb\u7edf\")",
    f"                text_22 += '\uff0c'.join(parts) + \"\u3002{EOL}\""
])

if content.count(prose_old) == 1:
    content = content.replace(prose_old, prose_new)
    print("OK Task 5: prose part B added")
else:
    print(f"WARN Task 5 count={content.count(prose_old)}")

# ============ Task 6: Common features ============
sentinel = "            # \u5171\u6027\u7279\u5f81\n"
end_pat_str = "                text_22 += f\"\u5404\u5efa\u7b51{'\\u201c\\uff0c'.join(common_parts)}\u3002"
end_pat = end_pat_str + EOL + EOL + '"'

start = content.find(sentinel)
end = content.find(end_pat, start)
if start >= 0 and end >= 0:
    block_old = content[start:end+len(end_pat)]

    block_lines = [
        "            # \u5171\u6027\u7279\u5f81 (\u6269\u5c55: \u542b\u5c4b\u9762\u4fdd\u6e29 / \u76d1\u6d4b / \u906e\u9633 / \u697c\u5c42\u8ba1\u91cf)",
        "            total = len(buildings)",
        "",
        "            def _rate(field, want):",
        "                cnt = sum(1 for b in buildings if b.get(field) == want)",
        "                if cnt == 0: return None",
        "                if cnt == total: return f\"\u5168\u90e8{total}\u680b\"",
        "                return f\"{cnt}\u680b\uff08{cnt/total*100:.0f}%\uff09\"",
        "",
        "            structures = set(b.get('structure','') for b in buildings if b.get('structure'))",
        "            insulations = set(b.get('insulation','') for b in buildings if b.get('insulation'))",
        "            windows = set(b.get('window_type','') for b in buildings if b.get('window_type'))",
        "            sunshades = set(b.get('sunshade_type','') for b in buildings if b.get('sunshade_type'))",
        "            common_parts = []",
        "            if structures:",
        "                s = '\u3001'.join(structures)",
        "                common_parts.append(f\"\u5747\u91c7\u7528{s}\" if '\u7ed3\u6784' in s else f\"\u5747\u91c7\u7528{s}\u7ed3\u6784\")",
        "            if insulations and '\u6709' in str(insulations): common_parts.append(\"\u8bbe\u6709\u5916\u5899\u4fdd\u6e29\")",
        "            if windows and '\u2014' not in str(windows) and '\u65e0' not in str(windows):",
        "                common_parts.append(f\"\u5916\u7a97\u91c7\u7528{'\u3001'.join(windows)}\")",
        "            # ---- \u65b0\u589e\u7ef4\u5ea6 ----",
        "            roof = _rate('roof_insulation', '\u6709')",
        "            if roof: common_parts.append(f\"{roof}\u5efa\u7b51\u8bbe\u6709\u5c4b\u9762\u4fdd\u6e29\")",
        "            mon = _rate('monitoring', '\u6709')",
        "            if mon: common_parts.append(f\"{mon}\u5efa\u7b51\u914d\u5907\u80fd\u8017\u5728\u7ebf\u76d1\u6d4b\u7cfb\u7edf\")",
        "            sm = _rate('storey_metrology', '\u662f')",
        "            if sm: common_parts.append(f\"{sm}\u5efa\u7b51\u5b9e\u73b0\u697c\u5c42\u5355\u72ec\u8ba1\u91cf\")",
        "            if sunshades:",
        "                sun_str = '\u3001'.join(sunshades)",
        "                common_parts.append(f\"\u906e\u9633\u5f62\u5f0f\u4e3a{sun_str}\")",
        "            if common_parts:",
        f"                text_22 += f\"\u5404\u5efa\u7b51{{'\\uff0c'.join(common_parts)}}\u3002{EOL}{EOL}\"",
        "",
        "            # \u9762\u79ef\u6c47\u603b: \u4f9b\u51b7/\u4f9b\u70ed/\u8f66\u5e93",
        "            total_cool = sum(float(b.get('cooling_area') or 0) for b in buildings)",
        "            total_heat = sum(float(b.get('heating_area') or 0) for b in buildings)",
        "            total_garage = sum(float(b.get('garage_area') or 0) for b in buildings)",
        "            agg = []",
        "            if total_cool > 0: agg.append(f\"\u4f9b\u51b7\u9762\u79ef{total_cool:g}m\u00b2\")",
        "            if total_heat > 0: agg.append(f\"\u4f9b\u70ed\u9762\u79ef{total_heat:g}m\u00b2\")",
        "            if total_garage > 0: agg.append(f\"\u5730\u4e0b\u8f66\u5e93\u9762\u79ef{total_garage:g}m\u00b2\")",
        "            if agg:",
        f"                text_22 += f\"{EOL}{EOL}\u5168\u9662\u5408\u8ba1\uff1a{{'\\uff0c'.join(agg)}}\u3002{EOL}\""
    ]
    new_block_str = "\n".join(block_lines) + "\n"

    new_content = content.replace(block_old, new_block_str)
    if len(new_content) >= 2 * len(content):
        print(f"ABORT: {len(new_content)} vs {len(content)}")
    else:
        content = new_content
        print("OK Task 6: common features extended")
else:
    print(f"WARN Task 6 sentinel not found (start={start}, end={end})")

# Write
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

new_size = os.path.getsize(file_path)
ratio = new_size / orig_size
print(f"\nFinal size: {new_size} bytes (ratio {ratio:.2f}x)")

try:
    py_compile.compile(file_path, doraise=True)
    print("OK Syntax")
except py_compile.PyCompileError as e:
    print(f"FAIL: {e}")