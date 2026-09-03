# Word 报告收尾三件套 + 仿写模式图表（2026-08 省立医院东院区实战）

report_generator.py 的 `generate()` 在 `doc.save()` 后自动完成三件收尾。
用户视目录/水印/页码为**必有项**，缺失会被直接质疑（"为什么还是没有目录和水印"）。

## 1. 目录自动刷新（updateFields on open）

- `build_toc()` 已写 TOC 域（`TOC \o "1-2" \h \z \u`），标题段落由
  `_add_heading_1/2/3` 设置 outlineLvl（0/1/2），域可收集到标题。
- `_set_update_fields_on_open()` 向 `word/settings.xml` 写入
  `<w:updateFields w:val="true"/>`（zip 解包→lxml 改→重打包）。
  Word/WPS 打开即自动刷新目录与页码，不再需要手动 Ctrl+A → F9。
- 占位提示文字："（目录将在 Word/WPS 打开时自动生成；若未显示请按 Ctrl+A 后 F9 更新域）"。
- 若用户仍报目录空白：让其在 Word 里 Ctrl+A → F9 一次（部分 Word 版本静默差异）。

## 2. 页眉 DrawingML 水印（2026-08 规范：禁 VML）

- 组装脚本落盘后由 `scripts/add_watermark.py` 注入（`assemble_report.py` 内部
  importlib 加载同目录脚本调用 `add_unit_name_watermark(docx, unit_name)`）。
- 形态：header 追加 DrawingML `<w:drawing><wp:anchor behindDoc="1">` + `wps:wsp`
  文本框，宋体浅灰 #C0C0C0、约 45°（`<a:xfrm rot="2700000">`）、居中衬底。
- 水印文字 = **被审计单位全称**（spec 的 `unit_name` / resolve_unit_name 结果），
  NOT 审计机构名、NOT cover.audit_organization。
- ⚠ **禁止 VML textpath**：脚本检测到页眉含 `v:textpath` 直接 raise（"禁止交付"）；
  早期实现（612×612pt rotation:315 opacity 0.5 的 VML）被 repo 规范否决，勿回退。
- 曾用 468pt/opacity 0.15 被用户批"不明显"——浅参数不再使用。
- 验证：header XML 应含 `EAWatermark` + `wps:wsp` + `behindDoc="1"`，且无 `v:textpath`。

## 3. 页脚页码（第 X 页 共 Y 页）

- `_add_page_numbers()`：footer 写入居中段落："第 " + PAGE 域 + " 页 共 "
  + NUMPAGES 域 + " 页"，10.5pt（sz=21），Times New Roman + eastAsia 宋体。
- 域结构：fldChar begin → instrText ` PAGE ` → separate → 占位 t → end。

## 4. 仿写模式图表（[[图:…]] 标记 + chart_data）

**图表不会自动生成**——正文里必须有标记行，spec 里必须有 chart_data。

### spec.json 的 chart_data 形状

```json
{
  "project_name": "<单位>",
  "audit_type": "公共机构",
  "cover": {"title": "...", "audit_organization": "..."},
  "chart_data": {
    "unit_name": "<单位>",
    "building_area": 20549.74,
    "people_count": 3405,
    "energy_types": ["electricity_kwh", "water_m3", "natural_gas_m3"],
    "years": [
      {
        "year": 2022,
        "electricity_kwh": 5090273, "water_m3": 163107.7, "natural_gas_m3": 57207,
        "monthly_electricity_kwh": [12 个值],
        "monthly_water_m3": [12 个值],
        "monthly_natural_gas_m3": [12 个值]
      },
      { 2023... }, { 2024... }
    ],
    "equipment": [{"device_name": "冷水机组", "device_num": 2, "power": 298, "category": "空调"}]
  },
  "imitated_chapters": { "第5章": "..." }
}
```

### 正文标记行

第5章正文任意位置插入一行（前后空行）：

```
[[图:flow|图5.1 能源资源流向图]]
[[图:monthly_electricity_kwh|图5.2 2022年-2024年逐月用电量（单位：kWh）]]
[[图:monthly_water_m3|图5.3 2022年-2024年逐月用水量（单位：m³）]]
[[图:monthly_natural_gas_m3|图5.4 2022年-2024年逐月天然气用量（单位：m³）]]
[[图:trend|图5.5 2022年-2024年逐年综合能耗趋势（单位：tce）]]
[[图:cost_pie|图5.6 2024年能源费用占比（单位：%）]]
```

支持类型：`flow`（graphviz 流向图）、`trend`（逐年折标柱状图）、`pie`（能源结构饼图）、
`cost_pie`（最新年费用占比，数据来自各年 `electricity_cost_wan` / `water_cost_wan` /
`natural_gas_cost_wan` / `heating_cost_wan`，万元，>0 才入图）、
`monthly_electricity_kwh` / `monthly_water_m3` / `monthly_natural_gas_m3`（逐月柱状图）。

### 渲染实现

- `_write_imitated_body` 识别 `[[图:…]]` 行 → `_render_imitated_chart()`。
- trend/pie 用 `YearlyEnergyData` 构造；cost_pie 用 `_generate_cost_pie_chart(years_data)`；
  monthly_* 用模块级 `_generate_monthly_bar_chart`；
  flow 用 `tools.energy_audit.energy_flow_chart.draw_energy_flow_diagram`。
- 输出到 `./charts/`，flow 用**时间戳文件名**（`energy_flow_<ts>.png`）避免用户已打开旧图时的文件锁。
- 缺 chart_data / matplotlib / graphviz 时静默返回 None（图缺失但不报错）——
  用户问"图表都没了"时先查这两样。

### 验证（组装后必做）

```python
import zipfile, re
with zipfile.ZipFile(p) as z:
    media = [n for n in z.namelist() if n.startswith('word/media/')]
    docxml = z.read('word/document.xml').decode('utf-8')
    caps = set(re.findall(r'图5\.\d', docxml))
    settings = z.read('word/settings.xml').decode('utf-8')
    headers = [n for n in z.namelist() if re.fullmatch(r'word/header\d+\.xml', n)]
    footers = [n for n in z.namelist() if re.fullmatch(r'word/footer\d+\.xml', n)]
    wm_ok = all('EnergyAuditWatermark' in z.read(h).decode() for h in headers)
    page_ok = all('PAGE' in z.read(f).decode() and 'NUMPAGES' in z.read(f).decode() for f in footers)
    print(len(media), len(caps), 'updateFields' in settings, wm_ok, page_ok)
```

## 5. 工具链注意

- `energy_audit_*` 工具 handler 必须 `(args, **kwargs)`——registry.dispatch 透传
  task_id/session_id/enabled_tools；缺 kwargs 时 TypeError。
- 改工具源码后当前会话旧模块仍生效：用 execute_code 直接 import 新模块验证，或重启后端。
- 测试命令：`.venv/Scripts/python.exe -m pytest tests/tools/energy_audit/ \
  tests/skills/test_energy_audit_imitate_skill.py tests/rag/test_rag_search.py -q`
  （141 passed，2026-08 状态）。
