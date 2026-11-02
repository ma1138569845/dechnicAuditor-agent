from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.energy_audit import public_building_audit_basis as basis_module


def project_data(
    *,
    subtype: str,
    category: str,
    specific_type: str = "",
    buildings: list[dict] | None = None,
    energy_yearly: list[dict] | None = None,
    equipment: list[dict] | None = None,
) -> dict:
    return {
        "base": {
            "unit_name": "测试公共建筑",
            "province": "浙江",
            "institution_category": category,
            "specific_type": specific_type,
        },
        "public_building": {"subtype": subtype},
        "buildings": buildings or [],
        "energy_yearly": energy_yearly or [],
        "equipment": equipment or [],
    }


def citations(data: dict, *, include_retrofit: bool = True) -> tuple[str, ...]:
    return tuple(
        item.citation
        for item in basis_module.select_public_building_audit_basis(
            data, include_retrofit=include_retrofit
        )
    )


class PublicBuildingAuditBasisTests(unittest.TestCase):
    def test_apartment_references_hotel_standard_and_never_claims_office_standard(self):
        data = project_data(
            subtype="hotel",
            category="公寓",
            specific_type="专家公寓",
            buildings=[
                {
                    "cooling_source": "空气源热泵",
                    "heating_source": "空气源热泵",
                    "water_system": "市政供水",
                }
            ],
            energy_yearly=[
                {"year": 2024, "electricity_kwh": 921039, "water_m3": 7223}
            ],
        )

        rendered = basis_module.render_public_building_audit_basis(data)

        self.assertIn(
            "- 参照《旅游饭店单位综合能耗限额及计算方法》；",
            rendered,
        )
        self.assertNotIn("DB33/T 760-2023", rendered)
        self.assertFalse(any("DB33/T 736-2021" in line for line in rendered))
        self.assertIn(
            "- 《浙江省用（取）水定额》（2019年）；",
            rendered,
        )
        self.assertIn(
            "- 《公共建筑节能改造技术规范》（JGJ 176-2009）；",
            rendered,
        )

    def test_research_office_references_office_venue_standard_not_hotel_standard(self):
        data = project_data(
            subtype="business_office",
            category="科研办公",
            buildings=[{"cooling_source": "冷水机组"}],
        )

        rendered = basis_module.render_public_building_audit_basis(data)

        self.assertIn(
            "- 参照《行政机关、场馆能耗定额及计算方法》"
            "（DB33/T 736-2021）；",
            rendered,
        )
        self.assertFalse(any("DB33/T 760-2023" in line for line in rendered))

    def test_tourist_hotel_uses_quota_as_direct_basis(self):
        data = project_data(
            subtype="hotel",
            category="旅游饭店",
            specific_type="五星级酒店",
        )

        rendered = basis_module.render_public_building_audit_basis(data)

        self.assertIn(
            "- 《旅游饭店单位综合能耗限额及计算方法》；",
            rendered,
        )
        self.assertNotIn(
            "- 参照《旅游饭店单位综合能耗限额及计算方法》；",
            rendered,
        )
        self.assertNotIn("DB33/T 760-2023", rendered)

    def test_system_standards_follow_project_system_evidence(self):
        without_hvac = project_data(
            subtype="business_office",
            category="科研办公",
            energy_yearly=[{"year": 2024, "electricity_kwh": 1000}],
        )
        with_hvac = project_data(
            subtype="business_office",
            category="科研办公",
            buildings=[{"heating_source": "市政热力"}],
            energy_yearly=[{"year": 2024, "electricity_kwh": 1000}],
        )

        without_hvac_citations = citations(without_hvac)
        with_hvac_citations = citations(with_hvac)

        self.assertNotIn(
            "《空调通风系统运行管理标准》（GB 50365-2019）",
            without_hvac_citations,
        )
        self.assertIn(
            "《空调通风系统运行管理标准》（GB 50365-2019）",
            with_hvac_citations,
        )
        self.assertNotIn(
            "《浙江省用（取）水定额》（2019年）",
            without_hvac_citations,
        )

    def test_out_of_scope_retrofit_removes_retrofit_standards(self):
        data = project_data(
            subtype="business_office",
            category="科研办公",
            energy_yearly=[{"year": 2024, "electricity_kwh": 1000}],
        )

        rendered = basis_module.render_public_building_audit_basis(
            data, include_retrofit=False
        )

        self.assertFalse(any("JGJ 176-2009" in line for line in rendered))
        self.assertFalse(any("GB 55015-2021" in line for line in rendered))

    def test_rendered_basis_is_list_form_and_compacts_survey_material(self):
        data = project_data(
            subtype="business_office",
            category="科研办公",
            buildings=[{"water_system": "市政供水"}],
            energy_yearly=[
                {"year": 2024, "electricity_kwh": 1000, "water_m3": 50}
            ],
        )

        rendered = basis_module.render_public_building_audit_basis(data)

        self.assertTrue(rendered)
        self.assertTrue(all(line.startswith("- ") for line in rendered))
        self.assertEqual(rendered[-1], "- 调研资料及其他相关资料。")
        self.assertFalse(
            any("国家法规与导则" in line for line in rendered)
        )
        self.assertFalse(
            any("浙江省规章" in line for line in rendered)
        )
        self.assertEqual(len(rendered), len(set(rendered)))

    def test_full_period_expands_month_boundaries(self):
        self.assertEqual(
            basis_module.format_full_period("2024年1月—2024年12月"),
            "2024年1月1日—2024年12月31日",
        )
        self.assertEqual(
            basis_module.format_full_period("2024-02-01—2024-02-29"),
            "2024年2月1日—2024年2月29日",
        )
        self.assertEqual(
            basis_module.format_full_period("2025年2月—2025年2月"),
            "2025年2月1日—2025年2月28日",
        )

    def test_month_range_uses_chinese_conference_format(self):
        self.assertEqual(
            basis_module.format_month_range("2025-06", "2025-07"),
            "2025年6月—2025年7月",
        )
        self.assertEqual(
            basis_module.format_month_range("", "2025-07"),
            "",
        )


if __name__ == "__main__":
    unittest.main()
