import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_module(name, path, module_name=None):
    spec = importlib.util.spec_from_file_location(module_name or name, path)
    module = importlib.util.module_from_spec(spec)
    if module_name:
        sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def install_module(name, module):
    module.__name__ = name
    sys.modules[name] = module
    return module


def package(name, path):
    module = ModuleType(name)
    module.__path__ = [str(path)]
    return install_module(name, module)


TOOLS = package("tools", REPO_ROOT / "tools")
ENERGY_AUDIT = package(
    "tools.energy_audit",
    REPO_ROOT / "tools" / "energy_audit",
)
TOOLS.energy_audit = ENERGY_AUDIT

PROJECT_DATA = install_module(
    "tools.energy_audit.project_data",
    load_module(
        "chapter6_data_chain_project_data",
        REPO_ROOT / "tools" / "energy_audit" / "project_data.py",
    ),
)
ENERGY_AUDIT.project_data = PROJECT_DATA

DB_CONFIG = install_module("tools.energy_audit.db_config", ModuleType("tools.energy_audit.db_config"))
DB_CONFIG.get_pg_config = lambda config=None: config or {}

QUERY = install_module(
    "tools.energy_audit.pg_query",
    load_module(
        "chapter6_data_chain_query",
        REPO_ROOT / "tools" / "energy_audit" / "pg_query.py",
        "tools.energy_audit.pg_query",
    ),
)
ENERGY_AUDIT.PgDataQuery = QUERY.PgDataQuery

PATHS = install_module("tools.energy_audit._paths", ModuleType("tools.energy_audit._paths"))
PATHS.PROJECT_ROOT = REPO_ROOT

INDICATORS = install_module(
    "tools.energy_audit.indicators",
    ModuleType("tools.energy_audit.indicators"),
)
INDICATORS.compute_project_indicators = lambda project: {}
INDICATORS.COEFFICIENT_RANGES = {}

CLASSIFIER = install_module(
    "tools.energy_audit.institution_classifier",
    ModuleType("tools.energy_audit.institution_classifier"),
)
CLASSIFIER.classify_institution = lambda *args, **kwargs: ("未分类", "")

DEPT_DICT = install_module(
    "tools.energy_audit.dept_dict",
    ModuleType("tools.energy_audit.dept_dict"),
)
DEPT_DICT.classify_from_codes = lambda *args, **kwargs: ("未分类", "")

FILE_RESOLVER = install_module(
    "tools.energy_audit.file_resolver",
    ModuleType("tools.energy_audit.file_resolver"),
)
for _name in (
    "enrich_energy_saving_images",
    "enrich_management_info",
    "enrich_meter_ledger",
    "resolve_attachment_urls",
    "download_attachment_images",
):
    setattr(FILE_RESOLVER, _name, lambda *args, **kwargs: None)
FILE_RESOLVER.parse_file_ids = lambda value: []

COLLECTOR = install_module(
    "tools.energy_audit.pg_collector",
    load_module(
        "chapter6_data_chain_collector",
        REPO_ROOT / "tools" / "energy_audit" / "pg_collector.py",
        "tools.energy_audit.pg_collector",
    ),
)


class WaterAuxImageChainTests(unittest.TestCase):
    def test_water_aux_rows_preserve_device_and_named_upload_fields(self):
        pg = SimpleNamespace(
            get_water_greening=lambda customer_id: [{
                "irrigation_type": "全部浇灌",
                "irrigation_source": "市政自来水",
                "device_img": "2113446598588964864",
            }],
            get_water_other=lambda customer_id: [],
            get_water_road=lambda customer_id: [],
        )
        result = {"found": {}, "missing": []}

        COLLECTOR.collect_water_aux(pg, 1, result)

        item = result["found"]["water_aux"]["greening"][0]
        self.assertEqual(item["img_ids"], [2113446598588964864])
        self.assertEqual(item["img_fields"][0]["field"], "device_img")
        self.assertEqual(
            item["img_fields"][0]["ids"],
            [2113446598588964864],
        )


