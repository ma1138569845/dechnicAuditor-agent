"""DataVA 纯函数单元测试（不依赖 tools.energy_audit / python-docx / DB）。

运行:
    cd <skill>/scripts && python -m pytest tests -q
    或直接: python tests/test_datava.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from datava import mode_data_check as v1  # noqa: E402
from datava import mode_indicator_review as v2  # noqa: E402
from datava import mode_report_review as v3  # noqa: E402
from datava.common import (  # noqa: E402
    EXIT_BLOCK,
    EXIT_OK,
    SEV_P0,
    SEV_P1,
    SEV_P2,
    Finding,
    build_result,
    pct_change,
    safe_float,
)


# ================================================================
#  common
# ================================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [("1.5", 1.5), (None, 0.0), ("", 0.0), ("abc", 0.0), (3, 3.0)],
)
def test_safe_float(value, expected):
    assert safe_float(value) == expected


def test_pct_change_zero_base_returns_none():
    assert pct_change(100, 0) is None
    assert pct_change(120, 100) == pytest.approx(20.0)
    assert pct_change(80, 100) == pytest.approx(-20.0)


def test_result_status_and_exit_code():
    clean = build_result("DATA_CHECK", "P", [])
    assert clean.status == "pass" and clean.exit_code == EXIT_OK

    warn = build_result("DATA_CHECK", "P", [Finding("C", "cat", SEV_P1, "t")])
    assert warn.status == "warn" and warn.exit_code == EXIT_OK

    block = build_result(
        "DATA_CHECK", "P", [Finding("C", "cat", SEV_P2, "t"), Finding("C", "cat", SEV_P0, "t")]
    )
    assert block.status == "block" and block.blocking and block.exit_code == EXIT_BLOCK
    # P0 排在最前
    assert block.findings[0].severity == SEV_P0


def test_result_render_text_contains_key_sections():
    result = build_result("REPORT_REVIEW", "某单位", [Finding("V3.X", "格式规范", SEV_P2, "字号偏离")])
    text = result.render_text()
    assert "REPORT_REVIEW" in text and "格式规范" in text and "字号偏离" in text


# ================================================================
#  V1 DATA_CHECK
# ================================================================

@dataclass
class FakeAnomaly:
    """镜像 data_analysis.AnomalyItem 的可 replace 结构。"""

    category: str = "年度对比"
    energy_type: str = "电"
    description: str = "2023年用电同比+42%"
    year: int = 2023
    month: int = 0
    value: float = 100.0
    reference_value: float = 70.0
    change_pct: float = 42.0
    severity: str = "warning"
    confirmed: Optional[bool] = None
    is_data_error: bool = False
    reason: str = ""
    system: str = "空调系统"
    diagnosis: Optional[dict] = None


def test_missing_severity_mapping():
    assert v1.missing_severity("5.x → 能耗数据（完全缺失）") == SEV_P0
    assert v1.missing_severity("6.1 → 设备清单（完全缺失）") == SEV_P1
    assert v1.missing_severity("审计组人员名单") == SEV_P1
    assert v1.missing_severity("审计机构信息表：审计机构详细地址") == SEV_P1
    assert v1.missing_severity("审计配合人员名单") == SEV_P1
    assert v1.missing_severity("某个没列过的字段") == SEV_P1


def test_check_missing_produces_graded_findings():
    findings = v1.check_missing(["2.1 → 建筑面积", "审计组人员名单"])
    assert [f.severity for f in findings] == [SEV_P0, SEV_P1]
    assert findings[0].location == "2.1"


def test_monthly_sum_mismatch_detected():
    rows = [{"year": 2023, "electricity_kwh": 1000.0, "monthly_electricity_kwh": [100.0] * 12}]
    codes = [f.code for f in v1.check_monthly_consistency(rows)]
    assert "V1.MONTHLY.SUM_MISMATCH" in codes


def test_monthly_within_tolerance_is_clean():
    rows = [{"year": 2023, "electricity_kwh": 1200.0, "monthly_electricity_kwh": [100.0] * 12}]
    assert v1.check_monthly_consistency(rows) == []


def test_monthly_absent_is_skipped_not_reported():
    rows = [{"year": 2023, "electricity_kwh": 1200.0, "monthly_electricity_kwh": None}]
    assert v1.check_monthly_consistency(rows) == []


def test_monthly_length_and_zero_annual():
    rows = [{"year": 2023, "electricity_kwh": 1200.0, "monthly_electricity_kwh": [100.0] * 10}]
    assert v1.check_monthly_consistency(rows)[0].code == "V1.MONTHLY.LENGTH"

    # 有月度明细但年度值为 0 → 年度值可疑，而非月度缺失
    rows = [{"year": 2023, "water_m3": 0, "monthly_water_m3": [1.0] * 12}]
    assert v1.check_monthly_consistency(rows)[0].code == "V1.MONTHLY.NO_ANNUAL"


def test_triage_negative_value_is_data_error():
    triaged = v1.triage_anomaly(FakeAnomaly(value=-5.0))
    assert triaged.is_data_error is True and triaged.confirmed is False


def test_triage_extreme_change_is_data_error():
    triaged = v1.triage_anomaly(FakeAnomaly(change_pct=350.0))
    assert triaged.is_data_error is True
    assert "超量级" in triaged.reason


def test_triage_missing_essential_energy_is_data_error():
    triaged = v1.triage_anomaly(FakeAnomaly(category="数据缺失", energy_type="水", change_pct=0))
    assert triaged.is_data_error is True


def test_triage_missing_optional_energy_is_confirmed():
    triaged = v1.triage_anomaly(
        FakeAnomaly(category="数据缺失", energy_type="天然气", change_pct=0)
    )
    assert triaged.confirmed is True and triaged.is_data_error is False


def test_triage_uses_kg_cause_and_never_fabricates():
    with_kg = v1.triage_anomaly(FakeAnomaly(diagnosis={"primary_cause": "冷机能效下降"}))
    assert with_kg.confirmed is True and "冷机能效下降" in with_kg.reason

    without_kg = v1.triage_anomaly(FakeAnomaly())
    assert "待现场核实" in without_kg.reason


def test_triage_preserves_existing_verdict():
    decided = FakeAnomaly(confirmed=True, reason="人工确认")
    assert v1.triage_anomaly(decided) is decided


def test_assess_data_quality_grades():
    p0 = [Finding("c", "完整性", SEV_P0, "t")]
    p1 = [Finding("c", "完整性", SEV_P1, "t")]
    assert v1.assess_data_quality(p0, [])[0] == "D"
    assert v1.assess_data_quality(p1 * 3, [])[0] == "C"
    assert v1.assess_data_quality(p1, [])[0] == "B"
    assert v1.assess_data_quality([], [])[0] == "A"
    assert v1.assess_data_quality([], [FakeAnomaly(severity="critical")] * 3)[0] == "C"


def test_detect_energy_types():
    rows = [{"electricity_kwh": 100, "water_m3": 0, "natural_gas_m3": 5}]
    assert v1.detect_energy_types(rows) == ["电力", "天然气"]


# ── config_validator → check_config_schema ───────────────────────

@dataclass
class FakeBase:
    unit_name: object = "某单位"
    institution_category: object = "医疗"
    building_area: object = 50000
    people_count: object = 1200
    beds_count: object = 0
    audit_start: object = "2022年1月"
    audit_end: object = "2024年12月"
    unit_short: str = ""
    address: str = ""
    unit_type: str = "公共机构"
    specific_type: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    auditor: str = ""
    report_date: str = ""
    province: str = "山东"
    data_start: str = ""
    data_end: str = ""
    admin_affiliation: str = ""


@dataclass
class FakeProject:
    base: FakeBase = field(default_factory=FakeBase)
    energy_yearly: list = field(default_factory=list)
    buildings: list = field(default_factory=list)
    equipment: list = field(default_factory=list)


def test_config_schema_clean_project_no_findings():
    proj = FakeProject(energy_yearly=[{"year": 2022}, {"year": 2023}, {"year": 2024}])
    assert v1.check_config_schema(proj) == []


def test_config_schema_missing_institution_and_audit_bounds():
    proj = FakeProject(base=FakeBase(institution_category="", audit_start="", audit_end=""))
    missing = [f for f in v1.check_config_schema(proj) if f.code == "V1.CONFIG.MISSING"]
    assert len(missing) == 3
    assert {f.location for f in missing} == {
        "base.institution_category", "base.audit_start", "base.audit_end",
    }
    assert all(f.severity == SEV_P1 for f in missing)


def test_config_schema_type_errors():
    proj = FakeProject(base=FakeBase(building_area="50000", people_count=True))
    types = [f for f in v1.check_config_schema(proj) if f.code == "V1.CONFIG.TYPE"]
    assert {f.location for f in types} == {"base.building_area", "base.people_count"}
    assert all(f.severity == SEV_P1 for f in types)


def test_config_schema_negative_range_is_p0():
    proj = FakeProject(base=FakeBase(building_area=-100))
    findings = v1.check_config_schema(proj)
    assert findings[0].code == "V1.CONFIG.RANGE" and findings[0].severity == SEV_P0


def test_config_schema_energy_years_advisory():
    one = FakeProject(energy_yearly=[{"year": 2023}])
    assert v1.check_config_schema(one)[0].code == "V1.CONFIG.ENERGY_YEARS"
    assert v1.check_config_schema(one)[0].severity == SEV_P2

    # 能耗为空：年数建议不报（由 completeness 报 P0 缺失），且不产生 ENERGY_YEARS
    empty = FakeProject(energy_yearly=[])
    assert not [f for f in v1.check_config_schema(empty) if f.code == "V1.CONFIG.ENERGY_YEARS"]


# ================================================================
#  V2 INDICATOR_REVIEW
# ================================================================

ENERGY_BENCH = {"约束值": 22.6, "基准值": 15.3, "引导值": 9.4, "标准": "DB37/T 2673-2019《医疗机构能源消耗定额标准》", "来源": "DB"}
# 医院用水：默认表存 (先进340, 通用540, 0)，位置映射后语义错位
WATER_BENCH_SWAPPED = {"约束值": 340.0, "基准值": 540.0, "引导值": 0.0, "标准": "DB37/T 4452-2021", "来源": "Default"}

ENERGY_SPEC = v2.METRIC_SPECS[0]
WATER_SPEC = v2.METRIC_SPECS[3]


def test_expected_energy_evaluation_tiers():
    assert v2.expected_energy_evaluation(8.0, ENERGY_BENCH) == "低于引导值"
    assert v2.expected_energy_evaluation(12.0, ENERGY_BENCH) == "低于基准值"
    assert v2.expected_energy_evaluation(20.0, ENERGY_BENCH) == "低于约束值"
    assert v2.expected_energy_evaluation(30.0, ENERGY_BENCH) == "高于约束值"


def test_water_thresholds_restore_semantics():
    assert v2.water_thresholds(WATER_BENCH_SWAPPED) == (340.0, 540.0)
    assert v2.water_thresholds({"约束值": 0, "基准值": 0, "引导值": 0}) == (0.0, 0.0)


def test_expected_water_evaluation():
    assert v2.expected_water_evaluation(300.0, WATER_BENCH_SWAPPED) == "低于先进值"
    assert v2.expected_water_evaluation(500.0, WATER_BENCH_SWAPPED) == "低于通用值"
    assert v2.expected_water_evaluation(600.0, WATER_BENCH_SWAPPED) == "高于通用值"
    assert v2.expected_water_evaluation(1.0, {"约束值": 0, "基准值": 0, "引导值": 0}) == "暂无定额标准可对标"


def test_benchmark_clean_energy_case_has_no_p0():
    bench = {**ENERGY_BENCH, "实际值": 12.0, "评价结果": "低于基准值"}
    findings = v2.check_benchmark_structure(ENERGY_SPEC, bench, "medical")
    findings += v2.check_evaluation(2023, ENERGY_SPEC, 12.0, bench)
    assert [f for f in findings if f.severity == SEV_P0] == []


def test_benchmark_eval_mismatch_is_p0():
    bench = {**ENERGY_BENCH, "评价结果": "低于引导值"}
    findings = v2.check_evaluation(2023, ENERGY_SPEC, 20.0, bench)
    assert findings[0].code == "V2.BENCH.EVAL_MISMATCH"
    assert findings[0].severity == SEV_P0


def test_evaluation_absent_is_not_flagged():
    assert v2.check_evaluation(2023, ENERGY_SPEC, 20.0, ENERGY_BENCH) == []


def test_benchmark_order_inverted_is_p0():
    bench = {"约束值": 9.4, "基准值": 15.3, "引导值": 22.6, "标准": "医疗机构定额", "来源": "DB"}
    codes = [f.code for f in v2.check_benchmark_structure(ENERGY_SPEC, bench, "medical")]
    assert "V2.BENCH.ORDER" in codes


def test_benchmark_standard_type_mismatch_is_p0():
    bench = {**ENERGY_BENCH, "标准": "DB37/T 2672-2019《党政机关能源消耗定额标准》"}
    codes = [f.code for f in v2.check_benchmark_structure(ENERGY_SPEC, bench, "medical")]
    assert "V2.BENCH.STANDARD_MISMATCH" in codes


def test_water_semantics_swap_detected():
    bench = {**WATER_BENCH_SWAPPED, "评价结果": "低于先进值"}
    structure = v2.check_benchmark_structure(WATER_SPEC, bench, "medical")
    # 500 L/(床·d) 介于先进值 340 与通用值 540 之间，应为"低于通用值"
    evaluation = v2.check_evaluation(2023, WATER_SPEC, 500.0, bench)
    assert "V2.BENCH.WATER_SEMANTICS" in [f.code for f in structure]
    assert "V2.BENCH.EVAL_MISMATCH" in [f.code for f in evaluation]


def test_water_metric_with_energy_standard_name_is_flagged():
    bench = {**WATER_BENCH_SWAPPED, "标准": "DB37/T 2673-2019《医疗机构能源消耗定额标准》"}
    codes = [f.code for f in v2.check_benchmark_structure(WATER_SPEC, bench, "medical")]
    assert "V2.BENCH.WATER_STANDARD_NAME" in codes


def test_water_metric_with_correct_standard_name_is_clean():
    bench = {**WATER_BENCH_SWAPPED, "标准": "DB37/T 4452-2021《山东省教育、卫生等服务业用水定额》"}
    codes = [f.code for f in v2.check_benchmark_structure(WATER_SPEC, bench, "medical")]
    assert "V2.BENCH.WATER_STANDARD_NAME" not in codes


def test_benchmark_no_quota_is_single_p1():
    bench = {"约束值": 0, "基准值": 0, "引导值": 0, "标准": "", "来源": "Default"}
    findings = v2.check_benchmark_structure(WATER_SPEC, bench, "education")
    assert len(findings) == 1 and findings[0].code == "V2.BENCH.NO_QUOTA"
    # 无定额时不再重复判评价文字
    assert v2.check_evaluation(2023, WATER_SPEC, 12.0, {**bench, "评价结果": "低于先进值"}) == []


def test_benchmark_default_source_is_p2_hint():
    bench = {**ENERGY_BENCH, "来源": "Default", "评价结果": "低于基准值"}
    findings = v2.check_benchmark_structure(ENERGY_SPEC, bench, "medical")
    assert [f.code for f in findings] == ["V2.BENCH.SOURCE_FALLBACK"]
    assert findings[0].severity == SEV_P2
    # 定额为逐年同一份，结构性问题按指标只报一次（location 不含年份）
    assert findings[0].location == ENERGY_SPEC.label


def _yearly(*pairs):
    return [
        {"year": year, "unit_area_non_heating": {"kgce_per_m2": value}}
        for year, value in pairs
    ]


def test_yoy_severity_tiers():
    assert v2._yoy_severity(10.0) is None
    assert v2._yoy_severity(20.0) == SEV_P2
    assert v2._yoy_severity(35.0) == SEV_P1
    assert v2._yoy_severity(-60.0) == SEV_P0


def test_check_yoy_flags_big_jump():
    findings = v2.check_yoy(_yearly((2022, 10.0), (2023, 14.0), (2024, 14.5)))
    changes = [f for f in findings if f.code == "V2.YOY.CHANGE"]
    assert len(changes) == 1 and "2022→2023年" in changes[0].location


def test_check_yoy_zero_base():
    codes = [f.code for f in v2.check_yoy(_yearly((2022, 0.0), (2023, 14.0)))]
    assert "V2.YOY.ZERO_BASE" in codes


def test_consistency_requires_area_and_people():
    findings = v2.check_consistency(
        {"institution_type": "government", "building_area": 0, "people_count": 0}, None
    )
    codes = [f.code for f in findings]
    assert "V2.CONSISTENCY.NO_AREA" in codes and "V2.CONSISTENCY.NO_PEOPLE" in codes


def test_consistency_medical_without_beds():
    findings = v2.check_consistency(
        {"institution_type": "medical", "building_area": 1000, "people_count": 500, "beds_count": 0},
        None,
    )
    assert "V2.CONSISTENCY.NO_BEDS" in [f.code for f in findings]


def test_consistency_area_sum_and_source_mismatch():
    indicators = {
        "institution_type": "government",
        "building_area": 9000,
        "people_count": 100,
    }
    raw = {
        "base": {"building_area": 10000, "province": "广东"},
        "buildings": [{"area": 6000}, {"area": 2000}],
        "energy_yearly": [{"year": 2023, "electricity_kwh": 1}],
    }
    codes = [f.code for f in v2.check_consistency(indicators, raw)]
    assert "V2.CONSISTENCY.AREA_SOURCE_MISMATCH" in codes
    assert "V2.CONSISTENCY.AREA_SUM" in codes


def test_heating_split_northern_without_heat():
    raw = {
        "base": {"province": "山东"},
        "energy_yearly": [{"year": 2023, "heating_energy_heat_gj": 0}],
    }
    findings = v2.check_heating_split(raw)
    assert findings[0].code == "V2.CONSISTENCY.HEATING_NOT_SPLIT"
    assert findings[0].severity == SEV_P1


def test_heating_split_with_purchased_heat_is_p2():
    raw = {
        "base": {"province": "山东"},
        "energy_yearly": [{"year": 2023, "heating_energy_heat_gj": 1200}],
    }
    findings = v2.check_heating_split(raw)
    assert findings[0].code == "V2.CONSISTENCY.HEATING_PUMP_ELEC"
    assert findings[0].severity == SEV_P2


def test_heating_split_southern_is_clean():
    raw = {"base": {"province": "广东"}, "energy_yearly": [{"year": 2023, "heating_energy_heat_gj": 0}]}
    assert v2.check_heating_split(raw) == []


def test_plausibility_range():
    assert v2.check_plausibility(2023, ENERGY_SPEC, "kgce_per_m2", 30.0) == []
    out = v2.check_plausibility(2023, ENERGY_SPEC, "kgce_per_m2", 4000.0)
    assert out[0].severity == SEV_P0


def test_metric_value_priority():
    assert v2.metric_value({"L_per_bed_day": 400}, WATER_SPEC) == ("L_per_bed_day", 400.0)
    assert v2.metric_value({"m3_per_person": 12}, WATER_SPEC) == ("m3_per_person", 12.0)
    assert v2.metric_value({}, WATER_SPEC) == ("", None)


# ================================================================
#  V3 REPORT_REVIEW
# ================================================================

@dataclass(frozen=True)
class FakeParagraph:
    text: str = ""
    runs: tuple = ()

    @property
    def _p(self):
        return type("FakeParagraphElement", (), {"xml": ""})()


@dataclass(frozen=True)
class FakeCell:
    text: str


@dataclass(frozen=True)
class FakeRow:
    cells: tuple


@dataclass(frozen=True)
class FakeTable:
    rows: tuple


def _block(text: str, chapter: int) -> v3.Block:
    return v3.Block("p", 0, text, FakeParagraph(text), chapter)


def _table_block(
    chapter: int,
    header: tuple[str, ...] = (),
    rows: tuple[tuple[str, ...], ...] = (),
) -> v3.Block:
    table = None
    if header:
        fake_rows = [FakeRow(tuple(FakeCell(text) for text in header))]
        fake_rows += [
            FakeRow(tuple(FakeCell(text) for text in row))
            for row in rows
        ]
        table = FakeTable(tuple(fake_rows))
    return v3.Block("tbl", 0, "", table, chapter)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("第1章 审计概况", 1), ("第八章 结论", 8), ("1.1 概况", 0), ("", 0)],
)
def test_chapter_number(text, expected):
    assert v3._chapter_number(text) == expected


def test_extract_areas_handles_wan_unit():
    blocks = [
        _block("总建筑面积为 12,345.60 平方米。", 2),
        _block("建筑面积 1.5 万m²", 5),
    ]
    areas = v3.extract_areas(blocks)
    assert areas[2] == [pytest.approx(12345.6)]
    assert areas[5] == [pytest.approx(15000.0)]


def test_extract_areas_ignores_heating_area_after_building_area_phrase():
    blocks = [
        _block("供暖按建筑面积计缴热费，供暖面积为 54,523.3 m²。", 6),
    ]
    assert v3.extract_areas(blocks) == {}


def test_area_consistency_cross_chapter_mismatch_is_p0():
    findings = v3.check_area_consistency({2: [10000.0], 5: [12000.0]}, 0)
    assert findings[0].code == "V3.CROSS.AREA_MISMATCH"
    assert findings[0].severity == SEV_P0


def test_area_consistency_against_source():
    findings = v3.check_area_consistency({2: [10000.0], 5: [10000.0]}, 12000.0)
    assert [f.code for f in findings] == ["V3.CROSS.AREA_VS_SOURCE"]


def test_area_consistency_clean():
    assert v3.check_area_consistency({2: [10000.0], 5: [10005.0]}, 10000.0) == []


def test_area_missing_is_p1():
    assert v3.check_area_consistency({}, 10000.0)[0].code == "V3.CROSS.AREA_MISSING"


def test_area_consistency_unit_areas_whitelist():
    """2026-10-13 岚山形态：2.2 逐栋段「总建筑面积{area}m²」+ 总面积共存，不报。"""
    areas = {
        2: [20549.7, 15677.0, 9109.32, 7977.0, 5100.85, 2687.0, 2365.0, 63465.91],
        8: [63465.91],
    }
    findings = v3.check_area_consistency(
        areas, 63465.91, 0.0,
        unit_areas=[20549.74, 15677.0, 9109.32, 7977.0, 5100.85, 2687.0, 2365.0],
    )
    assert findings == []


def test_area_consistency_illegal_value_still_p0_with_units():
    """逐栋白名单不放行真错误值：既非章级口径也非任一逐栋面积 → 仍 P0。"""
    findings = v3.check_area_consistency(
        {2: [20549.74, 63465.91, 50000.0]}, 63465.91, 0.0, unit_areas=[20549.74, 15677.0]
    )
    assert [f.code for f in findings] == ["V3.CROSS.AREA_VS_SOURCE"]
    assert findings[0].severity == SEV_P0


def test_area_consistency_units_only_no_chapter_level_is_missing():
    """只写逐栋、无总面积陈述 → 仍报 MISSING（P1），防白名单把口径检查放空。"""
    findings = v3.check_area_consistency(
        {2: [20549.74, 2365.0]}, 63465.91, 0.0, unit_areas=[20549.74, 2365.0]
    )
    assert [f.code for f in findings] == ["V3.CROSS.AREA_MISSING"]
    assert findings[0].severity == SEV_P1


def test_check_chapters_missing_is_p0():
    blocks = [_block(f"第{n}章 标题", n) for n in range(1, 8)]
    codes = [f.code for f in v3.check_chapters(blocks)]
    assert "V3.STRUCT.CHAPTER_MISSING" in codes


def test_cover_consistency_accepts_complete_cover():
    base = {
        "unit_name": "某医院",
        "audit_org_name": "某能源审计公司",
        "report_date": "2026年10月",
    }
    blocks = [
        _block("某医院", 0),
        _block("能源审计报告", 0),
        _block("某能源审计公司", 0),
        _block("2026年10月", 0),
    ]
    assert v3.check_cover_consistency(blocks, base) == []


def test_cover_consistency_missing_date_is_p0():
    base = {
        "unit_name": "某医院",
        "audit_org_name": "某能源审计公司",
        "report_date": "2026年10月",
    }
    blocks = [
        _block("某医院", 0),
        _block("能源审计报告", 0),
        _block("某能源审计公司", 0),
    ]
    findings = v3.check_cover_consistency(blocks, base)
    assert [f.code for f in findings] == ["V3.COVER.DATE_MISSING"]
    assert findings[0].severity == SEV_P0


def test_cover_consistency_rejects_date_mismatch():
    base = {
        "unit_name": "某医院",
        "audit_org_name": "某能源审计公司",
        "report_date": "2026年10月",
    }
    blocks = [
        _block("某医院", 0),
        _block("能源审计报告", 0),
        _block("某能源审计公司", 0),
        _block("2025年9月", 0),
    ]
    findings = v3.check_cover_consistency(blocks, base)
    assert [f.code for f in findings] == ["V3.COVER.DATE_MISMATCH"]


def test_check_chapters_empty_body_is_p0():
    blocks = []
    for n in range(1, 9):
        blocks.append(_block(f"第{n}章 标题", n))
        if n != 7:
            blocks.append(_block("内容" * 60, n))
    codes = [f.code for f in v3.check_chapters(blocks)]
    assert "V3.STRUCT.CHAPTER_EMPTY" in codes


def test_placeholder_detection_is_p0():
    blocks = [_block("审计组人员：【待补充】", 1)] + [_table_block(1) for _ in range(6)]
    findings = v3.check_tables_and_placeholders(blocks)
    placeholder = [f for f in findings if f.code == "V3.STRUCT.PLACEHOLDER"]
    assert placeholder and placeholder[0].severity == SEV_P0


def test_province_rules_count():
    enough = [
        _block("1.6 省级节能规章", 1),
        _block("《山东省节约能源条例》", 1),
        _block("《山东省公共机构节能办法》", 1),
        _block("《山东省能源审计管理规定》", 1),
    ]
    assert v3.check_province_rules(enough) == []

    too_few = enough[:2]
    assert v3.check_province_rules(too_few)[0].code == "V3.STRUCT.PROVINCE_RULES"


def test_chapter6_dynamic_subsections_requirement():
    blocks = [
        _block("第6章 主要能源资源利用系统分析", 6),
        _block("6.1 用电系统运行分析", 6),
        _block("本项目用电系统主要包括空调和照明系统。", 6),
        _block("（1）空调系统", 6),
        _block("（2）照明系统", 6),
    ]
    codes = {f.code for f in v3.check_chapter6_structure(blocks)}
    assert "V3.STRUCT.CHAPTER6_SUBSECTIONS" in codes


def test_chapter6_rejects_equipment_row_dump_in_composition_paragraph():
    blocks = [
        _block("第6章 主要能源资源利用系统分析", 6),
        _block("6.1 用电系统运行分析", 6),
        _block("本项目用电系统主要包括空调与供暖系统、照明系统和办公设备。", 6),
        _block("（1）空调与供暖系统", 6),
        _block(
            "医院冷源采用水冷冷水机组4台，其中YORK YSEZEZS45CKE/22型2台"
            "（单台298 kW）、YMC2-S0879AA型2台（单台155 kW）；配套冷冻水泵"
            "3台（单台30 kW）、冷却水泵3台（单台30 kW）、冷却塔2台（单台15 kW）。",
            6,
        ),
        _block("冷源系统按供冷季运行，机组启停采用人工控制。", 6),
        _block("冷源系统未单独计量，空调用电无法单独核算。", 6),
        _block("（2）照明系统", 6),
        _block("医院照明系统由LED灯具和传统灯具组成。", 6),
        _block("照明设施按使用区域分时段运行。", 6),
        _block("照明系统未单独计量，照明用电无法单独核算。", 6),
        _block("（3）办公设备", 6),
        _block("医院办公设备主要包括台式机和打印机。", 6),
        _block("办公设备主要在办公时段运行。", 6),
        _block("办公设备未单独计量，办公用电无法单独核算。", 6),
    ]
    codes = {f.code for f in v3.check_chapter6_structure(blocks)}
    assert "V3.STRUCT.CHAPTER6_DEVICE_DETAIL" in codes


def test_chapter6_accepts_equipment_summary_with_total_capacity():
    blocks = [
        _block("第6章 主要能源资源利用系统分析", 6),
        _block("6.1 用电系统运行分析", 6),
        _block("本项目用电系统主要包括空调与供暖系统、照明系统和办公设备。", 6),
        _block("（1）空调与供暖系统", 6),
        _block(
            "医院冷源采用集中式水冷冷水机组4台，总装机容量906 kW；"
            "配套冷冻水泵、冷却水泵各3台，冷却塔2台，末端采用风机盘管。",
            6,
        ),
        _block("冷源系统按供冷季运行，机组启停采用人工控制。", 6),
        _block("冷源系统未单独计量，空调用电无法单独核算。", 6),
        _block("（2）照明系统", 6),
        _block("医院照明系统由LED灯具和传统灯具组成。", 6),
        _block("照明设施按使用区域分时段运行。", 6),
        _block("照明系统未单独计量，照明用电无法单独核算。", 6),
        _block("（3）办公设备", 6),
        _block("医院办公设备主要包括台式机和打印机。", 6),
        _block("办公设备主要在办公时段运行。", 6),
        _block("办公设备未单独计量，办公用电无法单独核算。", 6),
    ]
    codes = {f.code for f in v3.check_chapter6_structure(blocks)}
    assert "V3.STRUCT.CHAPTER6_DEVICE_DETAIL" not in codes


def test_chapter6_public_institution_accepts_substation_special_table():
    blocks = [
        _block("表6.5 变配电系统设备清单", 6),
        _table_block(
            6,
            (
                "序号", "设备名称", "规格型号", "形式", "数量",
                "单台容量（kVA）", "安装时间",
            ),
        ),
    ]
    codes = {
        f.code
        for f in v3.check_chapter6_structure(blocks, public_institution=True)
    }
    assert "V3.STRUCT.CHAPTER6_TABLE" not in codes


def test_chapter6_public_building_keeps_standard_equipment_table_columns():
    blocks = [
        _block("表6.3 变配电系统设备清单", 6),
        _table_block(
            6,
            (
                "序号", "设备名称", "规格型号", "形式", "数量",
                "单台容量（kVA）", "安装时间",
            ),
        ),
    ]
    codes = {
        f.code
        for f in v3.check_chapter6_structure(blocks, public_institution=False)
    }
    assert "V3.STRUCT.CHAPTER6_TABLE" in codes


def test_chapter6_public_institution_enforces_electrical_system_order():
    blocks = [
        _block("6.1 用电系统运行分析", 6),
        _block("本项目用电系统主要包括空调与供暖系统、其他用电设备、"
               "特殊用能系统和变配电系统。", 6),
        _block("（1）空调与供暖系统", 6),
        _block("空调系统按供冷季运行。", 6),
        _block("（2）其他用电设备", 6),
        _block("（3）特殊用能系统", 6),
        _block("（4）变配电系统", 6),
    ]
    codes = {
        f.code
        for f in v3.check_chapter6_structure(blocks, public_institution=True)
    }
    assert "V3.STRUCT.CHAPTER6_SYSTEM_ORDER" in codes


def test_chapter6_public_building_ignores_public_institution_system_order():
    blocks = [
        _block("6.1 用电系统运行分析", 6),
        _block("本项目用电系统主要包括空调与供暖系统、其他用电设备、"
               "特殊用能系统和变配电系统。", 6),
        _block("（1）空调与供暖系统", 6),
        _block("空调系统按供冷季运行。", 6),
        _block("（2）其他用电设备", 6),
        _block("（3）特殊用能系统", 6),
        _block("（4）变配电系统", 6),
    ]
    codes = {
        f.code
        for f in v3.check_chapter6_structure(blocks, public_institution=False)
    }
    assert "V3.STRUCT.CHAPTER6_SYSTEM_ORDER" not in codes


def test_chapter6_photo_coverage_requires_each_equipment_with_img_ids():
    blocks = [
        _block("6.1 用电系统运行分析", 6),
        _block("图6.9 医疗设备", 6),
        _table_block(
            6,
            ("序号", "设备名称"),
            (("1", "医疗设备"), ("2", "数据中心/信息中心")),
        ),
    ]
    equipment = [
        {"name": "医疗设备", "category": "特殊设备", "img_ids": [101]},
        {"name": "数据中心/信息中心", "category": "特殊设备", "img_ids": [102, 103]},
    ]
    images = [{"file_id": 101}, {"file_id": 102}, {"file_id": 103}]
    findings = v3.check_chapter6_structure(
        blocks, equipment=equipment, images=images
    )
    coverage = [
        f for f in findings if f.code == "V3.STRUCT.CHAPTER6_PHOTO_COVERAGE"
    ]
    assert coverage
    assert "数据中心/信息中心" in coverage[0].detail
    assert "医疗设备" not in coverage[0].detail


def test_chapter6_photo_coverage_accepts_one_caption_per_special_system():
    blocks = [
        _block("6.1 用电系统运行分析", 6),
        _block("图6.9 医疗设备", 6),
        _block("图6.10 数据中心/信息中心", 6),
        _table_block(
            6,
            ("序号", "设备名称"),
            (("1", "医疗设备"), ("2", "数据中心/信息中心")),
        ),
    ]
    equipment = [
        {"name": "医疗设备", "category": "特殊设备", "img_ids": [101]},
        {"name": "数据中心/信息中心", "category": "特殊设备", "img_ids": [102]},
    ]
    images = [{"file_id": 101}, {"file_id": 102}]
    codes = {
        f.code
        for f in v3.check_chapter6_structure(
            blocks, equipment=equipment, images=images
        )
    }
    assert "V3.STRUCT.CHAPTER6_PHOTO_COVERAGE" not in codes


def test_area_billing_rejects_heat_meter_defect_wording():
    blocks = [
        _block("供暖按面积缴费，未安装热量计量表，供热量无法单独计量。", 6),
        _block("供暖按面积缴费，热力实物量数据缺失。", 7),
    ]
    findings = v3.check_heating_billing_semantics(blocks, "按面积缴费")
    assert len(findings) == 1
    assert findings[0].code == "V3.STRUCT.HEATING_AREA_BILLING"
    assert findings[0].severity == SEV_P1
    assert "第6章" in findings[0].location and "第7章" in findings[0].location


def test_area_billing_scans_table_cells():
    blocks = [
        _table_block(
            5,
            ("说明",),
            (("供暖按面积缴费，热力实物量数据缺失。",),),
        )
    ]
    findings = v3.check_heating_billing_semantics(blocks, "按面积缴费")
    assert len(findings) == 1
    assert "第5章" in findings[0].location


def test_area_billing_accepts_billing_facts():
    blocks = [
        _block(
            "供暖按建筑面积计缴热费，供暖面积63465.91 m²，"
            "供暖费单价23.30元/m²，供暖费用147.88万元。",
            6,
        )
    ]
    assert v3.check_heating_billing_semantics(blocks, "按面积缴费") == []


def test_metered_billing_does_not_apply_area_billing_rule():
    blocks = [_block("供暖按热量计缴热费，供热量无法单独计量。", 6)]
    assert v3.check_heating_billing_semantics(blocks, "按计量表缴费") == []


def test_unknown_billing_does_not_infer_metering_defect():
    blocks = [_block("本项目供暖未安装热量计量表，供热量无法单独计量。", 7)]
    assert v3.check_heating_billing_semantics(blocks, "") == []


def test_chapter7_711_rejects_empty_water_status_rewrite():
    blocks = [
        _block("7.1.1 能耗监测系统", 7),
        _block(
            "厨房用水未单独计量，现场未获取到空调供暖补水单独计量资料，"
            "绿化灌溉用水单独计量情况待进一步核实【待核实】。",
            7,
        ),
        _block("7.1.2 照明系统能效低", 7),
    ]
    findings = v3.check_chapter7_711_metering_semantics(blocks)
    assert len(findings) == 1
    assert findings[0].code == "V3.STRUCT.CHAPTER7_711_METERING_SPECULATION"
    assert findings[0].severity == SEV_P1
    assert "现场未获取到" in findings[0].detail


def test_chapter7_711_rejects_empty_gas_status_rewrite():
    blocks = [
        _block("7.1.1 能耗监测系统", 7),
        _block(
            "燃气蒸汽锅炉（手术室消毒）未单独计量，"
            "厨房炊事及供冷供热用气情况待进一步核实【待核实】。",
            7,
        ),
        _block("7.1.2 空调控制落后", 7),
    ]
    findings = v3.check_chapter7_711_metering_semantics(blocks)
    assert [f.code for f in findings] == [
        "V3.STRUCT.CHAPTER7_711_METERING_SPECULATION"
    ]
    assert "厨房炊事及供冷供热用气" in findings[0].detail


def test_chapter7_711_accepts_confirmed_metering_facts_only():
    blocks = [
        _block("7.1.1 能耗监测系统", 7),
        _block("本项目用水计量仅安装总计量水表。", 7),
        _block("厨房用水未单独计量。", 7),
        _block("燃气蒸汽锅炉用于手术室消毒，未单独计量。", 7),
        _block("7.1.2 照明系统能效低", 7),
    ]
    assert v3.check_chapter7_711_metering_semantics(blocks) == []


def test_chapter7_711_scope_does_not_flag_legitimate_verify_note_elsewhere():
    blocks = [
        _block("7.1.1 能耗监测系统", 7),
        _block("本项目用水计量仅安装总计量水表。", 7),
        _block("7.1.2 照明系统能效低", 7),
        _block("2022年4月用电量异常，异常原因请核实。", 5),
        _block("厨房炊事用气情况待进一步核实【待核实】。", 6),
    ]
    assert v3.check_chapter7_711_metering_semantics(blocks) == []


def test_chapter7_metering_classes_follow_actual_project_energy():
    raw = {
        "energy_yearly": [
            {"electricity_kwh": 100, "water_m3": 10, "natural_gas_m3": 0},
        ],
        "metering": {"heat_meters": 0, "heat_pay_type": ""},
        "buildings": [{"heating_source": ""}],
        "equipment": [],
    }
    assert v3.chapter7_metering_classes(raw) == ("用电", "用水")

    raw["equipment"] = [{"name": "燃气蒸汽锅炉", "independent_metering": "无"}]
    raw["buildings"] = [{"heating_source": "市政供暖"}]
    assert v3.chapter7_metering_classes(raw) == (
        "用电", "用水", "用燃气", "用热"
    )


def test_chapter7_711_cover_only_requires_actual_energy_classes():
    blocks = [
        _block("第7章 节能效果与节能潜力分析", 7),
        _block("7.1 用能系统现状分析", 7),
        _block("7.1.1 能耗监测系统", 7),
        _block("本项目用电计量仅安装总表，用水计量仅安装总表。", 7),
        _block("7.1.2 照明系统能效低", 7),
        _block("7.1.3 空调控制落后", 7),
        _block("7.2 节能潜力分析及建议", 7),
        _block("7.2.1 建设能耗监测系统", 7),
        _block("7.2.2 照明改造", 7),
        _block("7.2.3 空调改造", 7),
        _block("7.2.4 管理与行为节能", 7),
        _block("7.2.5 节能率分析", 7),
    ]
    codes = {
        f.code for f in v3.check_chapter7_structure(
            blocks, metering_classes=("用电", "用水")
        )
    }
    assert "V3.STRUCT.CHAPTER7_711_COVER" not in codes


def test_appendix2_wide_tables_are_exempt_from_standard_row_height():
    blocks = [
        _block("附表2-1 2022年建筑能耗数据统计表", 8),
        _table_block(8, ("月份", "用电量", "用水量")),
    ]
    assert v3.is_appendix2_table(blocks, 1)


def _chapter8_blocks(*, inline_suggestions: bool = False):
    blocks = [
        _block("5.3.1 指标甲", 5),
        _block("5.3.2 指标乙", 5),
    ]
    blocks += [
        _block("7.1.1 能耗监测系统", 7),
        _block("7.1.2 空调控制落后", 7),
        _block("7.2.1 建设能耗监测系统", 7),
        _block("7.2.2 空调智慧管控", 7),
        _block("7.2.3 管理与行为节能", 7),
        _block("7.2.4 节能率分析", 7),
        _block("第8章 审计结论", 8),
        _block("1.指标甲分别为1、2、3。", 8),
        _block("2.指标乙分别为4、5、6。", 8),
        _block("本次审计共发现用能管理问题2项，提出可行性节能改造建议3条，包括：", 8),
    ]
    if inline_suggestions:
        blocks.append(
            _block("（1）建设能耗监测系统；（2）空调智慧管控；（3）管理与行为节能。", 8)
        )
    else:
        blocks += [
            _block("（1）建设能耗监测系统。", 8),
            _block("（2）空调智慧管控。", 8),
            _block("（3）管理与行为节能。", 8),
        ]
    return blocks


def test_chapter8_summary_flat_list_and_appendix_exclusion():
    blocks = _chapter8_blocks()
    assert v3.check_chapter8_summary(blocks) == []

    blocks += [_block("附录：", 8), _table_block(8)]
    assert v3.check_chapter8_summary(blocks) == []


def test_chapter8_summary_rejects_inline_suggestions():
    findings = v3.check_chapter8_summary(_chapter8_blocks(inline_suggestions=True))
    assert "V3.STRUCT.CHAPTER8_LIST_FORMAT" in {f.code for f in findings}


def test_chapter8_summary_rejects_table_and_wrong_counts():
    blocks = _chapter8_blocks()
    title_index = next(
        i for i, b in enumerate(blocks) if b.text == "第8章 审计结论"
    )
    blocks.insert(title_index + 1, _table_block(8))
    blocks = [
        _block("本次审计共发现用能管理问题1项，提出可行性节能改造建议3条，包括：", 8)
        if b.text.startswith("本次审计共发现") else b
        for b in blocks
    ]
    codes = {f.code for f in v3.check_chapter8_summary(blocks)}
    assert "V3.STRUCT.CHAPTER8_TABLE" in codes
    assert "V3.STRUCT.CHAPTER8_COUNTS" in codes


def test_energy_consistency_cross_chapter():
    blocks = [
        _block("全年综合能耗 1,000.00 tce", 4),
        _block("综合能耗合计 1,200.00 tce", 5),
    ]
    findings = v3.check_energy_consistency(blocks)
    assert findings[0].code == "V3.CROSS.ENERGY_MISMATCH"

    same = [_block("1,000.00 tce", 4), _block("1,000.00 tce", 5)]
    assert v3.check_energy_consistency(same) == []


def test_year_coverage():
    blocks = [_block("2022年、2023年用电量如下", 5)]
    findings = v3.check_year_coverage(blocks, [2022, 2023, 2024])
    assert findings[0].code == "V3.CROSS.YEAR_MISSING" and "2024" in findings[0].actual


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("第3章 能源管理", "h1"),
        ("5.2.1 电耗分析", "h3"),
        ("5.2 能耗指标", "h2"),
        ("短句", "skip"),
        ("这是一段足够长的正文内容用于触发正文格式检查规则判定分支。", "body"),
    ],
)
def test_classify(text, expected):
    assert v3._classify(text) == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
