import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "public_building_chapter5.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "public_building_chapter5_under_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicBuildingChapter5FigureTests(unittest.TestCase):
    def test_hotel_5_3_1_uses_db33_t_760_formula_and_standard_symbols(self):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "electricity_cost_wan": 10,
                    "water_t": 100,
                    "water_cost_wan": 1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                }
            ],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100.0,
                },
                "quota": {
                    "unit_comparable_energy": [25.0, 18.0, 12.0],
                    "water": [125.0, 70.0],
                },
                "grade": {
                    "unit_comparable_energy": "低于1级（先进值）",
                    "water": "低于先进值",
                },
            }
        ]

        markdown = module.render(spec, results, "测试饭店")

        self.assertIn("单位可比综合能耗按下列公式计算：", markdown)
        self.assertIn("[FORMULA10]", markdown)
        self.assertIn("式中：", markdown)
        self.assertIn(
            "E_{kd}——单位可比综合能耗，单位为千克标准煤每平方米"
            "（kgce/m²）；",
            markdown,
        )
        self.assertIn(
            "E_{j}——单位综合能耗，单位为千克标准煤每平方米"
            "（kgce/m²）；",
            markdown,
        )
        self.assertIn("a——综合能耗修正系数；", markdown)
        self.assertIn("m——第m项综合能耗修正系数。", markdown)
        self.assertIn(
            "《旅游饭店单位综合能耗限额及计算方法》"
            "（DB33/T 760-2023）",
            markdown,
        )
        self.assertNotIn("该标准表", markdown)
        self.assertNotIn("a1×a2×…×am——各项修正系数连乘值", markdown)

    def test_hotel_metrics_start_with_comparable_energy_without_reference_section(
        self,
    ):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "electricity_cost_wan": 10,
                    "water_t": 100,
                    "water_cost_wan": 1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                }
            ],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100.0,
                    "water_per_bed_normalized": 60.0,
                },
                "quota": {
                    "unit_comparable_energy": [25.0, 18.0, 12.0],
                    "water": [125.0, 70.0],
                },
                "grade": {
                    "unit_comparable_energy": "低于1级（先进值）",
                    "water": "低于先进值",
                },
                "notes": {"water_missing": False},
            }
        ]

        markdown = module.render(spec, results, "测试饭店")

        self.assertIn("### 5.3.1 单位可比综合能耗", markdown)
        self.assertIn("### 5.3.2 单位床年用水量", markdown)
        self.assertIn(
            "单位综合能耗 E_{j} 仅为计算单位可比综合能耗的中间量，"
            "不作为独立评价指标。",
            markdown,
        )
        self.assertNotIn("### 5.3.1 单位综合能耗", markdown)
        self.assertNotIn("### 5.3.3", markdown)

    def test_hotel_energy_table_uses_unified_tiers_and_institution_grade(self):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "electricity_cost_wan": 10,
                    "water_t": 100,
                    "water_cost_wan": 1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                }
            ],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100.0,
                },
                "quota": {
                    "unit_comparable_energy": [25.0, 18.0, 12.0],
                    "water": [125.0, 70.0],
                },
                "grade": {
                    # 旧结果仍应在新报告中统一为公共机构评价短语。
                    "unit_comparable_energy": "低于1级（先进值）",
                    "water": "低于先进值",
                },
            }
        ]

        markdown = module.render(spec, results, "测试饭店")

        self.assertIn("表5.2 单位综合能耗", markdown)
        self.assertIn("表5.3 单位可比综合能耗", markdown)
        self.assertIn("| 定额标准约束值（kgce/m²） | 25 |", markdown)
        self.assertIn("| 定额标准基准值（kgce/m²） | 18 |", markdown)
        self.assertIn("| 定额标准引导值（kgce/m²） | 12 |", markdown)
        self.assertIn("| 评价结果 | 低于引导值 |", markdown)
        self.assertNotIn("3级（限额值）", markdown)
        self.assertNotIn("2级（约束值）", markdown)
        self.assertNotIn("1级（先进值）", markdown)

    def test_hotel_unit_energy_table_splits_coefficient_rows_and_excludes_missing_water(
        self,
    ):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2023,
                    "electricity_kwh": 900,
                    "water_t": 0,
                    "beds": 100,
                    "occupancy": 0.9,
                },
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "water_t": 100,
                    "beds": 100,
                    "occupancy": 0.9,
                },
            ],
        }
        results = [
            {
                "year": 2023,
                "values": {
                    "unit_energy": 5.5,
                    "unit_comparable_energy": 5.0,
                    "water_per_bed": 0,
                },
                "quota": {
                    "unit_comparable_energy": [25, 18, 12],
                    "water": [125, 70],
                },
                "grade": {
                    "unit_comparable_energy": "无数据，不评价",
                    "water": "无数据，不评价",
                },
                "notes": {
                    "water_missing": True,
                    "energy_complete": False,
                    "energy_kgce": 110.61,
                    "area_mm": 1000,
                    "energy_components": {
                        "electricity": {
                            "amount": 900,
                            "coefficient": 0.1229,
                            "kgce": 110.61,
                            "unit": "kWh",
                        }
                    },
                },
            },
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100,
                },
                "quota": {
                    "unit_comparable_energy": [25, 18, 12],
                    "water": [125, 70],
                },
                "grade": {
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
                "notes": {
                    "water_missing": False,
                    "energy_complete": True,
                    "energy_kgce": 148.61,
                    "area_mm": 1000,
                    "correction_factors": {"occupancy": 1.1},
                    "correction_product": 1.1,
                    "energy_components": {
                        "electricity": {
                            "amount": 1000,
                            "coefficient": 0.1229,
                            "kgce": 122.9,
                            "unit": "kWh",
                        },
                        "new_water": {
                            "amount": 100,
                            "coefficient": 0.2571,
                            "kgce": 25.71,
                            "unit": "t",
                        },
                    },
                },
            },
        ]

        markdown = module.render(spec, results, "测试饭店")
        table_52 = markdown.split("表5.2 单位综合能耗", 1)[1].split(
            "以单位综合能耗为中间量", 1
        )[0]

        self.assertIn("| 项目 | 2024年 |", table_52)
        self.assertNotIn("2023年", table_52)
        self.assertIn("| 年耗电量（kWh） | 1000 |", table_52)
        self.assertIn("| 折标准煤系数（kgce/kWh） | 0.1229 |", table_52)
        self.assertIn("| 年取水量（m³） | 100 |", table_52)
        self.assertIn("| 折标准煤系数（kgce/t） | 0.2571 |", table_52)
        self.assertNotIn("kgce/kWh、kgce/t", table_52)
        self.assertNotIn("评价结果", table_52)

    def test_hotel_5_1_keeps_complete_electricity_year_when_water_missing(
        self,
    ):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2022,
                    "electricity_kwh": 100,
                    "monthly_electricity_kwh": [None] * 7
                    + [20, 20, 20, 20, 20],
                    "water_t": 0,
                    "beds": 100,
                    "occupancy": 0.9,
                },
                {
                    "year": 2023,
                    "electricity_kwh": 900,
                    "monthly_electricity_kwh": [75] * 12,
                    "water_t": 0,
                    "beds": 100,
                    "occupancy": 0.9,
                },
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "monthly_electricity_kwh": [83.33] * 12,
                    "water_t": 100,
                    "beds": 100,
                    "occupancy": 0.9,
                },
            ],
        }
        results = [
            {
                "year": 2023,
                "values": {
                    "unit_energy": 5.5,
                    "unit_comparable_energy": 5.0,
                    "water_per_bed": 0,
                },
                "quota": {
                    "unit_comparable_energy": [25, 18, 12],
                    "water": [125, 70],
                },
                "grade": {
                    "unit_comparable_energy": "无数据，不评价",
                    "water": "无数据，不评价",
                },
                "notes": {
                    "water_missing": True,
                    "energy_complete": False,
                    "area_mm": 1000,
                    "energy_components": {
                        "electricity": {
                            "amount": 900,
                            "coefficient": 0.1229,
                            "kgce": 110.61,
                        }
                    },
                },
            },
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100,
                },
                "quota": {
                    "unit_comparable_energy": [25, 18, 12],
                    "water": [125, 70],
                },
                "grade": {
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
                "notes": {
                    "water_missing": False,
                    "energy_complete": True,
                    "area_mm": 1000,
                    "correction_factors": {"occupancy": 1.1},
                    "correction_product": 1.1,
                    "energy_components": {
                        "electricity": {
                            "amount": 1000,
                            "coefficient": 0.1229,
                            "kgce": 122.9,
                        },
                        "new_water": {
                            "amount": 100,
                            "coefficient": 0.2571,
                            "kgce": 25.71,
                        },
                    },
                },
            },
        ]

        markdown = module.render(spec, results, "测试饭店")
        section_51 = markdown.split("## 5.1", 1)[1].split("## 5.2", 1)[0]
        section_521 = markdown.split("### 5.2.1", 1)[1].split(
            "### 5.2.2", 1
        )[0]

        self.assertIn("电量数据完整的2023年、2024年", section_51)
        self.assertIn(
            "2023年缺少独立新水计量，仍纳入用电分析，但不纳入含新水的"
            "完整综合能耗口径和用水指标评价。",
            section_51,
        )
        self.assertIn("| 2023年 | 900 |", section_521)
        self.assertIn("| 2024年 | 1000 |", section_521)
        self.assertNotIn("| 2022年 |", section_521)

    def test_hotel_water_table_uses_selected_h6110_tiers_and_subitem(self):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "star": "3",
            "years": [{"year": 2024, "water_t": 100}],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 80.0,
                },
                "quota": {
                    "unit_comparable_energy": [25.0, 18.0, 12.0],
                    "water": [256.0, 146.0],
                },
                "grade": {
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
                "notes": {
                    "water_industry_code": "H6110",
                    "water_category_name": "旅游饭店",
                    "water_subitem": "三星级（或具有同等规模、质量、水平）",
                },
            }
        ]

        markdown = module.render(spec, results, "测试饭店")

        self.assertIn(
            "本项目按 H6110 旅游饭店—三星级（或具有同等规模、质量、水平）"
            "匹配用水定额，定额单位为 m³/(床·年)。",
            markdown,
        )
        self.assertIn("| 定额标准通用值（m³/(床·年)） | 256 |", markdown)
        self.assertIn("| 定额标准先进值（m³/(床·年)） | 146 |", markdown)

    def test_hotel_water_metric_uses_bed_year_formula_and_normalized_value(
        self,
    ):
        module = load_module()
        spec = {
            "subtype": "hotel",
            "star": "3",
            "years": [{"year": 2024, "water_t": 100}],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100.0,
                    "water_per_bed_unadjusted": 80.0,
                    "water_per_bed_normalized": 100.0,
                },
                "quota": {
                    "unit_comparable_energy": [25.0, 18.0, 12.0],
                    "water": [256.0, 146.0],
                },
                "grade": {
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
                "notes": {
                    "water_industry_code": "H6110",
                    "water_category_name": "旅游饭店",
                    "water_subitem": "三星级（或具有同等规模、质量、水平）",
                },
            }
        ]

        markdown = module.render(spec, results, "测试饭店")

        self.assertIn("### 5.3.2 单位床年用水量", markdown)
        self.assertIn("单位床年用水量按下式计算：", markdown)
        self.assertIn("[FORMULA9]", markdown)
        self.assertIn(
            "V_{uc}——单位床年用水量，单位为立方米每床年"
            "（m³/(床·年)）；",
            markdown,
        )
        self.assertIn(
            "V_{k}——年度用水量，单位为立方米每年（m³/a）；",
            markdown,
        )
        self.assertIn("N——总床位数，单位为床；", markdown)
        self.assertIn("Q——宾馆床位出租率。", markdown)
        self.assertIn("| 单位床年用水量（m³/(床·年)） | 100 |", markdown)
        self.assertNotIn("按出租率折算的单位用水量", markdown)

    def test_render_uses_only_manifest_captions(self):
        module = load_module()
        spec = {
            "subtype": "office",
            "area_m2": 1000,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 1000,
                    "electricity_cost_wan": 10,
                    "water_t": 100,
                    "water_cost_wan": 1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                }
            ],
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_area_energy": 10,
                    "unit_area_electricity": 5,
                    "per_capita_energy": 6,
                    "per_capita_electricity": 3,
                    "unit_water": 1,
                },
                "quota": {
                    "unit_area_energy": [20, 15, 10],
                    "unit_area_electricity": [10, 8, 5],
                    "per_capita_energy": [10, 8, 6],
                    "per_capita_electricity": [6, 5, 3],
                    "unit_water": [2, 1],
                },
                "grade": {
                    "unit_area_energy": "基准值",
                    "unit_area_electricity": "引导值",
                    "per_capita_energy": "引导值",
                    "per_capita_electricity": "引导值",
                    "unit_water": "先进值",
                },
            }
        ]
        manifest = {
            "figures": [
                {
                    "figure_no": "5.1",
                    "caption": "图5.1 能源资源流向图",
                    "kind": "energy_flow",
                }
            ]
        }
        markdown = module.render(
            spec, results, "测试单位", figures_manifest=manifest
        )
        self.assertIn("图5.1 能源资源流向图", markdown)
        self.assertNotIn("图5.2", markdown)
        self.assertNotIn("![图5.", markdown)

    def test_incomplete_year_is_excluded_from_tables_but_kept_in_narrative(
        self,
    ):
        module = load_module()
        spec = {
            "subtype": "office",
            "area_m2": 1000,
            "incomplete_report_years": {
                "2022": ["建筑自 2022年8月投入使用"],
            },
            "years": [
                {
                    "year": year,
                    "electricity_kwh": 1000 + year,
                    "electricity_cost_wan": 10 + year,
                    "water_t": 100 + year,
                    "water_cost_wan": 1 + year,
                    "gas_m3": 0,
                    "heat_gj": 0,
                }
                for year in (2022, 2023, 2024)
            ],
        }
        results = [
            {
                "year": year,
                "values": {
                    "unit_area_energy": 10 + idx,
                    "unit_area_electricity": 5 + idx,
                    "per_capita_energy": 6 + idx,
                    "per_capita_electricity": 3 + idx,
                    "unit_water": 1 + idx,
                },
                "quota": {
                    "unit_area_energy": [20, 15, 10],
                    "unit_area_electricity": [10, 8, 5],
                    "per_capita_energy": [10, 8, 6],
                    "per_capita_electricity": [6, 5, 3],
                    "unit_water": [2, 1],
                },
                "grade": {
                    "unit_area_energy": "基准值",
                    "unit_area_electricity": "引导值",
                    "per_capita_energy": "引导值",
                    "per_capita_electricity": "引导值",
                    "unit_water": "先进值",
                },
            }
            for idx, year in enumerate((2022, 2023, 2024))
        ]

        markdown = module.render(spec, results, "测试单位")
        table_lines = [
            line for line in markdown.splitlines() if line.startswith("|")
        ]

        self.assertTrue(table_lines)
        self.assertNotIn("2022年", "\n".join(table_lines))
        self.assertIn("| 项目 | 2023年 | 2024年 |", markdown)
        self.assertIn("2022年为10kgce/m²", markdown)


if __name__ == "__main__":
    unittest.main()
