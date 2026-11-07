import importlib.util
import io
import os
import sys
import tempfile
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
SHANDONG_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "shandong_public_building_indicators.py"
)
ZHEJIANG_PUBLIC_INSTITUTION_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "zhejiang_public_institution_indicators.py"
)
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


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dept_dict_module():
    return load_module(
        "dept_dict_under_test",
        ROOT / "tools" / "energy_audit" / "dept_dict.py",
    )


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
    shandong_indicators = types.ModuleType(
        "shandong_public_building_indicators"
    )
    shandong_indicators.compute_project = mock.Mock()
    shandong_indicators.load_quota_values = mock.Mock()
    zhejiang_institution_indicators = types.ModuleType(
        "zhejiang_public_institution_indicators"
    )
    zhejiang_institution_indicators.compute_project = mock.Mock()
    standard_chapter5 = types.ModuleType("standard_chapter5")
    standard_chapter5.render = mock.Mock()
    reporting_periods = load_module(
        "reporting_periods_under_test",
        ROOT / "tools" / "energy_audit" / "reporting_periods.py",
    )

    substitutes = {
        "tools.energy_audit.dept_dict": load_dept_dict_module(),
        "tools.energy_audit.report_family": report_family,
        "tools.energy_audit.reporting_periods": reporting_periods,
        "tools.energy_audit.project_data": project_data,
        "tools.energy_audit.indicators": indicators,
        "tools.energy_audit.chapter5_agent": chapter5,
        "public_building_indicators": public_indicators,
        "public_building_chapter5": public_chapter5,
        "shandong_public_building_indicators": shandong_indicators,
        "zhejiang_public_institution_indicators": (
            zhejiang_institution_indicators
        ),
        "standard_chapter5": standard_chapter5,
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

    def test_shandong_public_building_selects_the_shandong_pack(self):
        context = resolve_report_family({
            "unit_type": "公共建筑",
            "province": "山东",
        })
        self.assertEqual(context.family, "public_building")
        self.assertEqual(context.region, "山东")
        self.assertEqual(
            context.standard_pack,
            (
                "energy-audit-core/references/standards/"
                "shandong/public_building/"
            ),
        )
        self.assertTrue(context.is_shandong_public_building)

    def test_unsupported_public_building_province_is_rejected(self):
        with self.assertRaisesRegex(
            ReportFamilyUnsupported, "目前仅接入山东、浙江"
        ):
            resolve_report_family({
                "unit_type": "公共建筑",
                "province": "江苏",
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

    def test_unsupported_public_building_stops_before_any_calculation(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_type="公共建筑", province="江苏")
        )
        self.module.TOOLS_AVAILABLE = True
        self.module.load_project = mock.Mock(return_value=project)
        self.module.extract_yearly_data = mock.Mock()
        self.module.run_public_building_caliber = mock.Mock()
        self.module.run_shandong_public_building_caliber = mock.Mock()
        self.module.run_zhejiang_public_institution_caliber = mock.Mock()

        with redirect_stdout(io.StringIO()):
            result = self.module.run_caliber("unsupported-project")

        self.assertIn("目前仅接入山东、浙江", result["error"])
        self.module.extract_yearly_data.assert_not_called()
        self.module.run_public_building_caliber.assert_not_called()
        self.module.run_shandong_public_building_caliber.assert_not_called()
        self.module.run_zhejiang_public_institution_caliber.assert_not_called()

    def test_shandong_public_building_uses_only_the_shandong_runner(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_type="公共建筑", province="山东")
        )
        self.module.TOOLS_AVAILABLE = True
        self.module.load_project = mock.Mock(return_value=project)
        self.module.extract_yearly_data = mock.Mock()
        self.module.run_public_building_caliber = mock.Mock()
        self.module.run_zhejiang_public_institution_caliber = mock.Mock()
        expected = {"indicators_path": "shandong.json"}
        self.module.run_shandong_public_building_caliber = mock.Mock(
            return_value=expected
        )

        with redirect_stdout(io.StringIO()):
            result = self.module.run_caliber("shandong-project")

        self.assertIs(result, expected)
        self.module.run_shandong_public_building_caliber.assert_called_once_with(
            project_name="shandong-project",
            proj=project,
            skip_charts=False,
            output_dir=None,
        )
        self.module.run_public_building_caliber.assert_not_called()
        self.module.run_zhejiang_public_institution_caliber.assert_not_called()
        self.module.extract_yearly_data.assert_not_called()

    def test_zhejiang_public_institution_avoids_the_legacy_main_chain(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_type="公共机构", province="浙江")
        )
        self.module.TOOLS_AVAILABLE = True
        self.module.load_project = mock.Mock(return_value=project)
        self.module.extract_yearly_data = mock.Mock()
        self.module.run_public_building_caliber = mock.Mock()
        self.module.run_shandong_public_building_caliber = mock.Mock()
        expected = {"indicators_path": "zhejiang-pi.json"}
        self.module.run_zhejiang_public_institution_caliber = mock.Mock(
            return_value=expected
        )

        with redirect_stdout(io.StringIO()):
            result = self.module.run_caliber(
                "zhejiang-project",
                skip_charts=True,
                output_dir="out",
            )

        self.assertIs(result, expected)
        self.module.run_zhejiang_public_institution_caliber.assert_called_once_with(
            project_name="zhejiang-project",
            proj=project,
            skip_charts=True,
            output_dir="out",
        )
        self.module.run_public_building_caliber.assert_not_called()
        self.module.run_shandong_public_building_caliber.assert_not_called()
        self.module.extract_yearly_data.assert_not_called()

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


class PublicBuildingCodeRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_caliber_module()

    def _project(self, **base_fields):
        fields = {
            "unit_name": "某公共建筑",
            "unit_type": "公共建筑",
            "province": "浙江",
            "unit_func": "",
            "children_func": "",
            "institution_category": "",
            "specific_type": "",
            "building_area": 10000,
            "people_count": 100,
            "beds_count": 0,
            "city": "",
            "address": "",
            "clinic_num": 0,
        }
        fields.update(base_fields)
        base = SimpleNamespace(**fields)
        return SimpleNamespace(
            base=base,
            buildings=[],
            energy_yearly=[],
            energy_monthly=[],
        )

    def test_zhejiang_hotel_star_comes_from_platform_code(self):
        project = self._project(
            unit_func="zj_hotel",
            children_func="zj_hotel_4",
        )
        spec = self.module.build_public_building_spec(project, {})
        self.assertEqual(spec["subtype"], "hotel")
        self.assertEqual(spec["star"], "4")

    def test_incomplete_year_is_flagged_without_removing_chart_inputs(self):
        project = self._project(
            unit_func="zj_hotel",
            children_func="zj_hotel_3",
        )
        project.energy_yearly = [
            SimpleNamespace(
                year=2022,
                electricity_kwh=100,
                water_m3=0,
                natural_gas_m3=0,
                heating_energy_heat_gj=0,
                heating_energy_kwh=0,
            ),
            SimpleNamespace(
                year=2023,
                electricity_kwh=1200,
                water_m3=80,
                natural_gas_m3=0,
                heating_energy_heat_gj=0,
                heating_energy_kwh=0,
            ),
        ]
        raw = {
            "buildings": [{"begin_date": "2022-08"}],
            "energy_yearly": [
                {
                    "year": 2022,
                    "monthly_electricity_kwh": [
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        20,
                        20,
                        20,
                        20,
                        20,
                    ],
                },
                {
                    "year": 2023,
                    "monthly_electricity_kwh": [100] * 12,
                },
            ],
        }

        spec = self.module.build_public_building_spec(project, raw)

        self.assertIn("2022", spec["incomplete_report_years"])
        self.assertEqual(
            [row["year"] for row in spec["years"]],
            [2022, 2023],
        )

    def test_platform_hotel_star_overrides_stale_water_category(self):
        project = self._project(
            unit_func="zj_hotel",
            children_func="zj_hotel_3",
        )
        spec = self.module.build_public_building_spec(
            project,
            {"public_building": {"water_category": "below"}},
        )

        self.assertEqual(spec["star"], "3")
        self.assertEqual(spec["water_category"], "3")

    def test_zhejiang_public_building_without_codes_is_blocked(self):
        project = self._project(unit_name="某办公建筑")
        with self.assertRaisesRegex(ValueError, "customer_func"):
            self.module.build_public_building_spec(project, {})

    def test_shandong_b_routes_to_agency_office(self):
        project = self._project(
            province="山东",
            unit_func="B",
            children_func="",
        )
        self.assertEqual(
            self.module._shandong_public_building_subtype(
                project.base,
                {},
            ),
            "agency_office",
        )

    def test_shandong_d3_sets_hospital_level_and_specialty_from_code(self):
        project = self._project(
            province="山东",
            unit_func="D",
            children_func="D3",
        )
        resolved = self.module._public_building_codes(project.base)
        self.assertEqual(resolved["hospital_level"], "<=2")
        self.assertEqual(resolved["hospital_specialty"], "general")

    def test_shandong_agency_spec_carries_5077_correction_parameters(self):
        project = self._project(
            province="山东",
            unit_func="B",
            children_func="",
        )
        raw = {
            "public_building": {
                "area_m2": 10000,
                "heating_area_m2": 10000,
                "annual_use_hours": 2500,
                "area_per_person": 10,
            }
        }
        spec = self.module.build_shandong_public_building_spec(project, raw)
        self.assertEqual(spec["subtype"], "agency_office")
        self.assertEqual(spec["correction"]["annual_use_hours"], 2500)
        self.assertEqual(spec["correction"]["area_per_person"], 10)

    def test_shandong_agency_metrics_include_all_three_5077_columns(self):
        metrics = self.module._shandong_metrics("agency_office")
        self.assertEqual(
            {metric["key"] for metric in metrics},
            {
                "unit_area_heating_energy",
                "unit_area_non_heating_electricity",
                "unit_area_total_electricity",
            },
        )


