"""Select chapter 1 audit bases for public-building reports.

The selector keeps one authoritative catalog in code so the writing contract
and report QA use the same applicability decisions.  It deliberately separates
standards that apply directly from standards that can only be cited by analogy.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


ZJ_HOTEL_STANDARD_ID = "DB33/T 760-2023"
ZJ_HOTEL_STANDARD_TITLE = "《旅游饭店单位综合能耗限额及计算方法》"


@dataclass(frozen=True)
class AuditBasis:
    key: str
    citation: str
    applicability: str = ""
    reason: str = ""


_COMMON_BASES: tuple[AuditBasis, ...] = (
    AuditBasis(
        "energy_conservation_law",
        "《中华人民共和国节约能源法》（2016年）",
        reason="公共建筑能源审计的通用法律依据",
    ),
    AuditBasis(
        "public_building_audit_guideline",
        "《公共建筑能源审计技术导则》（2016年）",
        reason="公共建筑能源审计程序依据",
    ),
    AuditBasis(
        "general_energy_calculation",
        "《综合能耗计算通则》（GB/T 2589-2020）",
        reason="综合能耗计算依据",
    ),
    AuditBasis(
        "energy_metering",
        "《用能单位能源计量器具配备和管理通则》（GB 17167-2016）",
        reason="能源计量器具配备与核查依据",
    ),
)

_RETROFIT_BASES: tuple[AuditBasis, ...] = (
    AuditBasis(
        "building_energy_general",
        "《建筑节能与可再生能源利用通用规范》（GB 55015-2021）",
        reason="既有建筑节能分析与改造方向的技术依据",
    ),
    AuditBasis(
        "public_building_retrofit",
        "《公共建筑节能改造技术规范》（JGJ 176-2009）",
        reason="既有公共建筑节能改造建议的技术依据",
    ),
)

_HVAC_BASES: tuple[AuditBasis, ...] = (
    AuditBasis(
        "hvac_operation",
        "《空调通风系统运行管理标准》（GB 50365-2019）",
        reason="项目配置供暖空调系统",
    ),
    AuditBasis(
        "hvac_design",
        "《民用建筑供暖通风与空气调节设计规范》（GB 50736-2016）",
        reason="供暖空调系统分析与改造技术参考",
    ),
)

_WATER_BASES: tuple[AuditBasis, ...] = (
    AuditBasis(
        "building_water_design",
        "《建筑给水排水设计标准》（GB 50015-2019）",
        reason="项目具有建筑给水或生活热水系统",
    ),
)

_ELECTRICITY_BASES: tuple[AuditBasis, ...] = (
    AuditBasis(
        "building_electrical_design",
        "《民用建筑电气设计标准》（GB 51348-2019）",
        reason="项目具有建筑用电系统",
    ),
    AuditBasis(
        "power_supply_design",
        "《供配电系统设计规范》（GB 50052-2009）",
        reason="项目具有供配电系统",
    ),
    AuditBasis(
        "building_lighting",
        "《建筑照明设计标准》（GB/T 50034-2024）",
        reason="项目具有建筑照明及用电设备",
    ),
)

_HVAC_KEYS = (
    "cooling_source",
    "heating_source",
    "cooling_terminal",
    "heating_terminal",
)
_WATER_KEYS = ("water_system", "hot_water", "fire_system")
_HVAC_WORDS = ("空调", "热泵", "冷源", "热源", "供暖", "采暖", "冷水机组")
_WATER_WORDS = ("供水", "给水", "热水", "用水", "水泵", "浴室")
_APARTMENT_WORDS = ("公寓", "专家公寓", "人才公寓")
_HOTEL_WORDS = ("饭店", "酒店", "宾馆", "旅馆", "hotel")
_OFFICE_WORDS = ("办公", "行政机关", "机关")
_VENUE_WORDS = ("场馆", "科技馆", "文化馆", "博物馆")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _has_value(value: Any) -> bool:
    text = _text(value).lower()
    return text not in {"", "0", "0.0", "none", "null", "false", "no", "无", "—"}


def _iter_mappings(values: Any) -> Sequence[Mapping[str, Any]]:
    if not isinstance(values, list):
        return ()
    return tuple(item for item in values if isinstance(item, Mapping))


def _building_records(data: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return _iter_mappings(data.get("buildings"))


def _equipment_records(data: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    return _iter_mappings(data.get("equipment"))


def _has_hvac_system(data: Mapping[str, Any]) -> bool:
    for building in _building_records(data):
        if any(_has_value(building.get(key)) for key in _HVAC_KEYS):
            return True
    for equipment in _equipment_records(data):
        text = " ".join(
            _text(equipment.get(key))
            for key in ("name", "category", "remark")
        )
        if any(word in text for word in _HVAC_WORDS):
            return True
    return False


def _has_water_system(data: Mapping[str, Any]) -> bool:
    for building in _building_records(data):
        if any(_has_value(building.get(key)) for key in _WATER_KEYS):
            return True
    for row in _iter_mappings(data.get("energy_yearly")):
        if _has_value(row.get("water_m3")):
            return True
    metering = _mapping(data.get("metering"))
    return _has_value(metering.get("water_meters"))


def _has_electricity_system(data: Mapping[str, Any]) -> bool:
    if any(
        _has_value(row.get("electricity_kwh"))
        for row in _iter_mappings(data.get("energy_yearly"))
    ):
        return True
    metering = _mapping(data.get("metering"))
    return _has_value(metering.get("electric_meters"))


def _project_type_text(data: Mapping[str, Any]) -> str:
    base = _mapping(data.get("base"))
    public_building = _mapping(data.get("public_building"))
    parts = [
        base.get("unit_name"),
        base.get("institution_category"),
        base.get("specific_type"),
        public_building.get("subtype"),
    ]
    parts.extend(building.get("function") for building in _building_records(data))
    return " ".join(_text(part) for part in parts).lower()


def _type_specific_basis(data: Mapping[str, Any]) -> AuditBasis | None:
    public_building = _mapping(data.get("public_building"))
    subtype = _text(public_building.get("subtype")).lower()
    text = _project_type_text(data)

    if subtype == "hotel" or any(word in text for word in _HOTEL_WORDS):
        if any(word in text for word in _APARTMENT_WORDS):
            applicability = "参照"
            reason = "专家公寓等公寓类建筑不在旅游饭店标准直接适用对象内"
        else:
            applicability = ""
            reason = "旅游饭店直接适用"
        return AuditBasis(
            "zhejiang_hotel_quota",
            ZJ_HOTEL_STANDARD_TITLE,
            applicability,
            reason,
        )

    if subtype in {"agency_office", "venue"} or any(
        word in text for word in _OFFICE_WORDS + _VENUE_WORDS
    ):
        direct = subtype in {"agency_office", "venue"} or any(
            word in text for word in ("行政机关", "场馆", "科技馆", "文化馆", "博物馆")
        )
        return AuditBasis(
            "zhejiang_office_venue_quota",
            "《行政机关、场馆能耗定额及计算方法》（DB33/T 736-2021）",
            "" if direct else "参照",
            (
                "行政机关或场馆直接适用"
                if direct
                else "科研办公等非标准直接列举对象，仅可按相近口径参照"
            ),
        )
    return None


def select_public_building_audit_basis(
    data: Mapping[str, Any],
    *,
    include_retrofit: bool = True,
) -> tuple[AuditBasis, ...]:
    """Return de-duplicated bases applicable to one public-building project."""
    selected: list[AuditBasis] = list(_COMMON_BASES)
    if include_retrofit:
        selected.extend(_RETROFIT_BASES)

    type_basis = _type_specific_basis(data)
    if type_basis is not None:
        selected.append(type_basis)

    if _has_hvac_system(data):
        selected.extend(_HVAC_BASES)
    if _has_water_system(data):
        selected.extend(_WATER_BASES)
        selected.append(
            AuditBasis(
                "zhejiang_water_quota",
                "《浙江省用（取）水定额》（2019年）",
                reason="项目具有实际用水或给水系统",
            )
        )
    if _has_electricity_system(data):
        selected.extend(_ELECTRICITY_BASES)

    seen: set[str] = set()
    unique: list[AuditBasis] = []
    for basis in selected:
        if basis.key in seen:
            continue
        seen.add(basis.key)
        unique.append(basis)
    return tuple(unique)


def render_public_building_audit_basis(
    data: Mapping[str, Any],
    *,
    include_retrofit: bool = True,
) -> tuple[str, ...]:
    """Render chapter 1.6 items as Markdown unordered-list lines."""
    items = []
    for basis in select_public_building_audit_basis(
        data, include_retrofit=include_retrofit
    ):
        prefix = f"{basis.applicability}" if basis.applicability else ""
        items.append(f"- {prefix}{basis.citation}；")
    items.append("- 调研资料及其他相关资料。")
    return tuple(items)


def _month_end(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def format_full_period(value: Any) -> str:
    """Normalize a project period to ``YYYY年M月D日—YYYY年M月D日``."""
    text = _text(value).replace("－", "-").replace("–", "-").replace("—", "-")
    if not text:
        return ""

    chinese = re.fullmatch(
        r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?\s*-\s*"
        r"(\d{4})年(\d{1,2})月(?:(\d{1,2})日)?",
        text,
    )
    if chinese:
        sy, sm, sd, ey, em, ed = chinese.groups()
        start_year, start_month = int(sy), int(sm)
        end_year, end_month = int(ey), int(em)
        start_day = int(sd) if sd else 1
        end_day = int(ed) if ed else _month_end(end_year, end_month)
        return (
            f"{start_year}年{start_month}月{start_day}日"
            f"—{end_year}年{end_month}月{end_day}日"
        )

    iso = re.fullmatch(
        r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?\s*-\s*"
        r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?",
        text,
    )
    if iso:
        sy, sm, sd, ey, em, ed = iso.groups()
        start_year, start_month = int(sy), int(sm)
        end_year, end_month = int(ey), int(em)
        start_day = int(sd) if sd else 1
        end_day = int(ed) if ed else _month_end(end_year, end_month)
        return (
            f"{start_year}年{start_month}月{start_day}日"
            f"—{end_year}年{end_month}月{end_day}日"
        )

    single_year = re.fullmatch(r"(\d{4})年?", text)
    if single_year:
        year = int(single_year.group(1))
        return f"{year}年1月1日—{year}年12月31日"
    return _text(value)


def format_month_range(start: Any, end: Any) -> str:
    """Format separate ``YYYY-MM`` values as a Chinese month range."""
    start_text = _text(start)
    end_text = _text(end)
    start_match = re.fullmatch(r"(\d{4})-(\d{1,2})", start_text)
    end_match = re.fullmatch(r"(\d{4})-(\d{1,2})", end_text)
    if not (start_match and end_match):
        return ""
    return (
        f"{int(start_match.group(1))}年{int(start_match.group(2))}月"
        f"—{int(end_match.group(1))}年{int(end_match.group(2))}月"
    )
