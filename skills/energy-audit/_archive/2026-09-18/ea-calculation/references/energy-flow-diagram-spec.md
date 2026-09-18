# 能源流向图生成规范 (Graphviz)

## 原理

用 **graphviz** (dot engine) 生成三层能源流向图，替代 matplotlib 版本。

## 架构

```
能源输入(圆角矩形) → 用能系统(直角矩形) → 终端设备(直角矩形)
    实线 = 主能源流   虚线 = 辅助/间接能源流
    颜色: 电=橙/水=蓝/气=绿/热=红/汽油=琥珀/柴油=褐
```

## 动态适配

`draw_energy_flow_diagram(energy_types, equipment, unit_name)` 完全由数据驱动：

| 参数 | 影响 |
|------|------|
| energy_types | 决定源节点数量和种类 |
| equipment 列表 | 终端设备名称从 equipment.name 生成 |
| equipment 为空 | 内置默认终端兜底 |
| unit_name | 标题变化 |

## 安装

- Windows: `winget install Graphviz.Graphviz`
- macOS: `brew install graphviz`
- 代码自动将 `C:\Program Files\Graphviz\bin` 加入 PATH

## 5.1 规范

1. 一句话概述: "{unit_name}主要用能类型包括{能源列表}。"
2. 图5.1 能源流向图
3. 饼图/趋势图/结构表/对比表 → 已全部移除
