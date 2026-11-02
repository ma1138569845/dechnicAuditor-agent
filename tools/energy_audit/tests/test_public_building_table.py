from tools.energy_audit.public_building_table import (
    expected_public_building_table_labels,
    format_public_building_table_values,
    missing_or_misordered_fields,
    table_label_rows,
    table_rows,
)


def test_catalog_has_fixed_16_fields_in_8_rows():
    assert expected_public_building_table_labels() == (
        "建筑物名称",
        "建筑面积（m²）",
        "建筑地址",
        "投用年份",
        "建筑层数",
        "建筑高度（m）",
        "建筑结构形式",
        "建筑透明围护结构",
        "夏季空调冷源",
        "冬季供暖热源",
        "夏季空调末端形式",
        "冬季供暖末端形式",
        "建筑外墙保温",
        "生活热水系统",
        "建筑给水系统",
        "能耗在线监测系统",
    )
    assert [len(row) for row in table_label_rows()] == [2] * 8


def test_building_values_are_formatted_and_unresolved_address_becomes_dash():
    unresolved_address = "{" * 2 + "ADDRESS_" + "puapbqh2" + "}" * 2
    values = format_public_building_table_values(
        {
            "name": "专家公寓",
            "area": 19418.41,
            "address": unresolved_address,
            "year": 2022,
            "insulation": "外墙保温",
            "wall_material": "无机轻集料保温砂浆",
            "warm_state": "完好",
            "cooling_source": "空气源热泵",
        }
    )

    assert values["area"] == "19418.41"
    assert values["address"] == "—"
    assert values["year"] == "2022"
    assert values["insulation"] == "外墙保温"
    assert values["structure"] == "—"
    assert "无机轻集料保温砂浆" not in values["insulation"]
    assert "完好" not in values["insulation"]


def test_table_rows_are_four_columns_and_eight_rows_with_raw_values():
    rows = table_rows(
        {
            "name": "专家公寓",
            "area": 19418.41,
            "address": "——",
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
            "hot_water": "空气源热泵热水系统（4台热水机组，分一区、二区）",
            "water_system": "市政供水，经创新大厦C座水泵房加压后分高低区供给",
            "monitoring": "有",
        }
    )

    assert len(rows) == 8
    assert all(len(row) == 4 for row in rows)
    assert rows[0][0:2] == ("建筑物名称", "专家公寓")
    assert rows[0][2:4] == ("建筑面积（m²）", "19418.41")
    assert rows[3][0:2] == ("建筑结构形式", "钢筋混凝土框架核心筒")
    assert rows[3][2:4] == ("建筑透明围护结构", "中空双层玻璃窗")
    assert rows[6][0:2] == ("建筑外墙保温", "外墙保温")


def test_zero_is_preserved_but_blank_and_placeholder_values_use_dash():
    values = format_public_building_table_values(
        {
            "year": 0,
            "height": "",
            "water_system": "{{WATER_SYSTEM_x}}",
            "monitoring": None,
        }
    )

    assert values["year"] == "0"
    assert values["height"] == "—"
    assert values["water_system"] == "—"
    assert values["monitoring"] == "—"


def test_missing_or_misordered_fields_reports_missing_and_order_breaks():
    valid = [cell for row in table_rows({}) for cell in row]
    labels = valid[0::2]
    assert missing_or_misordered_fields(labels) == ()

    missing_one = tuple(item for i, item in enumerate(labels) if i != 3)
    assert missing_or_misordered_fields(missing_one) == ("缺字段：投用年份",)

    swapped = list(labels)
    swapped[2], swapped[4] = swapped[4], swapped[2]
    assert missing_or_misordered_fields(swapped) == ("字段顺序错误：建筑地址",)