class Chapter6DeviceQueryChainTests(unittest.TestCase):
    def test_all_devices_includes_terminal_table(self):
        pg = SimpleNamespace(
            get_device_air=lambda customer_id: [],
            get_device_light=lambda customer_id: [],
            get_device_office=lambda customer_id: [],
            get_device_power=lambda customer_id: [],
            get_device_hygiene=lambda customer_id: [],
            get_device_hotwater=lambda customer_id: [],
            get_device_other=lambda customer_id: [],
            get_device_special=lambda customer_id: [],
            get_device_steam=lambda customer_id: [],
            get_device_td=lambda customer_id: [],
            get_device_terminal=lambda customer_id: [{"id": 1}],
            get_device_substation=lambda customer_id: [],
        )

        devices = QUERY.PgDataQuery.get_all_devices(pg, customer_id=88)

        self.assertEqual(devices["末端设备"], [{"id": 1}])

    def test_special_device_format_keeps_power_components_and_total(self):
        record = {
            "id": 9,
            "device_name": "数据中心/信息中心",
            "server_num": 12,
            "server_power": 0.5,
            "network_num": 8,
            "network_power": 0.2,
            "storage_num": 2,
            "storage_power": 0.6,
            "air_num": 2,
            "air_power": 4.5,
            "power_unit": "kW",
        }

        formatted = QUERY.PgDataQuery._fmt_device(record, "特殊设备")

        self.assertEqual(formatted["total_power_kw"], 17.8)
        self.assertEqual(len(formatted["power_components"]), 4)
        self.assertEqual(formatted["power_unit"], "kW")

    def test_collector_attaches_chapter6_route_to_every_equipment(self):
        collect = getattr(COLLECTOR, "_with_chapter6_routes", None)
        self.assertTrue(callable(collect), "缺少采集结果第6章路由接线")

        routed = collect(
            [{
                "category": "特殊设备",
                "name": "数据中心/信息中心",
                "total_power_kw": 17.8,
            }],
            unit_func="C",
            children_func="B",
            institution_category="医疗",
        )

        self.assertEqual(routed[0]["equipment_section_key"], "other_energy")
        self.assertEqual(routed[0]["photo_section_title"], "其他用电设备")
        self.assertEqual(
            routed[0]["routing_reason"],
            "information_room_power_le_100kw",
        )

    def test_collect_from_pg_returns_routed_equipment(self):
        class FakePg:
            version_code = "PX"

            def connect(self):
                pass

            def disconnect(self):
                pass

        pg_result = {
            "found": {
                "customer_info": {
                    "customer_func": "C",
                    "children_func": "B",
                },
                "equipment": [{
                    "category": "特殊设备",
                    "name": "数据中心/信息中心",
                    "total_power_kw": 17.8,
                }],
            },
            "missing": [],
            "project_id": 1,
        }

        with patch.object(COLLECTOR, "PgDataQuery", lambda **kwargs: FakePg()), \
                patch.object(COLLECTOR, "_collect_from_pg_impl", return_value=pg_result):
            result = COLLECTOR.collect_from_pg("测试单位")

        equipment = result["found"]["equipment"][0]
        self.assertEqual(equipment["equipment_section_key"], "other_energy")
        self.assertEqual(equipment["photo_section_title"], "其他用电设备")

    def test_merge_equipment_keeps_same_source_duplicates(self):
        pg = [
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "30kW",
                "img_ids": ["101"],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "30kW",
                "img_ids": ["102"],
            },
        ]

        merged = COLLECTOR._merge_equipment(pg)

        self.assertEqual(len(merged), 2)
        self.assertEqual([item.img_ids for item in merged], [["101"], ["102"]])

    def test_merge_equipment_merges_cross_source_photos_by_occurrence(self):
        pg = [
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "30kW",
                "img_ids": ["101"],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": ["101"],
                }],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "30kW",
                "img_ids": ["102"],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": ["102"],
                }],
            },
        ]
        excel = [
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "Excel不应覆盖",
                "img_ids": ["201"],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": ["201"],
                }],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "spec": "Excel不应覆盖",
                "img_ids": ["202"],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": ["202"],
                }],
            },
            {
                "category": "动力",
                "name": "补水泵",
                "spec": "5.5kW",
                "img_ids": ["203"],
            },
        ]

        merged = COLLECTOR._merge_equipment(pg, excel)

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0].spec, "30kW")
        self.assertEqual(merged[1].spec, "30kW")
        self.assertEqual(merged[0].img_ids, ["101", "201"])
        self.assertEqual(merged[1].img_ids, ["102", "202"])
        self.assertEqual(merged[2].name, "补水泵")
        self.assertEqual(merged[2].img_ids, ["203"])

    def test_merge_equipment_accepts_attachments_from_every_later_source(self):
        pg = [
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["101"],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["102"],
            },
        ]
        excel = [
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["201"],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["202"],
            },
        ]
        defaults = [
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["301"],
            },
            {
                "category": "动力",
                "name": "循环水泵",
                "img_ids": ["302"],
            },
        ]

        merged = COLLECTOR._merge_equipment(pg, excel, defaults)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].img_ids, ["101", "201", "301"])
        self.assertEqual(merged[1].img_ids, ["102", "202", "302"])


if __name__ == "__main__":
    unittest.main()
