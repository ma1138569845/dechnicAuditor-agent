import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WRITING_CONTEXT = load_module(
    "prepare_writing_context_family_under_test",
    Path(__file__).resolve().parents[1] / "prepare_writing_context.py",
)
DOCX_BUILDER = load_module(
    "build_docx_family_under_test",
    Path(__file__).resolve().parents[3]
    / "energy-audit-report"
    / "scripts"
    / "build_energy_audit_docx.py",
)
DOCX_ASSERTS = load_module(
    "docx_asserts_family_under_test",
    Path(__file__).resolve().parents[3]
    / "energy-audit-report"
    / "scripts"
    / "ea_docx_asserts.py",
)


def write_project(path: Path, *, unit_type: str, province: str):
    (path / "chapter_md").mkdir(parents=True)
    data = {
        "base": {
            "unit_name": "长三角研究院创新大厦AB座",
            "unit_type": unit_type,
            "province": province,
            "building_area": 95000,
            "people_count": 1238,
            "institution_category": "科研办公",
        },
        "images": [],
    }
    if unit_type == "公共建筑" and "山东" in province:
        indicators = {
            "family": "公共建筑",
            "region": "山东",
            "year": 2024,
            "public_building": {
                "subtype": "business_office",
                "region": "山东",
                "results": [{"year": 2024}],
            },
        }
    elif unit_type == "公共机构" and "浙江" in province:
        indicators = {
            "family": "公共机构",
            "region": "浙江",
            "year": 2024,
            "public_institution": {
                "region": "浙江",
                "subtype": "university",
                "results": [{"year": 2024}],
            },
        }
    else:
        indicators = {
            "family": "公共建筑",
            "year": 2024,
            "public_building": {"subtype": "office"},
        }
    (path / "data.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    (path / "indicators.json").write_text(
        json.dumps(indicators, ensure_ascii=False), encoding="utf-8"
    )


class WritingContextFamilyTests(unittest.TestCase):
    def test_indicators_family_cannot_override_data_json_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共机构", province="浙江")
            indicators_path = project / "indicators.json"
            indicators = json.loads(
                indicators_path.read_text(encoding="utf-8")
            )
            indicators["family"] = "公共建筑"
            indicators_path.write_text(
                json.dumps(indicators, ensure_ascii=False), encoding="utf-8"
            )

            family = WRITING_CONTEXT.resolve_project_family(
                {"unit_type": "公共机构", "province": "浙江"},
                indicators,
            )

            self.assertEqual(family.family, "public_institution")

    def test_zhejiang_public_building_context_selects_family_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="浙江")

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("公共建筑（浙江）", context)
            self.assertIn(
                "families/public-building/chapter-guides-1-4.md", context
            )
            self.assertIn(
                "families/public-building/blueprint.md", context
            )

    def test_shandong_public_building_context_uses_only_shandong_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="山东")

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("公共建筑（山东）", context)
            self.assertIn("DB37/T 5078-2024", context)
            self.assertIn("评价只有 **约束值、先进值** 两档", context)
            self.assertIn("无山东公共建筑专属蓝本", context)
            self.assertIn("不得借用浙江蓝本", context)

    def test_zhejiang_public_institution_context_uses_its_own_standard_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共机构", province="浙江")

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("公共机构（浙江）", context)
            self.assertIn("DB33/T 736-2021", context)
            self.assertIn("DB33/T 737-2021", context)
            self.assertIn("DB33/T 738-2021", context)
            self.assertIn("评价统一为约束值、基准值、引导值三档", context)
            self.assertIn("电力折标为 0.1229 kgce/kWh", context)
            self.assertIn("无浙江公共机构专属蓝本", context)


