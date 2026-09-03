# ISO日期转中文格式

## 问题

Config中使用ISO格式日期 `"2022-01-01"` 直接写在Word中显示为 `2022-01-01`，不符合中文报告规范。需转为 `2022年1月1日`。

## 转换函数

```python
def _iso_to_cn(date_str: str) -> str:
    """2022-01-01 → 2022年1月1日"""
    if not date_str or '年' in date_str:
        return date_str  # 已是中文格式，跳过
    parts = date_str.split('-')
    if len(parts) >= 3:
        y, m, d = parts[0], str(int(parts[1])), str(int(parts[2]))
        return f"{y}年{m}月{d}日"
    return date_str
```

## 使用位置

- `load_from_project()`: `'audit_period': b.audit_period`、`'base_period': b.base_period`（项目表审计期/基准期，YYYY年M月-YYYY年M月）
- audit_start/end 同理（如果使用了ISO格式）

## Pitfall

- `int(parts[1])` 去掉前导零——`"01"→1→"1"` 而非 `"01"`
- 已含中文"年"的跳过（幂等性）
- 空字符串直接返回，不抛异常
