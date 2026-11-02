"""Report-period completeness helpers.

Annual tables may contain only calendar years backed by a complete 12-month
reporting period. Narrative text can still explain a partial year.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import re
from typing import Any, Mapping


_FALSE_COMPLETE_FLAGS = (
    "report_complete",
    "year_complete",
    "is_complete_year",
    "complete_year",
    "data_complete",
)
_TRUE_INCOMPLETE_FLAGS = ("incomplete", "is_incomplete")
_MONTHLY_SERIES = (
    ("monthly_electricity_kwh", "electricity_kwh", "用电"),
    ("monthly_water_m3", "water_m3", "用水"),
    ("monthly_natural_gas_m3", "natural_gas_m3", "天然气"),
)
_DATE_PATTERN = re.compile(
    r"^\s*(?P<year>\d{4})\s*[-/.年]\s*(?P<month>\d{1,2})"
)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _has_month_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, str) and value.strip() in {"—", "-", "N/A", "n/a"}:
        return False
    return True


def _month_from_date(value: Any) -> tuple[int, int] | None:
    if isinstance(value, datetime):
        return value.year, value.month
    if isinstance(value, date):
        return value.year, value.month
    match = _DATE_PATTERN.match(str(value or ""))
    if not match:
        return None
    year = _as_int(match.group("year"))
    month = _as_int(match.group("month"))
    if year is None or month is None or not 1 <= month <= 12:
        return None
    return year, month


def incomplete_report_years(
    project_data: Mapping[str, Any] | None,
) -> dict[int, tuple[str, ...]]:
    """Return calendar years that must not appear in annual report tables.

    Detection uses explicit completeness flags, building operation dates, and
    partially filled monthly series. A missing monthly series alone is not
    treated as incomplete because some projects provide annual totals only.
    """

    data = project_data or {}
    reasons: dict[int, list[str]] = defaultdict(list)

    for year_row in data.get("energy_yearly") or []:
        if not isinstance(year_row, Mapping):
            continue
        year = _as_int(year_row.get("year"))
        if year is None:
            continue
        if any(year_row.get(flag) is False for flag in _FALSE_COMPLETE_FLAGS):
            reasons[year].append("数据标注为不完整年度")
        if any(year_row.get(flag) is True for flag in _TRUE_INCOMPLETE_FLAGS):
            reasons[year].append("数据标注为不完整年度")

        for monthly_key, annual_key, label in _MONTHLY_SERIES:
            months = year_row.get(monthly_key)
            if not isinstance(months, (list, tuple)) or not months:
                continue
            annual = 0.0
            try:
                annual = float(year_row.get(annual_key) or 0)
            except (TypeError, ValueError):
                annual = 0.0
            observed = sum(1 for value in months if _has_month_value(value))
            if annual > 0 and (
                len(months) < 12 or observed < 12
            ):
                reasons[year].append(
                    f"{label}逐月数据仅覆盖 {observed} 个月"
                )

    for building in data.get("buildings") or []:
        if not isinstance(building, Mapping):
            continue
        begin = _month_from_date(
            building.get("begin_date")
            or building.get("operation_date")
            or building.get("commissioning_date")
        )
        if begin and begin[1] > 1:
            reasons[begin[0]].append(
                f"建筑自 {begin[0]}年{begin[1]}月投入使用"
            )
        end = _month_from_date(
            building.get("end_date")
            or building.get("decommissioning_date")
        )
        if end and end[1] < 12:
            reasons[end[0]].append(
                f"建筑运行至 {end[0]}年{end[1]}月"
            )

    return {
        year: tuple(dict.fromkeys(year_reasons))
        for year, year_reasons in sorted(reasons.items())
    }


def complete_report_years(
    project_data: Mapping[str, Any] | None,
    years: list[int] | tuple[int, ...] | None = None,
) -> list[int]:
    """Return complete calendar years in ascending order."""

    data = project_data or {}
    if years is None:
        years = [
            year
            for row in (data.get("energy_yearly") or [])
            if isinstance(row, Mapping)
            for year in [_as_int(row.get("year"))]
            if year is not None
        ]
    incomplete = incomplete_report_years(data)
    return sorted({int(year) for year in years if int(year) not in incomplete})
