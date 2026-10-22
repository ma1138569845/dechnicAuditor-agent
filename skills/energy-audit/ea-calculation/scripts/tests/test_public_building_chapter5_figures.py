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


if __name__ == "__main__":
    unittest.main()
