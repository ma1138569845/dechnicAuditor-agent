import pytest

from tools.energy_audit.dept_dict import (
    DictionaryCodeError,
    classify_from_codes,
    expected_dictionary_rows,
    resolve_unit_codes,
)


def test_legacy_two_argument_call_is_unchanged():
    assert classify_from_codes("E", "A") == ("教育", "本科及以上")


def test_zhejiang_public_institution_namespace_is_selected():
    result = resolve_unit_codes(
        "zj_medical",
        "zj_medical_3",
        unit_type="公共机构",
        province="浙江",
    )
    assert result["dictionary_type"] == "zj_client_dept_type"
    assert result["public_building_subtype"] == ""
    assert result["hospital_level"] == "3"


def test_zhejiang_hotel_uses_only_the_zhejiang_public_building_namespace():
    result = resolve_unit_codes(
        "zj_hotel",
        "zj_hotel_4",
        unit_type="公共建筑",
        province="浙江省",
    )
    assert result["dictionary_type"] == "zj_public_build_type"
    assert result["public_building_subtype"] == "hotel"
    assert result["star"] == "4"


def test_shandong_public_building_codes_are_namespaced():
    agency = resolve_unit_codes(
        "B",
        "",
        unit_type="公共建筑",
        province="山东",
    )
    hospital = resolve_unit_codes(
        "D",
        "D2",
        unit_type="公共建筑",
        province="山东",
    )
    assert agency["public_building_subtype"] == "agency_office"
    assert hospital["hospital_level"] == "3"
    assert hospital["hospital_specialty"] == "specialty"


def test_other_provinces_reuse_codes_but_not_a_standard_pack():
    result = resolve_unit_codes(
        "C",
        "",
        unit_type="公共建筑",
        province="江苏",
    )
    assert result["dictionary_type"] == "public_build_type"
    assert result["public_building_subtype"] == "business_office"


def test_unknown_nonempty_platform_code_raises_with_raw_codes():
    with pytest.raises(DictionaryCodeError, match="X9"):
        resolve_unit_codes(
            "X9",
            "",
            unit_type="公共建筑",
            province="山东",
        )


def test_hotel_without_star_raises_instead_of_defaulting():
    with pytest.raises(DictionaryCodeError, match="A2/A3"):
        resolve_unit_codes(
            "A",
            "",
            unit_type="公共建筑",
            province="山东",
        )


def test_public_building_requires_a_province():
    with pytest.raises(DictionaryCodeError, match="province"):
        resolve_unit_codes(
            "B",
            "",
            unit_type="公共建筑",
            province="",
        )


def test_expected_rows_cover_all_registered_dictionary_types():
    rows = expected_dictionary_rows()
    assert set(rows) == {
        "zj_client_dept_type",
        "zj_client_dept_type_zj_gov",
        "zj_client_dept_type_venue",
        "zj_client_dept_type_zj_medical",
        "zj_public_build_type",
        "zj_public_build_type_zj_hotel",
        "client_dept_type",
        "client_dept_type_A",
        "client_dept_type_B",
        "client_dept_type_C",
        "client_dept_type_D",
        "client_dept_type_E",
        "public_build_type",
        "public_build_type_A",
        "public_build_type_D",
    }
    assert rows["zj_client_dept_type_venue"] == {
        "venue_science": "科技馆",
        "venue_culture": "文化馆",
        "venue_museum": "博物馆",
    }
    assert rows["public_build_type_D"]["D4"] == "二级及以下专科医院"

