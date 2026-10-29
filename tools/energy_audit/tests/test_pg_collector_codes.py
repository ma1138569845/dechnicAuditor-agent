import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _module(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _load_pg_collector():
    package = __import__("tools.energy_audit", fromlist=["energy_audit"])
    package.PgDataQuery = type("PgDataQuery", (), {})

    paths = _module("tools.energy_audit._paths")
    paths.PROJECT_ROOT = ROOT

    project_data = _module("tools.energy_audit.project_data")
    for name in (
        "AuditProject",
        "ProjectBase",
        "BuildingInfo",
        "EnergyYearly",
        "EnergyMonthly",
        "EnergyAnomaly",
        "Equipment",
        "MeteringInfo",
        "ManagementInfo",
        "EnergySaving",
        "SharedOfficeUnit",
        "TeamMember",
        "CoopMember",
        "ImageItem",
    ):
        setattr(project_data, name, type(name, (), {}))
    for name in (
        "save_project",
        "SourceResolver",
        "first_non_empty_source",
        "is_valid_coefficient",
        "total_building_area",
        "normalize_photo_category",
        "photo_category_for_equipment",
        "dedupe_image_items",
        "extract_equipment_image_fields",
        "chapter6_route_for_equipment",
    ):
        setattr(project_data, name, lambda *args, **kwargs: None)

    indicators = _module("tools.energy_audit.indicators")
    indicators.compute_project_indicators = lambda *args, **kwargs: {}
    indicators.COEFFICIENT_RANGES = {}

    classifier = _module("tools.energy_audit.institution_classifier")
    classifier.classify_institution = lambda name: ("未分类", "其他")

    file_resolver = _module("tools.energy_audit.file_resolver")
    for name in (
        "enrich_energy_saving_images",
        "enrich_management_info",
        "enrich_meter_ledger",
        "parse_file_ids",
        "resolve_attachment_urls",
        "download_attachment_images",
    ):
        setattr(file_resolver, name, lambda *args, **kwargs: None)

    path = ROOT / "tools" / "energy_audit" / "pg_collector.py"
    spec = importlib.util.spec_from_file_location(
        "pg_collector_under_test",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collector_uses_field_type_and_province_namespace():
    module = _load_pg_collector()
    category, resolved = module.resolve_customer_codes(
        {
            "field_type": "20",
            "customer_func": "B",
            "children_func": "",
            "province": "山东",
        }
    )
    assert category == "机关办公"
    assert resolved["public_building_subtype"] == "agency_office"
    assert resolved["dictionary_type"] == "public_build_type"


def test_collector_preserves_raw_codes_when_resolution_fails():
    module = _load_pg_collector()
    category, resolved = module.resolve_customer_codes(
        {
            "field_type": "20",
            "customer_func": "A",
            "children_func": "",
            "province": "山东",
        }
    )
    assert category == ""
    assert resolved["customer_func"] == "A"
    assert resolved["children_func"] == ""
    assert "A1/A2/A3" in resolved["error"]


def test_public_building_raw_codes_are_not_used_as_legacy_institution_codes():
    module = _load_pg_collector()
    _, resolved = module.resolve_customer_codes(
        {
            "field_type": "20",
            "customer_func": "C",
            "children_func": "",
            "province": "山东",
        }
    )
    assert resolved["public_building_subtype"] == "business_office"
    assert module.chapter6_code_context(resolved) == ("", "")


def test_public_building_missing_province_is_not_defaulted_to_shandong():
    module = _load_pg_collector()

    assert module.province_default_for_unit_type("公共建筑") == ""
    assert module.province_default_for_unit_type("公共机构") == "山东"


def test_public_building_missing_province_is_added_to_collection_gaps():
    module = _load_pg_collector()
    result = {
        "found": {
            "customer_info": {
                "field_type": "20",
                "province": "",
            },
        },
        "missing": [],
    }

    module._add_dictionary_collection_gaps(result)

    assert "所属省份（公共建筑类型路由必需）" in result["missing"]

