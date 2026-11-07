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


def write_project(
    path: Path,
    *,
    unit_type: str,
    province: str,
    unit_func: str | None = None,
    children_func: str | None = None,
    public_building_subtype: str | None = None,
    buildings: list[dict] | None = None,
    base_period: str | None = None,
    energy_yearly: list[dict] | None = None,
):
    (path / "chapter_md").mkdir(parents=True)
    if unit_func is None:
        if unit_type == "公共建筑" and "浙江" in province:
            unit_func = "zj_hotel"
            children_func = "zj_hotel_5" if children_func is None else children_func
        elif unit_type == "公共建筑":
            unit_func = "C"
            children_func = "" if children_func is None else children_func
        elif unit_type == "公共机构" and "浙江" in province:
            unit_func = "zj_college"
            children_func = "" if children_func is None else children_func
        else:
            unit_func = "E"
            children_func = "A" if children_func is None else children_func
    data = {
        "base": {
            "unit_name": "长三角研究院创新大厦AB座",
            "unit_type": unit_type,
            "province": province,
            "unit_func": unit_func,
            "children_func": children_func or "",
            "building_area": 95000,
            "people_count": 1238,
            "institution_category": "科研办公",
            "base_period": base_period or "",
        },
        "buildings": buildings or [],
        "energy_yearly": energy_yearly or [],
        "images": [],
    }
    if unit_type == "公共建筑":
        data["public_building"] = {
            "subtype": public_building_subtype
            or ("hotel" if "浙江" in province else "business_office")
        }
    if unit_type == "公共建筑" and "山东" in province:
        subtype = public_building_subtype or "business_office"
        indicators = {
            "family": "公共建筑",
            "region": "山东",
            "year": 2024,
            "public_building": {
                "subtype": subtype,
                "region": "山东",
                "results": [{"year": 2024}],
            },
        }
        if subtype == "agency_office":
            indicators.update({
                "standard_status": "废止",
                "legacy_override": True,
                "abolished_at": "2024-10-09",
                "standard_disclosure": (
                    "DB37/T 5077-2016标准已于2024-10-09废止；"
                    "本项目因暂无现行替代标准，按批准规则作过渡兼容沿用。"
                ),
            })
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
                "public_building": {
                    "subtype": public_building_subtype or "hotel",
                    "star": "5",
                },
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

    def test_zhejiang_public_building_context_injects_ch1_period_and_basis_contract(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="浙江",
                unit_func="zj_hotel",
                children_func="zj_hotel_3",
                public_building_subtype="hotel",
                buildings=[
                    {
                        "name": "专家公寓",
                        "cooling_source": "空气源热泵",
                        "heating_source": "空气源热泵",
                        "water_system": "市政供水",
                    }
                ],
                base_period="2024年1月—2024年12月",
                energy_yearly=[
                    {
                        "year": 2024,
                        "electricity_kwh": 921039,
                        "water_m3": 7223,
                    }
                ],
            )
            data_path = project / "data.json"
            data = json.loads(data_path.read_text(encoding="utf-8"))
            data["base"]["institution_category"] = "公寓"
            data["base"]["specific_type"] = "专家公寓"
            data_path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                "基准期：2024年1月1日—2024年12月31日",
                context,
            )
            self.assertNotIn("能耗对标基准期", context)
            self.assertIn("### 1.6 审计依据（动态适用）", context)
            self.assertIn(
                "- 参照《旅游饭店单位综合能耗限额及计算方法》；",
                context,
            )
            self.assertIn(
                "- 《公共建筑节能改造技术规范》（JGJ 176-2009）；",
                context,
            )
            self.assertIn(
                "- 《浙江省用（取）水定额》（2019年）；",
                context,
            )
            self.assertIn(
                "- 调研资料及其他相关资料。",
                context,
            )
            self.assertNotIn("- 国家法规与导则", context)
            self.assertNotIn("- 浙江省规章", context)

    def test_zhejiang_public_building_context_injects_fixed_16_field_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            unresolved_address = "{" * 2 + "ADDRESS_" + "x" + "}" * 2
            write_project(
                project,
                unit_type="公共建筑",
                province="浙江",
                buildings=[
                    {
                        "name": "专家公寓",
                        "area": 19418.41,
                        "address": unresolved_address,
                        "year": 2022,
                        "floors": "地上19层",
                        "height": "66.95",
                        "structure": "钢筋混凝土框架核心筒",
                        "window_type": "中空双层玻璃窗",
                        "cooling_source": "空气源热泵",
                        "heating_source": "空气源热泵",
                        "cooling_terminal": "风机盘管",
                        "heating_terminal": "风机盘管",
                        "insulation": "外墙保温",
                        "hot_water": "空气源热泵热水系统",
                        "water_system": "市政供水",
                        "monitoring": "有",
                    },
                    {
                        "name": "创新大厦AB座",
                        "area": 95000,
                        "address": "创新路1号",
                        "year": 2018,
                        "floors": "地上12层",
                        "height": "48",
                        "structure": "钢筋混凝土框架",
                        "window_type": "中空玻璃",
                        "cooling_source": "冷水机组",
                        "heating_source": "市政热力",
                        "cooling_terminal": "风机盘管",
                        "heating_terminal": "散热器",
                        "insulation": "外墙保温",
                        "hot_water": "电热水器",
                        "water_system": "市政供水",
                        "monitoring": "有",
                    },
                ],
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            section_start = context.index(
                "### 2.2 建筑信息统计表（固定 16 字段、4 列、8 行）"
            )
            section = context[section_start:]
            self.assertIn("表2.1 专家公寓建筑信息统计", section)
            self.assertIn("表2.2 创新大厦AB座建筑信息统计", section)
            self.assertIn(
                "| 建筑地址 | — | 投用年份 | 2022 |", section
            )
            self.assertIn(
                "| 建筑结构形式 | 钢筋混凝土框架核心筒 | "
                "建筑透明围护结构 | 中空双层玻璃窗 |",
                section,
            )
            self.assertIn("生活热水系统", section)
            self.assertIn("能耗在线监测系统", section)
            self.assertNotIn("建筑外窗类型", section)
            self.assertNotIn("ADDRESS_x", section)
            self.assertIn("缺失字段：建筑地址", section)

    def test_zhejiang_public_institution_context_omits_public_building_table_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(project, unit_type="公共机构", province="浙江")

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("固定 16 字段、4 列、8 行", context)
            self.assertNotIn("建筑透明围护结构", context)

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
            self.assertNotIn("### 1.6 审计依据（动态适用）", context)

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
            self.assertNotIn("### 1.6 审计依据（动态适用）", context)

    def test_shandong_agency_office_context_discloses_obsolete_5077(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="山东",
                unit_func="B",
                children_func="",
                public_building_subtype="agency_office",
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("| dictionary_type | public_build_type |", context)
            self.assertIn(
                "| public_building_subtype | agency_office（机关办公） |",
                context,
            )
            self.assertIn("| standard_id | DB37/T 5077-2016 |", context)
            self.assertIn("| standard_status | 废止 |", context)
            self.assertIn("| legacy_override | true |", context)
            self.assertIn(
                "DB37/T 5077-2016标准已于2024-10-09废止；"
                "本项目因暂无现行替代标准，按批准规则作过渡兼容沿用。",
                context,
            )

    def test_zhejiang_public_building_context_exposes_dictionary_and_star(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="浙江",
                unit_func="zj_hotel",
                children_func="zj_hotel_5",
                public_building_subtype="hotel",
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("| dictionary_type | zj_public_build_type |", context)
            self.assertIn(
                "| public_building_subtype | hotel（旅游饭店） |",
                context,
            )
            self.assertIn("| star | 5（五星级） |", context)
            self.assertIn("| standard_id | DB33/T 760-2023 |", context)
            self.assertIn(
                "| standard_name | 《旅游饭店单位综合能耗限额及计算方法》 |",
                context,
            )
            self.assertIn("不得单独用 DB33/T 760-2023 代替标准名称", context)

    def test_hotel_writing_context_lists_only_comparable_energy_and_water(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="浙江",
                unit_func="zj_hotel",
                children_func="zj_hotel_5",
                public_building_subtype="hotel",
            )
            indicators_path = project / "indicators.json"
            indicators = json.loads(
                indicators_path.read_text(encoding="utf-8")
            )
            indicators.update(
                {
                    "unit_energy": {
                        "kgce_per_m2": 6.0,
                        "benchmark": None,
                    },
                    "unit_comparable_energy": {
                        "kgce_per_m2": 5.4,
                        "benchmark": {
                            "约束值": 25.0,
                            "基准值": 18.0,
                            "引导值": 12.0,
                            "标准": "DB33/T 760-2023",
                            "评价结果": "低于引导值",
                        },
                    },
                    "water_indicator": {
                        "m3_per_bed": 100.0,
                        "benchmark": {
                            "通用值": 350.0,
                            "先进值": 216.0,
                            "标准": "浙江省用（取）水定额（2019）",
                            "评价结果": "低于先进值",
                            "行业代码": "H6110",
                            "类别名称": "旅游饭店",
                            "分项名称": (
                                "四、五星级（含白金五星级或具有同等规模、"
                                "质量、水平）"
                            ),
                            "定额单位": "m³/(床·年)",
                        },
                    },
                }
            )
            indicators_path.write_text(
                json.dumps(indicators, ensure_ascii=False),
                encoding="utf-8",
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("| 单位可比综合能耗 |", context)
            self.assertIn("| 单位床年用水量 |", context)
            self.assertIn("| 25.0 / 18.0 / 12.0 |", context)
            self.assertIn(
                "浙江省用（取）水定额（2019）（H6110 旅游饭店—"
                "四、五星级（含白金五星级或具有同等规模、质量、水平））",
                context,
            )
            self.assertIn("| 350.0 / 216.0 |", context)
            self.assertIn("| 低于引导值 |", context)
            self.assertNotIn("3级（限额值）", context)
            self.assertNotIn("低于1级（先进值）", context)
            self.assertNotIn("| 单位综合能耗（参考） |", context)

    def test_hotel_writing_context_normalizes_legacy_760_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="浙江",
                unit_func="zj_hotel",
                children_func="zj_hotel_5",
                public_building_subtype="hotel",
            )
            indicators_path = project / "indicators.json"
            indicators = json.loads(
                indicators_path.read_text(encoding="utf-8")
            )
            indicators.update(
                {
                    "unit_comparable_energy": {
                        "kgce_per_m2": 5.4,
                        "benchmark": {
                            "3级（限额值）": 25.0,
                            "2级（约束值）": 18.0,
                            "1级（先进值）": 12.0,
                            "标准": "DB33/T 760-2023",
                            "评价结果": "低于1级（先进值）",
                        },
                    },
                    "water_indicator": {
                        "m3_per_bed": 100.0,
                        "benchmark": {
                            "通用值": 125.0,
                            "先进值": 70.0,
                            "标准": "浙江省用（取）水定额（2019）",
                            "评价结果": "低于先进值",
                        },
                    },
                }
            )
            indicators_path.write_text(
                json.dumps(indicators, ensure_ascii=False),
                encoding="utf-8",
            )

            code = WRITING_CONTEXT.main([str(project), "--quiet"])

            self.assertEqual(code, 0)
            context = (project / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("| 25.0 / 18.0 / 12.0 |", context)
            self.assertIn("| 低于引导值 |", context)
            self.assertNotIn("| 低于1级（先进值） |", context)


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
    def test_760_native_fraction_formula_is_accepted(self):
        formula_xml = (
            "<m:oMath>"
            "<m:sSub><m:e><m:r><m:t>E</m:t></m:r></m:e>"
            "<m:sub><m:r><m:t>kd</m:t></m:r></m:sub></m:sSub>"
            "<m:r><m:t>=</m:t></m:r>"
            "<m:f><m:num><m:r><m:t>Ej</m:t></m:r></m:num>"
            "<m:den><m:r><m:t>a1×a2×⋯×am</m:t></m:r></m:den>"
            "</m:f></m:oMath>"
        )

        self.assertTrue(
            DOCX_ASSERTS._has_760_comparable_formula_object(formula_xml)
        )

    def test_hotel_ch5_accepts_comparable_energy_as_metric_531(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量"
        )

        self.assertTrue(checks["pb_ch5_metrics"], details)

    def test_hotel_ch5_rejects_legacy_three_metric_numbering(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "5.3.1 单位综合能耗 "
            "5.3.2 单位可比综合能耗 "
            "5.3.3 单位床年用水量"
        )

        self.assertFalse(checks["pb_ch5_metrics"], details)

    def test_hotel_ch5_requires_full_standard_name_in_chapter_text(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量 "
            "低于该标准表1三星级及以下分项对应的引导值"
        )

        self.assertFalse(checks["pb_ch5_full_standard_name"], details)
        self.assertIn("旅游饭店单位综合能耗限额及计算方法", details[
            "pb_ch5_full_standard_name"
        ])

    def test_hotel_ch5_accepts_full_standard_name(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量 "
            "低于《旅游饭店单位综合能耗限额及计算方法》"
            "（DB33/T 760-2023）表1三星级及以下分项对应的引导值"
        )

        self.assertTrue(checks["pb_ch5_full_standard_name"], details)

    def test_valid_public_building_checks_cover_appendix_and_db33_only(self):
        checks, details = DOCX_ASSERTS.public_building_checks(
            "第1章 能源审计执行概要 1.3 审计周期 "
            "审计时间 2025年6月—2025年7月 "
            "审计周期 2022年1月1日—2024年12月31日 "
            "基准期 2024年1月1日—2024年12月31日 "
            "1.6 审计依据 "
            "《行政机关、场馆能耗定额及计算方法》（DB33/T 736-2021） "
            "《公共建筑节能改造技术规范》（JGJ 176-2009） "
            "调研资料及其他相关资料。 "
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

    def test_public_building_ch1_contract_rejects_wrong_period_and_long_basis(self):
        invalid_text = (
            "第1章 能源审计执行概要 1.3 审计周期 "
            "审计时间 2025年6月—2025年7月 "
            "审计周期 2022年1月1日—2024年12月31日 "
            "能耗对标基准期 2024年1月1日—2024年12月31日 "
            "1.6 审计依据 国家法规与导则 "
            "《公共建筑节能改造技术规范》（JGJ 176-2009） "
            "调研资料及其他相关资料。 "
            "2022年—2024年电、水能源账单，用能设备台账，现场勘察记录及"
            "被审计单位提供的其他相关资料。 "
            "第2章 建筑概况 "
            "6.1 用电系统运行分析 6.2 用水系统运行分析 6.3 其他用能系统运行分析 "
            "5.3.1 单位建筑面积能耗 5.3.2 常规用能系统单位建筑面积电耗 "
            "5.3.3 人均综合能耗 5.3.4 人均电耗 5.3.5 单位用水量 "
            "0.1229 DB33/T 736-2021 "
            "附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数"
        )

        checks, details = DOCX_ASSERTS.public_building_checks(invalid_text)

        self.assertFalse(checks["pb_ch1_period"])
        self.assertFalse(checks["pb_ch1_basis_list"])
        self.assertFalse(checks["pb_ch1_research_compact"])
        self.assertIn("基准期", details["pb_ch1_period"])
        self.assertIn("分组标题", details["pb_ch1_basis_list"])
        self.assertIn("调研资料及其他相关资料", details["pb_ch1_research_compact"])

    def test_public_building_ch1_contract_accepts_dynamic_quota_standard(self):
        text = (
            "目录 1.6 审计依据 3 第2章 建筑概况 4 "
            "第1章 能源审计执行概要 1.3 审计周期 "
            "审计时间 2025年6月—2025年7月 "
            "审计周期 2022年1月1日—2024年12月31日 "
            "基准期 2024年1月1日—2024年12月31日 "
            "1.6 审计依据 "
            "参照《旅游饭店单位综合能耗限额及计算方法》 "
            "《公共建筑节能改造技术规范》（JGJ 176-2009） "
            "调研资料及其他相关资料。 "
            "第2章 建筑概况 "
            "6.1 用电系统运行分析 6.2 用水系统运行分析 6.3 其他用能系统运行分析 "
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量 "
            "0.1229 附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数"
            " 5.3 定额标准通用值 不满足用水定额考核要求"
        )

        checks, details = DOCX_ASSERTS.public_building_checks(text)

        self.assertTrue(checks["pb_ch1_period"], details)
        self.assertTrue(checks["pb_ch1_basis_list"], details)
        self.assertTrue(checks["pb_ch1_research_compact"], details)

    def test_public_building_ch1_contract_rejects_bare_hotel_standard_id(self):
        text = (
            "第1章 能源审计执行概要 1.3 审计周期 "
            "审计时间 2025年6月—2025年7月 "
            "审计周期 2022年1月1日—2024年12月31日 "
            "基准期 2024年1月1日—2024年12月31日 "
            "1.6 审计依据 "
            "参照 DB33/T 760-2023 "
            "《公共建筑节能改造技术规范》（JGJ 176-2009） "
            "调研资料及其他相关资料。 "
            "第2章 建筑概况 "
            "6.1 用电系统运行分析 6.2 用水系统运行分析 6.3 其他用能系统运行分析 "
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量 "
            "0.1229 附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数"
        )

        checks, details = DOCX_ASSERTS.public_building_checks(text)

        self.assertFalse(checks["pb_ch1_basis_list"], details)

    def test_water_quota_standard_title_is_not_treated_as_group_heading(self):
        text = (
            "第1章 能源审计执行概要 1.3 审计周期 "
            "审计时间 2025年6月—2025年7月 "
            "审计周期 2022年1月1日—2024年12月31日 "
            "基准期 2024年1月1日—2024年12月31日 "
            "1.6 审计依据 "
            "《旅游饭店单位综合能耗限额及计算方法》 "
            "《公共建筑节能改造技术规范》（JGJ 176-2009） "
            "《浙江省用水定额》（2019年） "
            "调研资料及其他相关资料。 "
            "第2章 建筑概况 "
            "6.1 用电系统运行分析 6.2 用水系统运行分析 6.3 其他用能系统运行分析 "
            "5.3.1 单位可比综合能耗 5.3.2 单位床年用水量 "
            "0.1229 附录1：建筑能耗数据信息表 附录2：各种能源折标准煤参考系数"
        )

        checks, details = DOCX_ASSERTS.public_building_checks(text)

        self.assertTrue(checks["pb_ch1_basis_list"], details)

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
            "pb_ch1_period",
            "pb_ch1_basis_list",
            "pb_ch1_research_compact",
            "pb_ch2_title",
            "pb_ch6_structure",
            "pb_ch5_metrics",
            "pb_ch5_760_formula",
            "pb_ch5_760_tiers",
            "pb_ch5_full_standard_name",
            "pb_ch5_water_quota",
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
    def test_docx_asserts_detect_public_building_subtype_from_indicators(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            write_project(
                project,
                unit_type="公共建筑",
                province="山东",
                unit_func="B",
                children_func="",
                public_building_subtype="agency_office",
            )

            subtype = DOCX_ASSERTS.detect_public_building_subtype(
                str(project / "report.docx")
            )

            self.assertEqual(subtype, "agency_office")

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

    def test_shandong_agency_office_5077_report_passes_with_disclosure(self):
        checks, details = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "单位建筑面积总等效电耗（含供暖） DB37/T 5077-2016 "
            "DB37/T 5077-2016标准已于2024-10-09废止；"
            "本项目因暂无现行替代标准，按批准规则作过渡兼容沿用。 "
            "约束值 先进值 电力折标系数 0.1229",
            subtype="agency_office",
        )

        self.assertTrue(all(checks.values()), details)

    def test_shandong_agency_office_requires_obsolete_standard_disclosure(self):
        checks, _ = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "单位建筑面积总等效电耗（含供暖） DB37/T 5077-2016 "
            "约束值 先进值 0.1229",
            subtype="agency_office",
        )

        self.assertFalse(checks["sd_pb_legacy_disclosure"])

    def test_shandong_5077_is_rejected_for_another_subtype(self):
        checks, _ = DOCX_ASSERTS.shandong_public_building_checks(
            "第2章 建筑概况 单位建筑面积供暖能耗 单位建筑面积非供暖电耗 "
            "DB37/T 5077-2016 约束值 先进值 0.1229",
            subtype="business_office",
        )

        self.assertFalse(checks["sd_pb_subtype_standard"])

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

