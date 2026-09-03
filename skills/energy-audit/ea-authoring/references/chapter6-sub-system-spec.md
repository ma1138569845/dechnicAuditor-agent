# 第6章 用电系统：分系统写作规范

## 结构

```
6.1 用电系统运行分析

  总述段落: "{unit}用电系统主要包括空调与供暖、照明、办公设备、其他用电设备系统等。"
  （只列系统名，不写数字）

  ### 空调与供暖系统
    - 设备描述：具体名称 + 总数量 + 分类型展开 + 功能 + 运行时间
    - ⚠️ 节能改造提示
    - 📷 设备照片（一行两张）
    - 表6.1-1 设备清单

  ### 照明系统
    同上

  ### 办公设备系统
    同上

  ### 其他用电设备
    同上

  ### 变配电系统（⚠️无数据则提示）
    - 变压器数量/型号/容量/运行年限
    - 是否节能型变压器
    - 节能改造情况

  ### 信息机房系统（⚠️无数据则提示）
    - 机房面积/机柜数量/UPS/精密空调
    - 运行时间/节能改造措施
```

## 生成规则

1. **总述段不写具体数字**：写"包括XX、XX系统等"，不写各系统设备数量
2. **H2标题不可缺失**：`_add_heading_2("6.1  用电系统运行分析")` 必须在总述之前
3. **厨房设备归类用气系统**：`kitchen_eq` 不在6.1用电系统中出现，属于6.4其他用能
4. **设备描述含运行时间**：如"每年6月至9月制冷、11月至次年3月供暖，每天约8小时"
5. **无改造信息→⚠️提示**：每个分系统标注 `⚠️ 请提供{sub_name}的节能改造情况：是否进行过节能改造、改造措施及效果`
6. **无照片→📷提示**：每个分系统标注 `📷 请提供{sub_name}照片`（不是"设备照片"，避免sub_name="其他用电设备"→"其他用电设备设备照片"双"设备"）
7. **设备表编号格式**：`表6.1-{sub_idx}  {sub_name}清单`（不是"{sub_name}设备清单"，同样避免双"设备"）。sub_idx从1递增
8. **变配电/信息机房无人提供数据→只显示⚠️提示内容，无表格无照片**
9. **照片从images_equipment取**，暂无分系统自动匹配（简化为取前2张）
10. **_handled标志模式**：分系统已在推断代码中直接生成（标题+文字+图+表），设置 `data = {'_handled': True}`。主循环检查 `_handled` 时 `section_num += 1` 后 `continue` 跳过通用渲染
11. **section_num正确递增**：即使_handled=true也要section_num+=1。分系统内部的子标题不消耗section_num
12. **代码位置**：推断逻辑在 `build_chapter6()` 的 `if key == 'cooling' and ch6.get('_equipment'):` 分支中

## 代码模板

```python
# 分系统归类
cooling_eq = [e for e in all_elec if e.get('category') == '空调']
lighting_eq = [e for e in all_elec if e.get('category') == '照明']
office_eq = [e for e in all_elec if e.get('category') == '办公']
hot_water_eq = [e for e in all_elec if e.get('category') == '热水器']
# 注意: kitchen_eq 不属于用电系统

subsystems = []
if cooling_eq:
    subsystems.append(('空调与供暖系统', cooling_eq, f"...共{sum(qty)}台，..."))
# ... 其他系统
subsystems.append(('变配电系统', [], f"⚠️ 请提供变配电系统信息：..."))
subsystems.append(('信息机房系统', [], f"⚠️ 请提供信息机房系统信息：..."))

# 标题 + 总述
self._add_heading_2("6.1  用电系统运行分析")
self._add_body_text(f"{unit}用电系统主要包括{names}系统等。")

# 逐个子系统
sub_idx = 1
for sub_name, sub_eq, sub_text in subsystems:
    self._add_heading_3(sub_name)
    if sub_eq:
        self._add_body_text(sub_text)
        self._add_body_text(f"⚠️ 请提供{sub_name}的节能改造情况：...")
        # 照片
        sub_photos = equip_images[:2] if equip_images else []
        for img in sub_photos: self._add_image(img, width_cm=6.5)
        if not sub_photos: self._add_body_text(f"📷 请提供{sub_name}照片。")
        # 表
        eq_for_table = [{'name':...} for e in sub_eq]
        self._add_equipment_table(eq_for_table, f"表6.1-{sub_idx}  {sub_name}清单")
        sub_idx += 1
    else:
        self._add_body_text(sub_text)

data = {'_handled': True}
```
