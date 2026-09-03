# 第6.5章 室内环境检测 — 自动生成说明

build_chapter6() 在 for 循环后检查 `ch6.indoor_env` 数据：

```
indoor_env:
  test_date: "2025年6月15日"        # 可选
  test_conditions: "空调运行工况"    # 可选
  rooms:                            # 可选，无数据时跳过
    - name: "办公室301"
      temp: 26.3       # ℃
      humidity: 52.5   # %RH
      co2: 650         # ppm
      illumination: 320 # lx
      wind_speed: 0.08 # m/s
      voc: 0.35        # mg/m³
      pm25: 45         # μg/m³
```

生成内容：
1. 概述段（检测时间 + 条件）
2. 表 室内环境检测结果（8列：位置/温度/湿度/CO2/照度/风速/VOC/PM2.5）
3. 表 照明标准参考值（GB 50034-2024）
4. 表 室内空气质量标准参考值（GB/T 18883-2022）

无数据时整节跳过。检测结果表只有当 rooms 不为空时才生成。
标准对照表始终生成（即便没有检测数据，也可作为填写模板提示）。
