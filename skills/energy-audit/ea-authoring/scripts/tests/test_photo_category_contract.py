import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROJECT_DATA = load_module(
    "photo_contract_project_data",
    REPO_ROOT / "tools" / "energy_audit" / "project_data.py",
)
PHOTOS = load_module("prepare_report_photos_contract", ROOT / "prepare_report_photos.py")


class CanonicalPhotoCategoryTests(unittest.TestCase):
    def test_public_contract_uses_one_name_per_concept(self):
        categories = set(PROJECT_DATA.PHOTO_CATEGORIES)
        self.assertIn("缴费发票", categories)
        self.assertNotIn("能耗账单", categories)
        self.assertIn("建筑外观", categories)
        self.assertNotIn("各建筑外观", categories)

    def test_legacy_categories_normalize_at_the_boundary(self):
        normalize = getattr(PROJECT_DATA, "normalize_photo_category", None)
        self.assertTrue(callable(normalize), "缺少统一分类归一函数")
        self.assertEqual(normalize("能耗账单"), "缴费发票")
        self.assertEqual(normalize("各建筑外观"), "建筑外观")
        self.assertEqual(normalize(" 计量器具 "), "计量器具")

    def test_unknown_category_is_preserved_but_strict_writes_reject_it(self):
        normalize = getattr(PROJECT_DATA, "normalize_photo_category", None)
        self.assertTrue(callable(normalize), "缺少统一分类归一函数")
        self.assertEqual(normalize("旧项目自定义"), "旧项目自定义")
        with self.assertRaises(ValueError):
            normalize("旧项目自定义", strict=True)

    def test_image_item_normalizes_old_data_while_loading(self):
        image = PROJECT_DATA.ImageItem(path="invoice.png", category="能耗账单")
        self.assertEqual(image.category, "缴费发票")
        building = PROJECT_DATA.ImageItem(path="building.png", category="各建筑外观")
        self.assertEqual(building.category, "建筑外观")

    def test_equipment_photo_category_covers_database_categories(self):
        classify = getattr(PROJECT_DATA, "photo_category_for_equipment", None)
        self.assertTrue(callable(classify), "缺少设备照片分类映射")
        self.assertEqual(
            classify("厨房", name="燃气灶"),
            "厨房设备",
        )
        self.assertEqual(
            classify("动力", name="生活水泵"),
            "水泵/水箱",
        )
        self.assertEqual(
            classify("动力", name="客梯"),
            "其他用电设备",
        )
        self.assertEqual(
            classify("变配电", name="1号变压器"),
            "变压器/配电",
        )
        self.assertEqual(
            classify("特殊设备", name="信息中心服务器"),
            "信息机房",
        )

    def test_special_power_summary_normalizes_only_explicit_units(self):
        summarize = getattr(
            PROJECT_DATA, "special_power_summary", None
        )
        self.assertTrue(callable(summarize), "缺少特殊设备功率明细汇总")

        summary = summarize({
            "server_num": 12,
            "server_power": 0.5,
            "network_num": 8,
            "network_power": 0.2,
            "storage_num": 2,
            "storage_power": 0.6,
            "air_num": 2,
            "air_power": 4.5,
            "power_unit": "kW",
        })

        self.assertEqual(summary["total_power_kw"], 17.8)
        self.assertEqual(
            [item["name"] for item in summary["power_components"]],
            ["服务器", "网络设备", "存储设备", "空调设备"],
        )

        unknown = summarize({
            "server_num": 12,
            "server_power": 500,
            "power_unit": "",
        })

        self.assertIsNone(unknown["total_power_kw"])
        self.assertEqual(unknown["power_components"][0]["unit_power"], 500)

    def test_chapter6_route_applies_data_center_power_threshold(self):
        route = getattr(
            PROJECT_DATA, "chapter6_route_for_equipment", None
        )
        self.assertTrue(callable(route), "缺少第6章统一小节路由")

        large = route({
            "category": "特殊设备",
            "name": "数据中心/信息中心",
            "total_power_kw": 120,
        })
        boundary = route({
            "category": "特殊设备",
            "name": "数据中心/信息中心",
            "total_power_kw": 100,
        })
        unknown = route({
            "category": "特殊设备",
            "name": "数据中心/信息中心",
            "total_power_kw": None,
        })

        self.assertEqual(large["equipment_section_key"], "information_room")
        self.assertEqual(boundary["equipment_section_key"], "other_energy")
        self.assertEqual(unknown["equipment_section_key"], "other_energy")
        self.assertEqual(unknown["routing_reason"], "information_room_power_unconfirmed")

    def test_chapter6_route_splits_medical_equipment_by_hospital_level(self):
        route = PROJECT_DATA.chapter6_route_for_equipment
        equipment = {"category": "特殊设备", "name": "医疗设备"}

        second = route(equipment, unit_func="C", children_func="B")
        third = route(equipment, unit_func="C", children_func="C")
        first = route(equipment, unit_func="C", children_func="A")
        non_medical = route(equipment, unit_func="D", children_func="B")

        self.assertEqual(second["equipment_section_key"], "medical_equipment")
        self.assertEqual(third["equipment_section_key"], "medical_equipment")
        self.assertEqual(first["equipment_section_key"], "other_energy")
        self.assertEqual(non_medical["equipment_section_key"], "other_energy")

    def test_chapter6_route_keeps_other_devices_out_of_cooling_by_default(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        tower = route({"category": "其他设备", "name": "冷却塔"})
        makeup = route({"category": "其他设备", "name": "空调系统补水装置"})
        valve = route({"category": "其他设备", "name": "阀门"})
        terminal = route({"category": "末端设备", "name": "风机盘管"})

        self.assertEqual(tower["photo_section_key"], "air_heating")
        self.assertEqual(makeup["photo_section_key"], "air_heating")
        self.assertEqual(valve["photo_section_key"], "other_energy")
        self.assertEqual(valve["photo_category"], "其他用电设备")
        self.assertEqual(terminal["equipment_section_key"], "air_heating")

    def test_chapter6_route_keeps_water_pump_photo_with_other_electric_equipment(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        water_pump = route({"category": "动力", "name": "生活水泵"})
        gas_steam = route({"category": "蒸汽", "name": "燃气蒸汽锅炉"})
        gas_heater = route({"category": "生活热水", "name": "燃气热水锅炉"})
        electric_heater = route({"category": "生活热水", "name": "电热水器"})
        hot_water_absorption = route({
            "category": "生活热水",
            "name": "吸收式溴化锂机组",
            "gas_value": 1200,
        })

        self.assertEqual(water_pump["equipment_section_key"], "other_energy")
        self.assertEqual(water_pump["photo_section_key"], "other_energy")
        self.assertEqual(water_pump["routing_reason"], "domestic_water_pump")
        self.assertEqual(gas_steam["equipment_section_key"], "gas_system")
        self.assertEqual(gas_steam["photo_section_key"], "gas_system")
        self.assertEqual(gas_heater["equipment_section_key"], "gas_system")
        self.assertEqual(gas_heater["photo_section_key"], "water_system")
        self.assertEqual(gas_heater["photo_category"], "用水设施")
        self.assertEqual(
            gas_heater["routing_reason"],
            "hot_water_combustion_photo_to_water_system",
        )
        self.assertEqual(electric_heater["equipment_section_key"], "other_energy")
        self.assertEqual(electric_heater["photo_section_key"], "water_system")
        self.assertEqual(electric_heater["photo_category"], "用水设施")
        self.assertEqual(
            hot_water_absorption["equipment_section_key"],
            "gas_system",
        )
        self.assertEqual(
            hot_water_absorption["photo_section_key"],
            "water_system",
        )

    def test_chapter6_route_uses_recorded_combustion_for_absorption_equipment(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        gas_absorption = route({
            "category": "空调",
            "name": "吸收式溴化锂机组",
            "gas_value": 1200,
        })
        oil_direct_fired = route({
            "category": "空调",
            "name": "直燃型溴化锂机组",
            "fuel_value": 3.5,
        })

        for routed in (gas_absorption, oil_direct_fired):
            self.assertEqual(routed["equipment_section_key"], "gas_system")
            self.assertEqual(routed["photo_section_key"], "gas_system")
            self.assertEqual(routed["photo_category"], "燃气设备")

    def test_chapter6_route_does_not_use_combustion_without_evidence(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        zero_gas = route({
            "category": "空调",
            "name": "吸收式溴化锂机组",
            "gas_value": 0,
        })
        blank_gas = route({
            "category": "空调",
            "name": "吸收式溴化锂机组",
            "gas_value": None,
        })
        electric_chiller = route({
            "category": "空调",
            "name": "水冷冷水机组",
            "gas_value": 1200,
        })

        for routed in (zero_gas, blank_gas, electric_chiller):
            self.assertEqual(routed["equipment_section_key"], "air_heating")
            self.assertEqual(routed["photo_section_key"], "air_heating")

    def test_chapter6_route_puts_all_hygiene_devices_in_water_system(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        toilet = route({"category": "卫生器具", "name": "蹲便器"})
        hygiene_pump = route({"category": "卫生器具", "name": "生活水泵"})

        self.assertEqual(toilet["equipment_section_key"], "water_system")
        self.assertEqual(toilet["photo_section_key"], "water_system")
        self.assertEqual(toilet["photo_category"], "用水设施")
        self.assertEqual(hygiene_pump["equipment_section_key"], "water_system")
        self.assertEqual(hygiene_pump["photo_section_key"], "water_system")

    def test_equipment_image_fields_keep_source_order_and_labels(self):
        extract = getattr(
            PROJECT_DATA, "extract_equipment_image_fields", None
        )
        self.assertTrue(callable(extract), "缺少设备图片字段语义提取")
        ids, fields = extract(
            {
                "device_name": "冷冻水泵",
                "motor_img": "301,302",
                "pump_img": "303",
                "device_img": "304",
            },
            "输配设备",
        )
        self.assertEqual(ids, [301, 302, 303, 304])
        self.assertEqual(
            [item["field"] for item in fields],
            ["motor_img", "pump_img", "device_img"],
        )
        self.assertEqual(
            [item["label"] for item in fields],
            ["电机铭牌图片", "泵体图片", "设备整体图片"],
        )

    def test_cooling_tower_field_labels_do_not_repeat_the_device_name(self):
        extract = PROJECT_DATA.extract_equipment_image_fields
        _ids, fields = extract(
            {
                "device_name": "冷却塔",
                "tower_img": "401",
                "fan_img": "402",
            },
            "输配设备",
        )
        self.assertEqual(
            [item["label"] for item in fields],
            ["参数铭牌/自动阀门图片", "参数铭牌/手动阀门图片"],
        )

    def test_other_equipment_uses_its_real_name_when_database_name_is_generic(self):
        display_name = getattr(
            PROJECT_DATA, "equipment_display_name", None
        )
        self.assertTrue(callable(display_name), "缺少其他设备真实名称规则")
        self.assertEqual(
            display_name(
                {
                    "device_name": "其他特殊设备",
                    "other_device_name": "某冷热源",
                },
                "空调",
            ),
            "某冷热源",
        )
        self.assertEqual(
            display_name(
                {
                    "device_name": "螺杆式冷水机组",
                    "other_device_name": "不应覆盖",
                },
                "空调",
            ),
            "螺杆式冷水机组",
        )

    def test_other_equipment_real_name_source_matches_each_device_table(self):
        display_name = PROJECT_DATA.equipment_display_name
        cases = (
            (
                "空调",
                {
                    "device_name": "其他特殊设备",
                    "other_device_name": "某冷热源",
                },
                "某冷热源",
            ),
            (
                "末端设备",
                {
                    "device_name": "其他特殊末端设备",
                    "other_device_name": "风机盘管",
                },
                "风机盘管",
            ),
            (
                "照明",
                {
                    "device_name": "其他特殊灯具等",
                    "other_device_name": "面板灯",
                },
                "面板灯",
            ),
            (
                "办公",
                {
                    "device_name": "大屏",
                    "type": "其他特殊办公设备",
                },
                "大屏",
            ),
            (
                "特殊设备",
                {
                    "device_name": "其他特殊设备",
                    "other_device_name": "信息中心",
                },
                "信息中心",
            ),
        )
        for category, record, expected in cases:
            with self.subTest(category=category):
                self.assertEqual(display_name(record, category), expected)

    def test_explicit_device_name_is_never_overwritten_by_alias_field(self):
        display_name = PROJECT_DATA.equipment_display_name
        self.assertEqual(
            display_name(
                {
                    "device_name": "燃气热水锅炉",
                    "other_device_name": "不应覆盖",
                },
                "其他设备",
            ),
            "燃气热水锅炉",
        )

    def test_generic_name_without_real_name_stays_visible_for_data_review(self):
        display_name = PROJECT_DATA.equipment_display_name
        self.assertEqual(
            display_name(
                {"device_name": "其他特殊设备"},
                "空调",
            ),
            "其他特殊设备",
        )
        self.assertEqual(
            display_name(
                {
                    "device_name": "其他特殊设备",
                    "other_device_name": "其他",
                },
                "空调",
            ),
            "其他特殊设备",
        )

    def test_information_room_requires_specific_evidence(self):
        is_information_room = PROJECT_DATA.is_information_room_equipment

        for name in ("电梯机房", "消防机房", "水泵机房", "空调机房"):
            self.assertFalse(is_information_room({
                "category": "特殊设备",
                "name": name,
            }))

        for name in (
            "数据中心/信息中心",
            "信息机房",
            "数据机房",
            "服务器",
            "网络设备",
            "存储设备",
        ):
            self.assertTrue(is_information_room({
                "category": "特殊设备",
                "name": name,
            }))

    def test_medical_institution_uses_platform_code_as_authority(self):
        is_medical = PROJECT_DATA.is_medical_institution

        self.assertTrue(is_medical("C", "其他", ""))
        self.assertFalse(is_medical("D", "医疗", "某某医院"))
        self.assertTrue(is_medical("", "医疗", ""))
        self.assertTrue(is_medical("", "", "日照市某医院"))
        self.assertFalse(is_medical("", "机关", "某机关单位"))

    def test_hospital_level_accepts_platform_and_chinese_values(self):
        normalize = PROJECT_DATA.normalize_hospital_level

        self.assertEqual(normalize("A"), "A")
        self.assertEqual(normalize("一级"), "A")
        self.assertEqual(normalize("二级甲等"), "B")
        self.assertEqual(normalize("三级医院"), "C")
        self.assertEqual(normalize("未评级"), "")

    def test_equipment_photo_slots_expand_each_attachment_id(self):
        slots = PROJECT_DATA.equipment_photo_slots({
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "img_fields": [{
                "field": "system_img",
                "label": "系统图片",
                "ids": [101, "102"],
            }],
            "img_ids": [101, "102"],
        })

        self.assertEqual([slot["file_id"] for slot in slots], ["101", "102"])
        self.assertEqual(
            [slot["caption_label"] for slot in slots],
            ["数据中心/信息中心", "数据中心/信息中心"],
        )
        self.assertEqual([slot["attachment_index"] for slot in slots], [0, 1])

    def test_equipment_photo_slots_include_flat_ids_missing_from_fields(self):
        slots = PROJECT_DATA.equipment_photo_slots({
            "name": "冷冻水泵",
            "category": "输配设备",
            "img_fields": [{
                "field": "device_img",
                "label": "设备图片",
                "ids": [101],
            }],
            "img_ids": [101, 201],
        })

        self.assertEqual([slot["file_id"] for slot in slots], ["101", "201"])

    def test_information_room_rows_are_atomic_without_group_evidence(self):
        route = PROJECT_DATA.chapter6_route_for_equipment

        first = route({
            "id": 1,
            "category": "特殊设备",
            "name": "数据中心/信息中心",
            "other_device_name": "数据中心",
            "total_power_kw": 80,
        })
        second = route({
            "id": 2,
            "category": "特殊设备",
            "name": "数据中心/信息中心",
            "other_device_name": "数据中心",
            "total_power_kw": 80,
        })

        self.assertEqual(first["equipment_section_key"], "other_energy")
        self.assertEqual(second["equipment_section_key"], "other_energy")


class PhotoManagerContractTests(unittest.TestCase):
    def setUp(self):
        path = REPO_ROOT / "tools" / "energy_audit" / "photo_manager.py"
        self.assertTrue(path.is_file(), "镜像仓缺少 photo_manager.py，分类契约无法统一")
        self.photo_manager = load_module("photo_manager_contract", path)

    def test_requirements_only_reference_canonical_categories(self):
        canonical = set(PROJECT_DATA.PHOTO_CATEGORIES)
        referenced = {
            category
            for requirements in self.photo_manager.PHOTO_REQUIREMENTS.values()
            for category, _desc, _path_hint in requirements
        }
        self.assertEqual(referenced - canonical, set())

    def test_optional_system_photos_do_not_block_checklist(self):
        project = PROJECT_DATA.AuditProject(
            base=PROJECT_DATA.ProjectBase(name="测试", unit_name="测试单位")
        )
        _ok, missing = self.photo_manager.check_photos(project)
        missing_text = "\n".join(missing)
        for optional in ("建筑外观", "厨房设备", "医疗设备", "变压器/配电", "水泵/水箱"):
            self.assertNotIn(optional, missing_text)

    def test_water_pump_photo_path_points_to_other_electric_equipment(self):
        requirement = next(
            item
            for item in self.photo_manager.PHOTO_REQUIREMENTS["第6章"]
            if item[0] == "水泵/水箱"
        )
        self.assertEqual(requirement[2], "chapter6.images.other_energy")


class PrepareReportPhotosContractTests(unittest.TestCase):
    def test_ch6_pool_contains_all_classified_device_photos(self):
        canonical = set(PROJECT_DATA.PHOTO_CATEGORIES)
        self.assertLessEqual(PHOTOS.CH6_DEVICE_CATS, canonical)
        for category in ("变压器/配电", "水泵/水箱", "厨房设备"):
            self.assertIn(category, PHOTOS.CH6_DEVICE_CATS)

    def test_generic_machine_room_does_not_trigger_information_room_fallback(self):
        category_hints = dict(
            (word, category)
            for words, category in PHOTOS.CH6_CAT_HINTS
            for word in words
        )
        keyword_hints = dict(PHOTOS.CH6_KEYWORDS)

        self.assertNotIn("机房", category_hints)
        self.assertNotIn("机房", keyword_hints["数据中心"])
        self.assertIn("数据机房", category_hints)
        self.assertIn("信息中心", keyword_hints["数据中心"])

    def test_report_photo_route_replaces_stale_air_heating_with_gas_system(self):
        routed = PHOTOS._route_chapter6_equipment(
            [{
                "name": "吸收式溴化锂机组",
                "category": "空调",
                "gas_value": 1200,
                "photo_section_key": "air_heating",
                "photo_section_title": "空调与供暖系统",
                "routing_reason": "空调_equipment",
            }],
            {},
        )

        self.assertEqual(routed[0]["photo_section_key"], "gas_system")
        self.assertEqual(
            routed[0]["routing_reason"],
            "recorded_combustion_equipment",
        )

    def test_pick_photo_accepts_legacy_building_alias(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = Path(td) / "门诊楼.png"
            image_path.write_bytes(b"not-used-by-picker")
            images = [{
                "path": str(image_path),
                "category": "各建筑外观",
                "building_name": "门诊楼",
            }]
            with mock.patch.object(PHOTOS.os.path, "isfile", return_value=True):
                picked = PHOTOS.pick_photo(
                    images, PHOTOS.BUILDING_CAT, building="门诊楼"
                )
            self.assertEqual(picked, str(image_path))


if __name__ == "__main__":
    unittest.main()
