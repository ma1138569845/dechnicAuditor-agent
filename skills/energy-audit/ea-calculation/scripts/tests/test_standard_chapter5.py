import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "standard_chapter5.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "standard_chapter5_under_test", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StandardChapter5QuotaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def _render(self, *, tier_labels, rows):
        spec = {
            "years": [
                {
                    "year": 2023,
                    "electricity_kwh": 1000,
                    "electricity_cost_wan": 1,
                    "water_t": 100,
                    "water_cost_wan": 1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                },
                {
                    "year": 2024,
                    "electricity_kwh": 1100,
                    "electricity_cost_wan": 1.1,
                    "water_t": 110,
                    "water_cost_wan": 1.1,
                    "gas_m3": 0,
                    "heat_gj": 0,
                },
            ]
        }
        metrics = [{
            "key": "unit_area_heating_energy",
            "label": "单位建筑面积供暖能耗",
            "unit": "kgce/(m²·a)",
            "tier_labels": tier_labels,
            "anchor": "表7.0.2",
        }]
        return self.module.render(
            spec=spec,
            results=rows,
            unit_name="测试单位",
            standard_id="DB37/T 5078-2024",
            standard_title="商务办公建筑能耗限额标准",
            metrics=metrics,
            figures_manifest={"figures": []},
        )

    def test_each_year_uses_its_own_corrected_quota(self):
        markdown = self._render(
            tier_labels=["约束值", "先进值"],
            rows=[
                {
                    "year": 2023,
                    "values": {"unit_area_heating_energy": 8.0},
                    "quota": {"unit_area_heating_energy": [9.0, 7.0]},
                    "grade": {"unit_area_heating_energy": "符合约束值"},
                },
                {
                    "year": 2024,
                    "values": {"unit_area_heating_energy": 8.5},
                    "quota": {"unit_area_heating_energy": [12.0, 9.0]},
                    "grade": {"unit_area_heating_energy": "达到先进值"},
                },
            ],
        )

        self.assertIn("| 约束值（kgce/(m²·a)） | 9 | 12 |", markdown)
        self.assertIn("| 先进值（kgce/(m²·a)） | 7 | 9 |", markdown)
        self.assertIn("各年度限额依据该年度实际使用强度修正后分别列示", markdown)

    def test_three_tier_standard_keeps_all_three_tiers(self):
        markdown = self._render(
            tier_labels=["约束值", "基准值", "引导值"],
            rows=[
                {
                    "year": 2023,
                    "values": {"unit_area_heating_energy": 3.0},
                    "quota": {"unit_area_heating_energy": [7.0, 4.5, 2.5]},
                    "grade": {"unit_area_heating_energy": "低于基准值"},
                },
                {
                    "year": 2024,
                    "values": {"unit_area_heating_energy": 2.0},
                    "quota": {"unit_area_heating_energy": [7.0, 4.5, 2.5]},
                    "grade": {"unit_area_heating_energy": "低于引导值"},
                },
            ],
        )

        self.assertIn("| 约束值（kgce/(m²·a)） | 7 | 7 |", markdown)
        self.assertIn("| 基准值（kgce/(m²·a)） | 4.5 | 4.5 |", markdown)
        self.assertIn("| 引导值（kgce/(m²·a)） | 2.5 | 2.5 |", markdown)


if __name__ == "__main__":
    unittest.main()
