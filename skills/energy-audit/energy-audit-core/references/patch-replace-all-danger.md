# patch replace_all — 高危操作记录（2026-07-02）

## 场景

在 report_generator.py 中将 "表5.3"~"表5.8" 批量改为动态表号 `f"表5.{next_table+X}"`。

## 错误操作

```python
# ❌ 使用 replace_all=True，把4个不同的表标题全部替换成同一个字符串
patch(old_string='self._add_table(headers, rows, "表5.3  单位建筑面积非供暖能耗")',
      new_string='self._add_table(headers, rows, f"表5.{next_table}  单位建筑面积非供暖能耗")',
      replace_all=True)
```

## 后果

- 4个表（非供暖能耗/电耗/人均能耗/人均取水量）全部显示为"单位建筑面积非供暖能耗"
- 损失约30分钟逐个修回
- 因为 `f"表5.{next_table}  ..."` 没有区分 `next_table+1/+2/+3`

## 正确做法

**逐条替换，用唯一上下文区分**：

```python
# ✅ 每次只替换一个，用前后代码行做唯一匹配
patch(old_string='''
            rows[5].append(r['benchmark']['评价结果'] if r.get('benchmark') else '—')
        self._add_table(headers, rows, f"表5.{next_table+1}  常规用能系统单位建筑面积电耗")
        ''', new_string='...')
```

或者**直接先设变量再引用**，根本不需要 replace 操作：

```python
tbl_52 = section_num + 1   # 5.2表号
tbl_53_1 = next_table      # 5.3.1
tbl_53_2 = next_table + 1  # 5.3.2
```

## 教训

1. `replace_all=True` 只在**确实所有匹配都该替换成相同内容**时使用
2. 批量动态编号应该用 `next_table + offset` 模式，在代码生成时就传正确值
3. 受影响的代码行多于3行时，直接 `write_file` 重写整个区域更安全
