# Config JSON 格式规范

## 文件名

`config_<项目简称>.json`

## 必填字段

```json
{
  "unit_name": "莘县县政府",
  "institution_category": "党政机关",
  "building_area": 4190,
  "people_count": 300,
  "audit_start": "2025年6月",
  "audit_end": "2025年7月"
}
```

## 完整模板

```json
{
  "unit_name": "", "unit_short": "",
  "address": "", "unit_type": "公共机构",
  "institution_category": "", "specific_type": "",
  "contact_person": "", "contact_phone": "",
  "auditor": "同方德诚（山东）科技股份公司",
  "report_date": "2026年6月", "province": "山东",
  "audit_start": "", "audit_end": "",
  "data_start": "2022-01-01", "data_end": "2024-12-31",
  "building_area": 0, "people_count": 0,

  "buildings": [
    {"name":"","year":0,"function":"","floors":"","area":0,
     "structure":"","insulation":"","window_type":""}
  ],

  "energy_yearly": [
    {"year":2022,"electricity_kwh":0,"water_m3":0,"natural_gas_m3":0,
     "heating_energy_heat_gj":0,"heating_cost_wan":0,
     "petrol_kg":0,"diesel_kg":0,
     "electricity_cost_wan":0,"water_cost_wan":0}
  ],

  "equipment": [
    {"name":"","category":"","spec":"","quantity":0,"remark":""}
  ],

  "metering": {
    "has_monitoring_system": false,
    "has_household_metering": false
  },

  "management": {},
  "images": [],
  "_note_images": "images 必须是纯路径字符串数组 List[str]（例: [\"E:/图片/建筑.jpg\"]），不可传 dict 对象。上限 5 张。"
}

## 校验

> ⚠️ 原 `config_validator.py` 已删除（当前代码无独立 config 校验模块）。
> 采集/构建入口（`data_collection_cli.py` / Hermes 工具）负责校验关键字段；
> 数据完整性检查见 `data_check.py::check_completeness`。
