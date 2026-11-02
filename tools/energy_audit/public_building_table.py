"""Public-building-only catalog for the chapter 2 building information table."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PublicBuildingTableField:
    index: int
    key: str
    label: str
    required: bool = True
    value_format: str = "raw_text"


PUBLIC_BUILDING_TABLE_FIELDS: tuple[PublicBuildingTableField, ...] = (
    PublicBuildingTableField(1, "name", "建筑物名称"),
    PublicBuildingTableField(2, "area", "建筑面积（m²）"),
    PublicBuildingTableField(3, "address", "建筑地址"),
    PublicBuildingTableField(4, "year", "投用年份"),
    PublicBuildingTableField(5, "floors", "建筑层数"),
    PublicBuildingTableField(6, "height", "建筑高度（m）"),
    PublicBuildingTableField(7, "structure", "建筑结构形式"),
    PublicBuildingTableField(8, "window_type", "建筑透明围护结构"),
    PublicBuildingTableField(9, "cooling_source", "夏季空调冷源"),
    PublicBuildingTableField(10, "heating_source", "冬季供暖热源"),
    PublicBuildingTableField(11, "cooling_terminal", "夏季空调末端形式"),
    PublicBuildingTableField(12, "heating_terminal", "冬季供暖末端形式"),
    PublicBuildingTableField(13, "insulation", "建筑外墙保温"),
    PublicBuildingTableField(14, "hot_water", "生活热水系统"),
    PublicBuildingTableField(15, "water_system", "建筑给水系统"),
    PublicBuildingTableField(16, "monitoring", "能耗在线监测系统"),
)

_MISSING_VALUE = "—"
_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^{}]+\}\}")


def expected_public_building_table_labels() -> tuple[str, ...]:
    return tuple(field.label for field in PUBLIC_BUILDING_TABLE_FIELDS)


def table_label_rows() -> tuple[tuple[str, str], ...]:
    labels = expected_public_building_table_labels()
    return tuple((labels[index], labels[index + 1]) for index in range(0, len(labels), 2))


def _display_value(value: Any) -> str:
    if value is None:
        return _MISSING_VALUE
    rendered = str(value).strip()
    if not rendered or _PLACEHOLDER_PATTERN.search(rendered):
        return _MISSING_VALUE
    return rendered


def format_public_building_table_values(
    building: Mapping[str, Any],
) -> dict[str, str]:
    return {
        field.key: _display_value(building.get(field.key))
        for field in PUBLIC_BUILDING_TABLE_FIELDS
    }


def table_rows(
    building: Mapping[str, Any],
) -> tuple[tuple[str, str, str, str], ...]:
    values = format_public_building_table_values(building)
    fields = PUBLIC_BUILDING_TABLE_FIELDS
    return tuple(
        (
            fields[index].label,
            values[fields[index].key],
            fields[index + 1].label,
            values[fields[index + 1].key],
        )
        for index in range(0, len(fields), 2)
    )


def missing_or_misordered_fields(labels: Sequence[str]) -> tuple[str, ...]:
    expected = expected_public_building_table_labels()
    actual = tuple(labels)

    missing = tuple(f"缺字段：{label}" for label in expected if label not in actual)
    unexpected = tuple(f"未知字段：{label}" for label in actual if label not in expected)
    if missing or unexpected:
        return missing + unexpected

    for position, expected_label in enumerate(expected):
        if actual[position] != expected_label:
            return (f"字段顺序错误：{expected_label}",)
    return ()