class HotelWaterDenominatorTests(unittest.TestCase):
    def test_all_hotel_water_quota_tiers_match_the_2019_table(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        cases = (
            ("5", [350, 216], "H6110", "旅游饭店", "四、五星级（含白金五星级或具有同等规模、质量、水平）"),
            ("4", [350, 216], "H6110", "旅游饭店", "四、五星级（含白金五星级或具有同等规模、质量、水平）"),
            ("3", [256, 146], "H6110", "旅游饭店", "三星级（或具有同等规模、质量、水平）"),
            ("2", [180, 110], "H6110", "旅游饭店", "一、二星级（或具有同等规模、质量、水平）"),
            ("1", [180, 110], "H6110", "旅游饭店", "一、二星级（或具有同等规模、质量、水平）"),
            ("below", [125, 70], "H6120", "一般旅馆", "星级以下（招待所、旅社）"),
        )

        for water_category, expected, code, category, subitem in cases:
            with self.subTest(water_category=water_category):
                project = {
                    "subtype": "hotel",
                    "star": "3",
                    "water_category": water_category,
                    "area_m2": 10000,
                    "beds": 100,
                    "occupancy": 0.8,
                    "years": [
                        {
                            "year": 2024,
                            "electricity_kwh": 100000,
                            "water_t": 20000,
                        }
                    ],
                }

                result = module.compute_project(project, quota)[0]

                self.assertEqual(result["quota"]["water"], expected)
                self.assertEqual(
                    result["notes"]["water_industry_code"], code
                )
                self.assertEqual(
                    result["notes"]["water_category_name"], category
                )
                self.assertEqual(result["notes"]["water_subitem"], subitem)

    def test_platform_star_routes_water_quota_to_h6110(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "3",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0.8,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 100000,
                    "water_t": 20000,
                }
            ],
        }

        result = module.compute_project(project, quota)[0]

        self.assertEqual(result["quota"]["water"], [256, 146])
        self.assertEqual(result["notes"]["water_category"], "3")
        self.assertEqual(result["notes"]["water_industry_code"], "H6110")
        self.assertEqual(result["notes"]["water_category_name"], "旅游饭店")
        self.assertEqual(
            result["notes"]["water_subitem"],
            "三星级（或具有同等规模、质量、水平）",
        )

    def test_only_explicit_below_uses_general_hotel_h6120(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "3",
            "water_category": "below",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0.8,
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 100000,
                    "water_t": 20000,
                }
            ],
        }

        result = module.compute_project(project, quota)[0]

        self.assertEqual(result["quota"]["water"], [125, 70])
        self.assertEqual(result["notes"]["water_industry_code"], "H6120")
        self.assertEqual(result["notes"]["water_category_name"], "一般旅馆")
        self.assertEqual(
            result["notes"]["water_subitem"],
            "星级以下（招待所、旅社）",
        )

    def test_unit_energy_is_intermediate_not_a_graded_indicator(self):
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

        self.assertIn("unit_energy", result["values"])
        self.assertNotIn("unit_energy", result["grade"])
        self.assertEqual(result["notes"]["unit_energy_role"], "intermediate")

    def test_hotel_missing_new_water_still_grades_complete_electricity_year(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "3",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0.9,
            "hotel_corrections": {"occupancy": 1.1},
            "years": [
                {
                    "year": 2023,
                    "electricity_kwh": 100000,
                    "water_t": 0,
                }
            ],
        }

        result = module.compute_project(project, quota)[0]

        self.assertFalse(result["notes"]["includes_new_water"])
        self.assertFalse(result["notes"]["energy_complete"])
        self.assertFalse(result["notes"]["water_complete"])
        self.assertTrue(result["notes"]["electricity_complete"])
        self.assertFalse(result["notes"]["electricity_missing"])
        self.assertTrue(result["notes"]["unit_comparable_energy_applicable"])
        self.assertEqual(
            result["grade"]["unit_comparable_energy"],
            "低于引导值",
        )
        self.assertEqual(result["grade"]["water"], "无数据，不评价")
        self.assertIn("new_water", result["notes"]["missing_energy_components"])
        self.assertIn("electricity", result["notes"]["energy_components"])

    def test_hotel_incomplete_reporting_year_is_not_graded(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "3",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0.9,
            "hotel_corrections": {"occupancy": 1.1},
            "incomplete_report_years": {
                "2022": ["建筑自2022年8月投入使用"],
            },
            "years": [
                {
                    "year": 2022,
                    "electricity_kwh": 100000,
                    "monthly_electricity_kwh": [0] * 7 + [20000] * 5,
                    "water_t": 2000,
                }
            ],
        }

        result = module.compute_project(project, quota)[0]

        self.assertTrue(result["notes"]["electricity_complete"])
        self.assertFalse(result["notes"]["reporting_period_complete"])
        self.assertFalse(result["notes"]["unit_comparable_energy_applicable"])
        self.assertEqual(
            result["grade"]["unit_comparable_energy"],
            "无数据，不评价",
        )
        self.assertEqual(result["grade"]["water"], "无数据，不评价")

    def test_water_metric_uses_bed_count_and_occupancy_denominator(self):
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

        self.assertEqual(result["values"]["water_per_bed"], 250.0)
        self.assertEqual(
            result["values"]["water_per_bed_unadjusted"], 200.0
        )
        self.assertEqual(result["grade"]["water"], "低于通用值")
        self.assertEqual(result["values"]["water_per_bed_normalized"], 250.0)

    def test_water_metric_rejects_zero_occupancy_instead_of_falling_back(self):
        module = load_indicator_module()
        quota = module.load_quota_values()
        project = {
            "subtype": "hotel",
            "star": "3",
            "area_m2": 10000,
            "beds": 100,
            "occupancy": 0,
            "hotel_corrections": {"occupancy": 1.0},
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 100000,
                    "water_t": 20000,
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "occupancy"):
            module.compute_project(project, quota)


class ZhejiangPublicBuildingGradeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_indicator_module()

    def test_760_uses_public_institution_four_level_evaluation(self):
        cases = (
            (12.0, "低于引导值"),
            (12.1, "低于基准值"),
            (18.0, "低于基准值"),
            (18.1, "低于约束值"),
            (25.0, "低于约束值"),
            (25.1, "高于约束值"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(
                    self.module._grade_760(value, [25.0, 18.0, 12.0]),
                    expected,
                )


class HotelIndicatorJsonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_caliber_module()

    def test_hotel_json_omits_independent_unit_energy_indicator(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_name="测试饭店")
        )
        spec = {
            "subtype": "hotel",
            "area_m2": 10000,
            "people": 0,
            "star": "5",
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
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
            }
        ]

        payload = self.module.build_public_building_indicators_json(
            project, spec, results
        )

        self.assertNotIn("unit_energy", payload)
        self.assertIn("unit_comparable_energy", payload)
        self.assertIn("water_indicator", payload)
        self.assertEqual(
            payload["public_building"]["results"][0]["values"]["unit_energy"],
            6.0,
        )
        benchmark = payload["unit_comparable_energy"]["benchmark"]
        self.assertEqual(
            benchmark,
            {
                "约束值": 25.0,
                "基准值": 18.0,
                "引导值": 12.0,
                "标准": "DB33/T 760-2023",
                "来源": "表1",
                "评价结果": "低于引导值",
            },
        )

    def test_hotel_water_benchmark_exposes_industry_and_subitem(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_name="测试饭店")
        )
        spec = {
            "subtype": "hotel",
            "area_m2": 10000,
            "people": 0,
            "star": "3",
        }
        results = [
            {
                "year": 2024,
                "values": {
                    "unit_energy": 6.0,
                    "unit_comparable_energy": 5.4,
                    "water_per_bed": 100.0,
                    "water_per_bed_normalized": 80.0,
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
                    "water_category": "3",
                    "water_industry_code": "H6110",
                    "water_category_name": "旅游饭店",
                    "water_subitem": "三星级（或具有同等规模、质量、水平）",
                },
            }
        ]

        payload = self.module.build_public_building_indicators_json(
            project, spec, results
        )

        self.assertEqual(
            payload["water_indicator"]["benchmark"],
            {
                "通用值": 256.0,
                "先进值": 146.0,
                "标准": "浙江省用（取）水定额（2019）",
                "来源": "表47",
                "评价结果": "低于先进值",
                "行业代码": "H6110",
                "类别名称": "旅游饭店",
                "分项名称": "三星级（或具有同等规模、质量、水平）",
                "定额单位": "m³/(床·年)",
            },
        )

    def test_hotel_indicator_report_marks_unit_energy_as_intermediate(self):
        project = SimpleNamespace(
            base=SimpleNamespace(unit_name="测试饭店"),
            energy_flow_trees=[],
            equipment=[],
        )
        spec = {
            "subtype": "hotel",
            "area_m2": 10000,
            "people": 0,
            "star": "5",
            "years": [
                {
                    "year": 2024,
                    "electricity_kwh": 100000,
                    "water_t": 20000,
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
                    "unit_comparable_energy": "低于引导值",
                    "water": "低于先进值",
                },
            }
        ]
        indicators = {"project": "测试饭店", "year": 2024}
        family = SimpleNamespace(is_public_building=True)

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(
                    self.module, "_report_family_context", return_value=family
                ),
                mock.patch.object(
                    self.module, "_load_raw_project_data", return_value={}
                ),
                mock.patch.object(
                    self.module, "build_public_building_spec", return_value=spec
                ),
                mock.patch.object(
                    self.module,
                    "compute_public_building_indicators",
                    return_value=results,
                ),
                mock.patch.object(
                    self.module,
                    "build_public_building_indicators_json",
                    return_value=indicators,
                ),
                mock.patch.object(
                    self.module,
                    "load_chapter5_manifest",
                    return_value={"figures": []},
                ),
                mock.patch.object(
                    self.module,
                    "render_public_building_chapter5",
                    return_value="# 第5章",
                ),
            ):
                with redirect_stdout(io.StringIO()):
                    self.module.run_public_building_caliber(
                        "测试饭店",
                        proj=project,
                        skip_charts=True,
                        output_dir=tmp,
                    )
                report = (Path(tmp) / "indicators_report.txt").read_text(
                    encoding="utf-8"
                )

        self.assertIn(
            "unit_energy: 6.0  [中间量，不评价]",
            report,
        )
        self.assertNotIn("[参考指标]", report)


class ShandongPublicBuildingCalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module("shandong_public_building_under_test", SHANDONG_SCRIPT)

    def _project(self, **year):
        return {
            "subtype": "business_office",
            "city": "日照",
            "area_m2": 10000,
            "heating_area_m2": 10000,
            "correction": {
                "annual_use_hours": 2900,
                "area_per_person": 10,
            },
            "years": [{"year": 2024, **year}],
        }

    def test_heating_electricity_requires_annual_equal_value_coefficient(self):
        with self.assertRaisesRegex(ValueError, "全国平均火力发电标准煤耗"):
            self.module.compute_project(
                self._project(
                    electricity_kwh=100000,
                    heating_energy_kwh=5000,
                )
            )

    def test_heating_electricity_accepts_explicit_annual_coefficient(self):
        result = self.module.compute_project(
            self._project(
                electricity_kwh=100000,
                heating_energy_kwh=5000,
                heating_electricity_kgce_per_kwh=0.3,
            )
        )[0]

        self.assertAlmostEqual(
            result["notes"]["heating_energy_kgce"],
            1500.0,
            places=4,
        )
        self.assertEqual(
            len(result["quota"]["unit_area_heating_energy"]),
            2,
        )

    def test_hotel_without_star_is_blocked_instead_of_defaulting(self):
        project = self._project(electricity_kwh=100000)
        project["subtype"] = "hotel"
        with self.assertRaisesRegex(ValueError, "star=3/4/5"):
            self.module.compute_project(project)

    def test_hospital_without_specialty_is_blocked_instead_of_guessing(self):
        project = self._project(electricity_kwh=100000, heating_gas_m3=1000)
        project.update({
            "subtype": "hospital",
            "hospital_level": "三级",
            "beds": 100,
        })
        with self.assertRaisesRegex(ValueError, "综合/专科"):
            self.module.compute_project(project)

    def test_agency_office_uses_5077_and_reports_obsolete_status(self):
        project = self._project(
            electricity_kwh=50000,
            gas_m3=5000,
            heating_gas_m3=3000,
        )
        project.update({
            "subtype": "agency_office",
            "correction": {
                "annual_use_hours": 2500,
                "area_per_person": 10,
            },
        })
        result = self.module.compute_project(project)[0]

        self.assertEqual(result["standard_id"], "DB37/T 5077-2016")
        self.assertEqual(result["standard_table"], "表7.0.3")
        self.assertTrue(result["legacy_override"])
        self.assertEqual(result["standard_status"], "废止")
        self.assertEqual(result["abolished_at"], "2024-10-09")
        self.assertEqual(
            result["quota_raw"]["unit_area_heating_energy"],
            [8.2, 4.3],
        )
        self.assertEqual(
            result["quota_raw"]["unit_area_non_heating_electricity"],
            [54, 35],
        )
        self.assertEqual(
            result["quota_raw"]["unit_area_total_electricity"],
            [80, 50],
        )

    def test_5077_correction_uses_annual_use_hours_and_ten_square_metres(self):
        project = self._project(
            electricity_kwh=50000,
            heating_gas_m3=3000,
        )
        project.update({
            "subtype": "agency_office",
            "correction": {
                "annual_use_hours": 1250,
                "area_per_person": 20,
            },
        })
        result = self.module.compute_project(project)[0]

        self.assertEqual(result["correction"]["annual_use_hours"], 1250)
        self.assertAlmostEqual(result["correction"]["alpha1_use_hours"], 0.65)
        self.assertAlmostEqual(result["correction"]["alpha2_people_density"], 0.85)
        self.assertAlmostEqual(result["correction"]["factor"], 0.5525)

    def test_5077_heating_electricity_uses_the_fixed_equal_value_coefficient(self):
        project = self._project(
            electricity_kwh=50000,
            heating_electricity_kwh=1000,
        )
        project["subtype"] = "agency_office"
        result = self.module.compute_project(project)[0]

        self.assertAlmostEqual(result["notes"]["heating_energy_kgce"], 300.0)

    def test_5077_purchased_heat_requires_an_explicit_equivalent_coefficient(self):
        project = self._project(
            electricity_kwh=50000,
            heating_heat_gj=100,
        )
        project["subtype"] = "agency_office"

        with self.assertRaisesRegex(ValueError, "heating_heat_equivalent"):
            self.module.compute_project(project)

    def test_5077_purchased_heat_uses_the_supplied_equivalent_coefficient(self):
        project = self._project(
            electricity_kwh=50000,
            heating_heat_gj=100,
            heating_heat_equivalent_electricity_kwh_per_gj=64,
        )
        project["subtype"] = "agency_office"
        result = self.module.compute_project(project)[0]

        self.assertAlmostEqual(
            result["values"]["unit_area_total_electricity"],
            5.64,
        )

    def test_hospital_code_d4_uses_secondary_or_lower_specialty_table(self):
        project = self._project(electricity_kwh=50000, heating_gas_m3=3000)
        project.update({
            "subtype": "hospital",
            "hospital_level": "二级及以下",
            "hospital_specialty": "专科",
            "beds": 100,
        })
        result = self.module.compute_project(project)[0]
        self.assertEqual(result["standard_table"], "表7.0.2-4")


class ZhejiangPublicInstitutionCalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            "zhejiang_public_institution_under_test",
            ZHEJIANG_PUBLIC_INSTITUTION_SCRIPT,
        )

    def test_university_uses_three_tiers_and_annualized_energy(self):
        result = self.module.compute_project({
            "subtype": "university",
            "area_m2": 100000,
            "people": 20000,
            "years": [{
                "year": 2024,
                "electricity_kwh": 3000000,
                "gas_m3": 100000,
            }],
        })[0]

        self.assertEqual(result["standard_id"], "DB33/T 737-2021")
        self.assertEqual(
            result["quota"]["unit_area_energy"],
            [7.0, 4.5, 2.5],
        )
        self.assertAlmostEqual(
            result["values"]["unit_area_energy"],
            4.90,
            places=2,
        )

    def test_hospital_uses_comparable_metric_and_correction(self):
        result = self.module.compute_project({
            "subtype": "hospital",
            "hospital_level": "三级",
            "area_m2": 100000,
            "people": 5000,
            "outpatient_visits": 3500000,
            "open_beds": 1100,
            "years": [{
                "year": 2024,
                "electricity_kwh": 10000000,
                "outpatient_visits": 3500000,
                "open_beds": 1100,
            }],
        })[0]

        self.assertEqual(result["standard_id"], "DB33/T 738-2021")
        self.assertIn("comparable_unit_area_energy", result["values"])
        self.assertAlmostEqual(
            result["notes"]["medical_correction"]["product"],
            1.44,
            places=6,
        )

    def test_primary_hospital_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "仅适用于二级及以上"):
            self.module.compute_project({
                "subtype": "hospital",
                "hospital_level": "一级",
                "area_m2": 10000,
                "people": 300,
                "years": [{"year": 2024, "electricity_kwh": 100000}],
            })

    def test_adult_university_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "成人高校、自考高校不得套用"):
            self.module.compute_project({
                "subtype": "university",
                "specific_type": "成人高校",
                "area_m2": 10000,
                "people": 1000,
                "years": [{"year": 2024, "electricity_kwh": 100000}],
            })

    def test_hospital_level_is_not_guessed_from_the_name(self):
        with self.assertRaisesRegex(ValueError, "不得根据单位名称猜测"):
            self.module.compute_project({
                "subtype": "hospital",
                "unit_name": "某市三级综合医院",
                "area_m2": 10000,
                "people": 1000,
                "years": [{"year": 2024, "electricity_kwh": 100000}],
            })


if __name__ == "__main__":
    unittest.main()

