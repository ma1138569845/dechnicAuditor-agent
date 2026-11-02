from tools.energy_audit.reporting_periods import (
    complete_report_years,
    incomplete_report_years,
)


def test_mid_year_building_start_is_excluded_from_complete_years():
    data = {
        "buildings": [{"begin_date": "2022-08", "end_date": ""}],
        "energy_yearly": [
            {"year": 2022, "electricity_kwh": 100},
            {"year": 2023, "electricity_kwh": 100},
            {"year": 2024, "electricity_kwh": 100},
        ],
    }

    incomplete = incomplete_report_years(data)

    assert 2022 in incomplete
    assert "2022年8月投入使用" in "；".join(incomplete[2022])
    assert complete_report_years(data) == [2023, 2024]


def test_partial_monthly_series_is_excluded_even_without_building_dates():
    data = {
        "energy_yearly": [
            {
                "year": 2022,
                "electricity_kwh": 100,
                "monthly_electricity_kwh": [
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    10,
                    10,
                    10,
                    10,
                    10,
                ],
            }
        ]
    }

    incomplete = incomplete_report_years(data)

    assert 2022 in incomplete
    assert "仅覆盖 5 个月" in "；".join(incomplete[2022])


def test_annual_only_water_data_does_not_make_complete_year_incomplete():
    data = {
        "buildings": [{"begin_date": "2022-01", "end_date": ""}],
        "energy_yearly": [
            {
                "year": 2024,
                "electricity_kwh": 1200,
                "monthly_electricity_kwh": [100] * 12,
                "water_m3": 80,
                "monthly_water_m3": None,
            }
        ],
    }

    assert incomplete_report_years(data) == {}
    assert complete_report_years(data) == [2024]


def test_explicit_incomplete_flag_overrides_available_totals():
    data = {
        "energy_yearly": [
            {
                "year": 2021,
                "year_complete": False,
                "electricity_kwh": 100,
            }
        ]
    }

    assert 2021 in incomplete_report_years(data)
