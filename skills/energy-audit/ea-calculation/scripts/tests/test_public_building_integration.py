import importlib.util
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[5]


def load_report_family_module():
    """只加载镜像仓中的路由模块，不改变 deploy 依赖的包搜索顺序。"""
    path = ROOT / "tools" / "energy_audit" / "report_family.py"
    spec = importlib.util.spec_from_file_location(
        "report_family_under_test", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REPORT_FAMILY = load_report_family_module()
ReportFamilyUnsupported = REPORT_FAMILY.ReportFamilyUnsupported
resolve_report_family = REPORT_FAMILY.resolve_report_family


SCRIPT = Path(__file__).resolve().parents[1] / "public_building_indicators.py"
CALIBER_SCRIPT = (
    Path(__file__).resolve().parents[1] / "caliber_agent.py"
)


def load_indicator_module():
    spec = importlib.util.spec_from_file_location(
        "public_building_indicators_under_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_caliber_module():
    """加载计算入口，但用替身切断部署环境和图表依赖。"""
    report_family = types.ModuleType("tools.energy_audit.report_family")
    report_family.ReportFamilyUnsupported = ReportFamilyUnsupported
    report_family.resolve_report_family = resolve_report_family

    project_data = types.ModuleType("tools.energy_audit.project_data")
    project_data.load_project = mock.Mock(return_value=None)
    project_data.AuditProject = object

    indicators = types.ModuleType("tools.energy_audit.indicators")
    for name in (
        "YearlyEnergyData",
        "calc_unit_area_non_heating_energy",
        "compare_with_benchmark",
        "calc_unit_area_electricity",
        "calc_per_capita_energy",
        "calc_water_indicator",
        "calc_unit_area_heating_energy",
        "project_sub_type",
        "calc_baseline",
        "resolve_coefficient",
        "resolve_benchmark",
        "institution_category_to_type",
    ):
        setattr(indicators, name, mock.Mock())

    chapter5 = types.ModuleType("tools.energy_audit.chapter5_agent")
    chapter5.generate = mock.Mock()
    chapter5.generate_charts = mock.Mock()
    chapter5.load_chapter5_manifest = mock.Mock()

    public_indicators = types.ModuleType("public_building_indicators")
    public_indicators.compute_project = mock.Mock()
    public_chapter5 = types.ModuleType("public_building_chapter5")
    public_chapter5.render = mock.Mock()

    substitutes = {
        "tools.energy_audit.report_family": report_family,
        "tools.energy_audit.project_data": project_data,
        "tools.energy_audit.indicators": indicators,
        "tools.energy_audit.chapter5_agent": chapter5,
        "public_building_indicators": public_indicators,
        "public_building_chapter5": public_chapter5,
    }

    spec = importlib.util.spec_from_file_location(
        "caliber_agent_under_test", CALIBER_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {CALIBER_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    original_path = list(sys.path)
    try:
        with (
            mock.patch.dict(sys.modules, substitutes),
            mock.patch.dict(
                os.environ,
                {
                    "HERMES_AGENT_HOME": str(
                        Path(
                            os.environ.get(
                                "EA_TARGET_REPO",
                                r"D:\data\pyProject\dc_agent\dechnicAuditor-agent",
                            )
                        )
                    )
                },
            ),
        ):
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    return module


class ReportFamilyResolutionTests(unittest.TestCase):
    def test_public_institution_remains_the_backward_compatible_default(self):
        context = resolve_report_family({})
        self.assertEqual(context.family, "public_institution")
        self.assertTrue(context.supported)

    def test_zhejiang_public_building_selects_the_zhejiang_pack(self):
        context = resolve_report_family({
            "unit_type": "公共建筑",
            "province": "浙江省",
        })
        self.assertEqual(context.family, "public_building")
        self.assertEqual(context.region, "浙江")
        self.assertEqual(
            context.standard_pack,
            "energy-audit-core/references/standards/zhejiang/",
        )
        self.assertTrue(context.supported)

    def test_non_zhejiang_public_building_is_rejected(self):
        with self.assertRaisesRegex(
            ReportFamilyUnsupported, "目前仅接入浙江"
        ):
            resolve_report_family({
                "unit_type": "公共建筑",
                "province": "山东",
            })

    def test_unknown_report_family_is_rejected(self):
        with self.assertRaisesRegex(
            ReportFamilyUnsupported, "不支持的报告族"
        ):
            resolve_report_family({"unit_type": "工业企业"})


class CalculationEntryGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_caliber_module()

    def test_non_zhejiang_public_building_stops_before_any_calculation(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_type="公共建筑", province="山东")
        )
        self.module.TOOLS_AVAILABLE = True
        self.module.load_project = mock.Mock(return_value=project)
        self.module.extract_yearly_data = mock.Mock()
        self.module.run_public_building_caliber = mock.Mock()

        with redirect_stdout(io.StringIO()):
            result = self.module.run_caliber("unsupported-project")

        self.assertIn("目前仅接入浙江", result["error"])
        self.module.extract_yearly_data.assert_not_called()
        self.module.run_public_building_caliber.assert_not_called()

    def test_public_institution_keeps_the_existing_calculation_path(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_type="公共机构", province="山东")
        )
        self.module.TOOLS_AVAILABLE = True
        self.module.load_project = mock.Mock(return_value=project)
        self.module.extract_yearly_data = mock.Mock(return_value=[])
        self.module.run_public_building_caliber = mock.Mock()

        with redirect_stdout(io.StringIO()):
            result = self.module.run_caliber("legacy-project")

        self.assertEqual(result["error"], "无能耗数据")
        self.module.extract_yearly_data.assert_called_once_with(project)
        self.module.run_public_building_caliber.assert_not_called()


class HotelWaterDenominatorTests(unittest.TestCase):
    def test_water_grade_keeps_the_standard_occupancy_adjustment(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "5",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0.8,
            "hotel_corrections": {"occupancy": 1.0},
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 100000,
                    "water_t": 20000,
                }
            ],
        }

        result = module.compute_project(project, quota)[0]

        self.assertEqual(result["values"]["water_per_bed"], 200.0)
        self.assertEqual(result["grade"]["water"], "低于通用值")
        self.assertEqual(result["values"]["water_per_bed_normalized"], 250.0)


if __name__ == "__main__":
    unittest.main()

