"""能源审计折标煤系数持久化与指标计算测试。"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.energy_audit import indicators
from tools.energy_audit import pg_collector as pgc
from tools.energy_audit.project_data import (
    AuditProject,
    EnergyYearly,
    ProjectBase,
    is_valid_coefficient,
    load_project,
    save_project,
)


# ============================================================
# Helpers
# ============================================================

@pytest.fixture
def temp_projects_root(monkeypatch):
    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr('tools.energy_audit.project_data._PROJECTS_ROOT', tmp)
    return tmp


def _make_pg_instance(energy_records, project_id='P001', customer_id=1):
    """构造一个模拟的 PgDataQuery 实例。"""
    pg = MagicMock()
    pg.find_project_by_name.return_value = {
        'id': project_id,
        'customer_id': customer_id,
        'audited_name': '测试单位',
        'audit_dept_name': '审计机构',
    }
    pg.get_institution_build.return_value = []
    pg.get_institution_energy.return_value = energy_records
    pg.get_formatted_equipment.return_value = []
    pg.get_project_audit_users.return_value = []
    pg.get_project_audited_users.return_value = []
    pg.get_institution_scene.return_value = []
    pg.get_institution_scene_mode.return_value = []
    pg.get_energy_meter.return_value = []
    pg.get_energy_standards.return_value = []
    pg.get_customer_info.return_value = [{'name': 'Test'}]
    pg.get_province_name_by_district_id.return_value = ''
    return pg


# ============================================================
# is_valid_coefficient
# ============================================================

@pytest.mark.parametrize('value,expected', [
    (0.1229, True),
    ('0.1229', True),
    (0, False),
    ('0', False),
    (-1, False),
    (None, False),
    ('', False),
    ('abc', False),
    ([], False),
])
def test_is_valid_coefficient(value, expected):
    assert is_valid_coefficient(value) is expected


# ============================================================
# pg_collector extraction
# ============================================================

def test_pg_collector_extracts_standard_coal_coefficient():
    records = [
        {
            'id': 1, 'year': '2023', 'data_type': 1, 'energy_code': '45',
            'energy_name': '电能', 'energy_unit': 'kWh',
            'standard_coal_coefficient': 0.1229,
            'building_total_value': 0, 'unit_total_value': 100000,
            'granularity': 1, 'customer_id': 1,
            **{f'value{i}': 10000 for i in range(1, 13)},
        },
        {
            'id': 2, 'year': '2023', 'data_type': 1, 'energy_code': '01',
            'energy_name': '水', 'energy_unit': 'm³',
            'standard_coal_coefficient': 0.2571,
            'building_total_value': 0, 'unit_total_value': 5000,
            'granularity': 1, 'customer_id': 1,
            **{f'value{i}': 500 for i in range(1, 13)},
        },
    ]
    pg = _make_pg_instance(records)
    result = pgc._collect_from_pg_impl(pg, '测试项目')

    ey = result['found']['energy_yearly'][0]
    assert ey['year'] == 2023
    assert ey['coefficients']['electricity'] == pytest.approx(0.1229)
    assert ey['coefficients']['water'] == pytest.approx(0.2571)
    assert ey['coefficient_sources']['electricity'] == 'PG'
    assert ey['coefficient_sources']['water'] == 'PG'


@pytest.mark.parametrize('raw,expected', [
    ('2022-5~2022-10', ('2022年5月', '2022年10月')),
    ('2022-05～2022-10', ('2022年5月', '2022年10月')),
    ('2023~2024', ('2023年', '2024年')),
    ('2025', ('2025年', '2025年')),
    ('', ('', '')),
    (None, ('', '')),
])
def test_parse_audit_year_range(raw, expected):
    assert pgc.parse_audit_year_range(raw) == expected


@pytest.mark.parametrize('district_id,expected', [
    ('370611', '370000'),
    ('370000', '370000'),
    ('11', '110000'),
    ('', ''),
    (None, ''),
])
def test_district_id_to_province_code(district_id, expected):
    from tools.energy_audit.pg_query import PgDataQuery
    assert PgDataQuery.district_id_to_province_code(district_id) == expected


@pytest.mark.parametrize('full,short', [
    ('山东省', '山东'),
    ('北京市', '北京'),
    ('内蒙古自治区', '内蒙古'),
    ('新疆维吾尔自治区', '新疆'),
    ('', ''),
])
def test_short_province_name(full, short):
    from tools.energy_audit.pg_query import PgDataQuery
    assert PgDataQuery.short_province_name(full) == short


def test_pg_collector_admin_affiliation_from_district_id():
    pg = _make_pg_instance([])
    pg.get_customer_info.return_value = [{'district_id': '370611'}]
    pg.get_province_name_by_district_id.return_value = '山东省'
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    customer = result['found']['customer_info']
    assert customer['admin_affiliation'] == '山东省'
    assert customer['province'] == '山东'
    pg.get_province_name_by_district_id.assert_called_once_with('370611')


@pytest.mark.parametrize('district_id,expected', [
    ('370611', '370600'),
    ('370000', '370000'),
    ('11', ''),
    ('', ''),
    (None, ''),
])
def test_district_id_to_city_code(district_id, expected):
    from tools.energy_audit.pg_query import PgDataQuery
    assert PgDataQuery.district_id_to_city_code(district_id) == expected


def test_pg_collector_fills_city_district_from_division():
    pg = _make_pg_instance([])
    pg.get_customer_info.return_value = [{'district_id': '370611'}]
    pg.get_admin_division_by_district_id.return_value = {
        'province': '山东',
        'city': '烟台',
        'district': '福山',
        'province_full': '山东省',
        'city_full': '烟台市',
        'district_full': '福山区',
    }
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    customer = result['found']['customer_info']
    assert customer['province'] == '山东'
    assert customer['city'] == '烟台'
    assert customer['district'] == '福山'
    assert customer['admin_affiliation'] == '山东省'


@pytest.mark.parametrize('raw,expected', [
    ('2023~2024', ('2023-01-01', '2024-12-31')),
    ('2022-5~2022-10', ('2022-05-01', '2022-10-31')),
    ('2025', ('2025-01-01', '2025-12-31')),
    ('', ('', '')),
    (None, ('', '')),
])
def test_parse_data_year_range(raw, expected):
    assert pgc.parse_data_year_range(raw) == expected


@pytest.mark.parametrize('reference_year,audit_year,expected', [
    ('2023~2024', '2025', ('2023-01-01', '2025-12-31')),
    ('2023~2024', None, ('2023-01-01', '2024-12-31')),
    (None, '2025', ('2025-01-01', '2025-12-31')),
    ('2022-5~2022-10', '2025', ('2022-05-01', '2025-12-31')),
])
def test_parse_data_period_unions_reference_and_audit(reference_year, audit_year, expected):
    assert pgc.parse_data_period(reference_year, audit_year) == expected


def test_pg_collector_parses_audit_year_into_start_end():
    pg = _make_pg_instance([])
    pg.find_project_by_name.return_value['audit_year'] = '2022-5~2022-10'
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    project = result['found']['project']
    assert project['audit_start'] == '2022年5月'
    assert project['audit_end'] == '2022年10月'


def test_pg_collector_parses_reference_year_into_data_start_end():
    pg = _make_pg_instance([])
    pg.find_project_by_name.return_value['audit_year'] = '2025'
    pg.find_project_by_name.return_value['reference_year'] = '2023~2024'
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    project = result['found']['project']
    assert project['data_start'] == '2023-01-01'
    assert project['data_end'] == '2025-12-31'


def test_pg_collector_data_range_falls_back_to_audit_year():
    pg = _make_pg_instance([])
    pg.find_project_by_name.return_value['audit_year'] = '2025'
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    project = result['found']['project']
    assert project['data_start'] == '2025-01-01'
    assert project['data_end'] == '2025-12-31'


def test_pg_collector_ignores_invalid_coefficients():
    records = [
        {
            'id': 1, 'year': '2023', 'data_type': 1, 'energy_code': '45',
            'energy_name': '电能', 'energy_unit': 'kWh',
            'standard_coal_coefficient': 0,  # invalid
            'building_total_value': 0, 'unit_total_value': 100000,
            'granularity': 1, 'customer_id': 1,
            **{f'value{i}': 10000 for i in range(1, 13)},
        },
    ]
    pg = _make_pg_instance(records)
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    ey = result['found']['energy_yearly'][0]
    assert 'electricity' not in ey.get('coefficients', {})
    assert 'electricity' not in ey.get('coefficient_sources', {})


def test_pg_collector_cost_records_do_not_write_coefficients():
    records = [
        {
            'id': 1, 'year': '2023', 'data_type': 2, 'energy_code': '45',
            'energy_name': '电能', 'energy_unit': 'kWh',
            'standard_coal_coefficient': 0.9999,  # should be ignored for dt==2
            'building_total_value': 0, 'unit_total_value': 100000,
            'granularity': 1, 'customer_id': 1,
            **{f'value{i}': 10000 for i in range(1, 13)},
        },
    ]
    pg = _make_pg_instance(records)
    result = pgc._collect_from_pg_impl(pg, '测试项目')
    ey = result['found']['energy_yearly'][0]
    assert 'coefficients' not in ey or 'electricity' not in ey.get('coefficients', {})


# ============================================================
# data_collection_cli merge
# ============================================================

def test_merge_energy_preserves_pg_coefficients():
    pg = [{'year': 2023, 'electricity_kwh': 100, 'coefficients': {'electricity': 0.15}}]
    excel = [{'year': 2023, 'electricity_kwh': 200, 'coefficients': {'electricity': 0.25}}]
    merged = pgc._merge_energy(pg, excel)
    assert merged[0].electricity_kwh == 100  # PG quantity wins
    assert merged[0].coefficients['electricity'] == pytest.approx(0.15)


def test_merge_energy_fills_missing_coefficients_from_lower_priority():
    pg = [{'year': 2023, 'electricity_kwh': 100, 'coefficients': {'electricity': 0.15}}]
    excel = [{'year': 2023, 'electricity_kwh': 200, 'coefficients': {'water': 0.35}}]
    merged = pgc._merge_energy(pg, excel)
    assert merged[0].coefficients['electricity'] == pytest.approx(0.15)
    assert merged[0].coefficients['water'] == pytest.approx(0.35)


def test_merge_energy_keeps_excel_when_pg_empty():
    pg = []
    excel = [{'year': 2023, 'electricity_kwh': 200, 'coefficients': {'electricity': 0.25}}]
    merged = pgc._merge_energy(pg, excel)
    assert merged[0].electricity_kwh == 200
    assert merged[0].coefficients['electricity'] == pytest.approx(0.25)


# ============================================================
# persistence roundtrip
# ============================================================

def test_save_and_load_roundtrip_with_coefficients(temp_projects_root):
    proj = AuditProject(
        base=ProjectBase(name='测试', unit_name='测试单位'),
        energy_yearly=[
            EnergyYearly(
                year=2023,
                electricity_kwh=100000,
                coefficients={'electricity': 0.1229, 'water': 0.2571},
                coefficient_sources={'electricity': 'PG', 'water': 'PG'},
            )
        ],
    )
    path = save_project(proj)
    with open(path, encoding='utf-8') as f:
        raw = json.load(f)
    assert raw['energy_yearly'][0]['coefficients'] == pytest.approx({'electricity': 0.1229, 'water': 0.2571})
    assert raw['energy_yearly'][0]['coefficient_sources'] == {'electricity': 'PG', 'water': 'PG'}

    loaded = load_project('测试单位')
    assert loaded.energy_yearly[0].coefficients == pytest.approx({'electricity': 0.1229, 'water': 0.2571})


# ============================================================
# indicators use persisted coefficients
# ============================================================

def test_yearly_energy_data_uses_persisted_coefficients():
    yd = indicators.YearlyEnergyData(
        year=2023,
        electricity_kwh=100000,
        water_m3=5000,
        natural_gas_m3=2000,
        heating_energy_heat=100,
        transportation_petrol_kg=300,
        transportation_diesel_kg=200,
        coefficients={
            'electricity': 0.15,
            'water': 0.3,
            'natural_gas': 1.4,
            'heat': 0.04,
            'gasoline': 1.5,
            'diesel': 1.5,
        },
    )
    expected = (
        100000 * 0.15 / 1000 +
        2000 * 1.4 / 1000 +
        100 * 0.04 +
        300 * 1.5 / 1000 +
        200 * 1.5 / 1000
    )  # 口径：水不折算标准煤（DB37/T 2672-2019 附录B），不计入综合能耗
    assert yd.total_energy_tce == pytest.approx(round(expected, 4))


def test_yearly_energy_data_zero_coefficient_falls_back(monkeypatch):
    """持久化系数为 0 时应回退，而不是使用 0 计算。"""
    yd = indicators.YearlyEnergyData(
        year=2023,
        electricity_kwh=100000,
        coefficients={'electricity': 0},
    )
    monkeypatch.setattr(indicators, 'resolve_coefficient', lambda et: 0.1229)
    assert yd.get_coefficient('electricity') == pytest.approx(0.1229)


def test_compute_project_indicators_uses_persisted_coefficients(monkeypatch):
    monkeypatch.setattr(indicators, 'resolve_coefficient', lambda et: 0.9999)
    proj = AuditProject(
        base=ProjectBase(
            name='测试',
            unit_name='测试单位',
            institution_category='党政机关',
            building_area=1000,
            people_count=100,
        ),
        energy_yearly=[
            EnergyYearly(
                year=2023,
                electricity_kwh=100000,
                water_m3=5000,
                natural_gas_m3=2000,
                heating_energy_heat_gj=100,
                petrol_kg=300,
                diesel_kg=200,
                coefficients={
                    'electricity': 0.15,
                    'water': 0.3,
                    'natural_gas': 1.4,
                    'heat': 0.04,
                    'gasoline': 1.5,
                    'diesel': 1.5,
                },
            )
        ],
    )
    result = indicators.compute_project_indicators(proj)
    assert result['status'] == 'ok'
    total_kgce = result['yearly'][0]['per_capita_energy']['total_kgce']
    expected = (
        100000 * 0.15 +
        2000 * 1.4 +
        100 * 1000 * 0.04 +
        300 * 1.5 +
        200 * 1.5
    )  # 口径：水不折算标准煤（DB37/T 2672-2019 附录B），不计入综合能耗
    assert total_kgce == pytest.approx(expected)