class AssemblyFamilyContractTests(unittest.TestCase):
    def test_assembly_resolves_zhejiang_public_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="浙江")

            context = DOCX_BUILDER.resolve_project_family(str(project))

            self.assertEqual(context.family, "public_building")
            self.assertEqual(context.region, "浙江")

    def test_assembly_resolves_shandong_public_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="山东")

            context = DOCX_BUILDER.resolve_project_family(str(project))

            self.assertEqual(context.family, "public_building")
            self.assertEqual(context.region, "山东")
            self.assertTrue(context.is_shandong_public_building)

    def test_assembly_rejects_missing_second_appendix(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="浙江")
            for number in range(1, 9):
                (project / "chapter_md" / f"ch{number}.md").write_text(
                    f"# 第{number}章\n", encoding="utf-8"
                )
            (project / "chapter_md" / "appendix.md").write_text(
                "# 附录：\n\n附录1：建筑能耗数据信息表\n", encoding="utf-8"
            )
            context = DOCX_BUILDER.resolve_project_family(str(project))

            with self.assertRaisesRegex(
                DOCX_BUILDER.ReportFamilyContractError, "附录2"
            ):
                DOCX_BUILDER.validate_family_inputs(str(project), context)

    def test_assembly_rejects_appendix_without_required_formal_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="浙江")
            for number in range(1, 9):
                (project / "chapter_md" / f"ch{number}.md").write_text(
                    f"# 第{number}章\n", encoding="utf-8"
                )
            (project / "chapter_md" / "appendix.md").write_text(
                "# 附录：\n\n附录1：其他表\n附录2：其他系数表\n",
                encoding="utf-8",
            )
            context = DOCX_BUILDER.resolve_project_family(str(project))

            with self.assertRaisesRegex(
                DOCX_BUILDER.ReportFamilyContractError, "命名不符"
            ):
                DOCX_BUILDER.validate_family_inputs(str(project), context)

    def test_shandong_public_building_does_not_require_zhejiang_appendices(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="山东")
            for number in range(1, 9):
                (project / "chapter_md" / f"ch{number}.md").write_text(
                    f"# 第{number}章\n", encoding="utf-8"
                )
            context = DOCX_BUILDER.resolve_project_family(str(project))

            DOCX_BUILDER.validate_family_inputs(str(project), context)

    def test_assembly_rejects_unsupported_public_building_province(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="江苏")

            with self.assertRaisesRegex(
                DOCX_BUILDER.ReportFamilyContractError, "目前仅接入山东、浙江"
            ):
                DOCX_BUILDER.resolve_project_family(str(project))


class PublicBuildingAssertionContractTests(unittest.TestCase):
    def test_valid_public_building_checks_cover_appendix_and_db33_only(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "第2章 建筑概况 "
            "6.1 用电系统运行分析 6.2 用水系统运行分析 6.3 其他用能系统运行分析 "
            "5.3.1 单位建筑面积能耗 5.3.2 常规用能系统单位建筑面积电耗 "
            "5.3.3 人均综合能耗 5.3.4 人均电耗 5.3.5 单位用水量 "
            "电力折标系数 0.1229 DB33/T 736-2021 "
            "附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数"
        )

        self.assertTrue(all(checks.values()), details)
        self.assertTrue(checks["pb_appendix1"])
        self.assertTrue(checks["pb_no_db37"])

    def test_wrong_appendix_and_db37_fail(self):
        checks, _ = DOCX_ASSERTS.public_building_checks(
            "第2章 建筑概况 6.1 用电系统运行分析 6.2 用水系统运行分析 "
            "6.3 其他用能系统运行分析 5.3.1 单位建筑面积能耗 "
            "5.3.2 常规用能系统单位建筑面积电耗 5.3.3 人均综合能耗 "
            "5.3.4 人均电耗 5.3.5 单位用水量 0.1229 DB37/T 2672-2019 "
            "附录2 各种能源折标准煤参考系数"
        )

        self.assertFalse(checks["pb_appendix1"])
        self.assertFalse(checks["pb_no_db37"])

    def test_public_building_rejects_appendix3(self):
        checks, _ = DOCX_ASSERTS.public_building_checks(
            "第2章 建筑概况 6.1 用电系统运行分析 6.2 用水系统运行分析 "
            "6.3 其他用能系统运行分析 5.3.1 单位建筑面积能耗 "
            "5.3.2 常规用能系统单位建筑面积电耗 5.3.3 人均综合能耗 "
            "5.3.4 人均电耗 5.3.5 单位用水量 0.1229 "
            "附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数 "
            "附录3：多余附录"
        )

        self.assertFalse(checks["pb_no_appendix3"])

    def test_public_building_checks_are_not_downgraded_to_warnings(self):
        blocking = {
            "pb_ch2_title",
            "pb_ch6_structure",
            "pb_ch5_metrics",
            "pb_coefficient",
            "pb_appendix1",
            "pb_appendix2",
            "pb_no_appendix3",
            "pb_no_db37",
            "pb_no_public_institution",
        }
        self.assertTrue(blocking.isdisjoint(DOCX_ASSERTS.P1_NONBLOCKING))
        self.assertIn("apx2_landscape", DOCX_ASSERTS.PUBLIC_BUILDING_SKIP)


