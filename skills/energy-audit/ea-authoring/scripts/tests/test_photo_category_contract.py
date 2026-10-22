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


class PrepareReportPhotosContractTests(unittest.TestCase):
    def test_ch6_pool_contains_all_classified_device_photos(self):
        canonical = set(PROJECT_DATA.PHOTO_CATEGORIES)
        self.assertLessEqual(PHOTOS.CH6_DEVICE_CATS, canonical)
        for category in ("变压器/配电", "水泵/水箱", "厨房设备"):
            self.assertIn(category, PHOTOS.CH6_DEVICE_CATS)

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
