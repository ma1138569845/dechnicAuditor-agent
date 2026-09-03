# 建筑参数表字段规范 (v2.0)

每栋建筑生成一张10行×4列的键值对参数表，标题在表格上方（不在表内合并单元格）。

## 10行字段（按顺序）

| 行 | 字段1 | 字段2 |
|----|-------|-------|
| 1 | 建筑物名称 | 建筑地址 |
| 2 | 建造年代 | 建筑功能 |
| 3 | 建筑层数及朝向 | 建筑面积 |
| 4 | 建筑功能分区 | 建筑结构形式 |
| 5 | 建筑外窗类型 | 建筑外墙保温 |
| 6 | 夏季空调冷源 | 冬季供暖热源 |
| 7 | 夏季空调末端形式 | 冬季供暖末端形式 |
| 8 | 建筑给水系统 | 建筑消防给水系统 |
| 9 | 生活热水系统 | 能耗在线监测系统 |
| 10 | 其他 | — |

## 数据来源

从 `BuildingInfo` dataclass 读取，字段映射：
- name → 建筑物名称
- address → 建筑地址
- year → 建造年代
- function → 建筑功能
- floors → 建筑层数
- area → 建筑面积
- function_zoning → 建筑功能分区
- structure → 建筑结构形式
- window_type → 建筑外窗类型
- insulation → 建筑外墙保温
- cooling_source → 夏季空调冷源
- heating_source → 冬季供暖热源
- cooling_terminal → 夏季空调末端形式
- heating_terminal → 冬季供暖末端形式
- water_system → 建筑给水系统
- fire_system → 建筑消防给水系统（增补字段，不可省略）
- hot_water → 生活热水系统
- monitoring → 能耗在线监测系统

## 代码实现

```python
def _add_building_param_table(self, bldg: dict, table_num: int):
    name = bldg.get('name', '')
    title = f"表2-{table_num}  {name}基本信息"
    # 标题在表格上方
    self._add_table_title(title)  # 独立行，非合并在表内第一行
    
    pairs = [
        ('建筑物名称', name, '建筑地址', bldg.get('address','')),
        ('建造年代', bldg.get('year',''), '建筑功能', bldg.get('function','')),
        ('建筑层数及朝向', bldg.get('floors',''), '建筑面积', area_str),
        ...
    ]
    
    headers = ['项目','内容','项目','内容']
    rows = [['','','',''] for _ in range(len(pairs))]
    for i, (k1, v1, k2, v2) in enumerate(pairs):
        rows[i][0]=k1; rows[i][1]=str(v1); rows[i][2]=k2; rows[i][3]=str(v2)
    
    self._add_table(headers, rows, title=None)  # title=None 因为标题已在表外
```

## 关键 Pitfall

- **标题不入表**: 必须用 `_add_table_title()` + `_add_table(title=None)`，不可合并单元格做标题行
- **空值处理**: 空字符串显示空，不可补"—"（除非确实"无"）
- **面积格式**: `f"{area}㎡"` 或 `f"{area:.0f}平方米"`，带单位，不可裸数字
- **层数格式**: "地上X层" 或 "地下Y层/地上X层"