class RegionalStandardAssertionTests(unittest.TestCase):
    def test_valid_shandong_public_building_report_passes(self):
        checks, details = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 第5章 能源资源消费指标 单位建筑面积供暖能耗 "
            "单位建筑面积非供暖电耗 DB37/T 5078-2024 约束值 先进值 "
            "电力折标系数 0.1229"
        )

        self.assertTrue(all(checks.values()), details)

    def test_shandong_public_building_rejects_zhejiang_three_tiers(self):
        checks, _ = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "DB37/T 5078-2024 DB33/T 736-2021 约束值 基准值 引导值 先进值 "
            "电力折标系数 0.31"
        )

        self.assertFalse(checks["sd_pb_two_tiers"])
        self.assertFalse(checks["sd_pb_no_db33"])
        self.assertFalse(
            checks["sd_pb_no_legacy_public_institution_coefficient"]
        )

    def test_shandong_public_building_requires_one_subtype_standard(self):
        checks, _ = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "DB37/T 5078-2024 DB37/T 5079-2024 约束值 先进值 0.1229"
        )

        self.assertFalse(checks["sd_pb_single_standard"])

    def test_shandong_hospital_requires_bed_metric(self):
        checks, _ = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "DB37/T 5079-2024 约束值 先进值 0.1229"
        )
        self.assertFalse(checks["sd_pb_hospital_metric"])

        checks, details = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "单位床位非供暖电耗 DB37/T 5079-2024 约束值 先进值 0.1229"
        )
        self.assertTrue(all(checks.values()), details)

    def test_valid_zhejiang_public_institution_report_passes(self):
        checks, details = DOCX_ASSERTS.zhejiang_public_institution_checks(
            "第2章 公共机构概况 单位建筑面积能耗 人均综合能耗 "
            "常规用能系统单位建筑面积电耗 DB33/T 737-2021 "
            "约束值 基准值 引导值 电力折标系数 0.1229"
        )

        self.assertTrue(all(checks.values()), details)

    def test_zhejiang_public_institution_rejects_shandong_values(self):
        checks, _ = DOCX_ASSERTS.zhejiang_public_institution_checks(
            "单位建筑面积能耗 人均综合能耗 常规用能系统单位建筑面积电耗 "
            "DB33/T 738-2021 DB37/T 5079-2024 约束值 基准值 引导值 "
            "电力折标系数 0.31 单位可比综合能耗"
        )

        self.assertFalse(checks["zj_pi_coefficient"])
        self.assertFalse(checks["zj_pi_no_db37"])
        self.assertFalse(checks["zj_pi_no_public_building_subtype"])

    def test_zhejiang_hospital_requires_comparable_metric(self):
        checks, _ = DOCX_ASSERTS.zhejiang_public_institution_checks(
            "单位建筑面积能耗 人均综合能耗 常规用能系统单位建筑面积电耗 "
            "DB33/T 738-2021 约束值 基准值 引导值 0.1229"
        )
        self.assertFalse(checks["zj_pi_hospital_metric"])

        checks, details = DOCX_ASSERTS.zhejiang_public_institution_checks(
            "可比单位建筑面积能耗 人均综合能耗 常规用能系统单位建筑面积电耗 "
            "DB33/T 738-2021 约束值 基准值 引导值 0.1229"
        )
        self.assertTrue(all(checks.values()), details)

    def test_zhejiang_public_institution_rejects_shandong_metrics(self):
        checks, _ = DOCX_ASSERTS.zhejiang_public_institution_checks(
            "单位建筑面积能耗 人均综合能耗 常规用能系统单位建筑面积电耗 "
            "单位建筑面积供暖能耗 DB33/T 737-2021 "
            "约束值 基准值 引导值 0.1229"
        )
        self.assertFalse(checks["zj_pi_no_shandong_metrics"])


class ReportFamilyCliErrorTests(unittest.TestCase):
    def test_auto_family_rejection_is_not_reported_as_docx_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共建筑", province="江苏")
            docx_path = project / "report.docx"
            docx_path.write_bytes(b"")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = DOCX_ASSERTS.main([str(docx_path)])

            self.assertEqual(code, 3)
            self.assertIn("report_family", stdout.getvalue())
            self.assertNotIn("zip_ok", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

