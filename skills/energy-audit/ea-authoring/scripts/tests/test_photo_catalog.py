import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[3]
PROJECT_DATA_PATH = REPO_ROOT / "tools" / "energy_audit" / "project_data.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROJECT_DATA = load_module("photo_catalog_project_data", PROJECT_DATA_PATH)
CATALOG_PATH = ROOT / "photo_catalog.py"
PHOTO_CATALOG = (
    load_module("photo_catalog", CATALOG_PATH) if CATALOG_PATH.is_file() else None
)
PHOTOS = load_module("photo_catalog_report_photos", ROOT / "prepare_report_photos.py")
WRITING_CONTEXT = load_module(
    "photo_catalog_writing_context",
    ROOT / "prepare_writing_context.py",
)


class ImageIdentityTests(unittest.TestCase):
    def test_dedupe_image_items_keeps_one_row_per_file_id_and_sets_sha256(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = Path(td) / "cold-source.png"
            image_path.write_bytes(b"one-physical-photo")
            expected_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            images = [
                PROJECT_DATA.ImageItem(
                    path=str(image_path),
                    category="制冷设备",
                    caption=f"第{index}次登记",
                    file_id=1001,
                )
                for index in range(13)
            ]

            result = PROJECT_DATA.dedupe_image_items(images)

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].caption, "第0次登记")
            self.assertEqual(result[0].sha256, expected_hash)

    def test_dedupe_image_items_keeps_distinct_file_ids_even_when_bytes_match(self):
        with tempfile.TemporaryDirectory() as td:
            first_path = Path(td) / "alias-a.png"
            second_path = Path(td) / "alias-b.png"
            content = b"same-bytes-different-attachment-id"
            first_path.write_bytes(content)
            second_path.write_bytes(content)
            images = [
                PROJECT_DATA.ImageItem(path=str(first_path), file_id=11),
                PROJECT_DATA.ImageItem(path=str(second_path), file_id=22),
            ]

            result = PROJECT_DATA.dedupe_image_items(images)

            self.assertEqual(len(result), 2)
            self.assertEqual(
                [image.file_id for image in result],
                [11, 22],
            )
            self.assertEqual(
                {image.sha256 for image in result},
                {hashlib.sha256(content).hexdigest()},
            )

    def test_image_identity_prefers_file_id_then_normalized_path(self):
        with tempfile.TemporaryDirectory() as td:
            image_path = Path(td) / "meter.png"
            image_path.write_bytes(b"meter")
            with_file_id = PROJECT_DATA.ImageItem(
                path=str(image_path),
                file_id=77,
            )
            without_file_id = PROJECT_DATA.ImageItem(path=str(image_path))

            self.assertEqual(
                PROJECT_DATA.image_identity(with_file_id),
                "file_id:77",
            )
            self.assertEqual(
                PROJECT_DATA.image_identity(without_file_id),
                f"path:{image_path.resolve()}",
            )


class PhotoCatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PHOTO_CATALOG, "缺少写作前照片事实目录模块")

    def test_catalog_aggregates_bindings_and_reuses_visual_by_content_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            building_path = root / "building.png"
            equipment_path = root / "chiller.png"
            award_path = root / "award.png"
            content = b"same-visible-photo-used-by-three-registered-rows"
            for path in (building_path, equipment_path, award_path):
                path.write_bytes(content)

            data = {
                "images": [
                    {
                        "path": str(building_path),
                        "file_id": 101,
                        "category": "建筑外观",
                        "building_name": "门诊楼",
                    },
                    {
                        "path": str(equipment_path),
                        "file_id": 202,
                        "category": "制冷设备",
                    },
                    {
                        "path": str(award_path),
                        "file_id": 303,
                        "category": "管理文件/荣誉",
                    },
                ],
                "buildings": [{"name": "门诊楼"}],
                "equipment": [
                    {
                        "name": "冷水机组",
                        "category": "冷热源",
                        "img_ids": ["202"],
                    },
                ],
                "energy_saving": [
                    {
                        "award_name": "节水型单位",
                        "award_certificate": "303",
                        "award_certificate_images": [str(award_path)],
                    },
                ],
            }
            calls = []

            def visualizer(image_path, context):
                calls.append((Path(image_path).name, context))
                return {
                    "scene_type": "设备与证书",
                    "visible_title": "节水型单位",
                    "object_labels": ["冷水机组"],
                    "brand": "测试品牌",
                    "model": "MODEL-1",
                    "confidence": 0.93,
                }

            catalog = PHOTO_CATALOG.build_photo_catalog(
                data,
                root,
                visualizer=visualizer,
            )

            candidates = catalog["candidates"]
            self.assertEqual(len(candidates), 3)
            by_file_id = {
                str(candidate["file_id"]): candidate for candidate in candidates
            }
            expected_hash = hashlib.sha256(content).hexdigest()
            self.assertTrue(
                all(candidate["source_sha256"] == expected_hash
                    for candidate in candidates)
            )
            self.assertIn(
                "门诊楼",
                {
                    binding["label"]
                    for binding in by_file_id["101"]["bindings"]
                },
            )
            self.assertIn(
                "冷水机组",
                {
                    binding["label"]
                    for binding in by_file_id["202"]["bindings"]
                },
            )
            self.assertIn(
                "节水型单位",
                {
                    binding["label"]
                    for binding in by_file_id["303"]["bindings"]
                },
            )
            self.assertIn("门诊楼", by_file_id["101"]["suggested_caption"])
            self.assertIn("冷水机组", by_file_id["202"]["suggested_caption"])
            self.assertIn("节水型单位", by_file_id["303"]["suggested_caption"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                by_file_id["101"]["visual"]["status"],
                "pass",
            )
            self.assertEqual(
                set(by_file_id["101"]["content_aliases"]),
                {"202", "303"},
            )

            output = PHOTO_CATALOG.write_photo_catalog(root, catalog)
            saved = json.loads(Path(output).read_text(encoding="utf-8"))
            self.assertEqual(len(saved["candidates"]), 3)

    def test_catalog_reuses_visual_facts_from_hash_cache_across_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "chiller.png"
            image.write_bytes(b"cached-visual-photo")
            data = {
                "base": {"unit_name": "测试单位", "unit_short": "测试单位"},
                "images": [{
                    "path": str(image),
                    "file_id": 202,
                    "category": "制冷设备",
                }],
                "equipment": [{
                    "name": "冷水机组",
                    "img_ids": ["202"],
                }],
            }
            calls = []

            def first_visualizer(image_path, context):
                calls.append((image_path, context))
                return {
                    "scene_type": "设备",
                    "visible_title": "冷水机组",
                    "object_labels": ["冷水机组"],
                    "brand": "",
                    "model": "",
                    "confidence": 0.95,
                }

            first = PHOTO_CATALOG.build_photo_catalog(
                data, root, visualizer=first_visualizer
            )

            def should_not_run(*_args, **_kwargs):
                raise AssertionError("缓存命中后不应再次调用视觉接口")

            second = PHOTO_CATALOG.build_photo_catalog(
                data, root, visualizer=should_not_run
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(first["candidates"][0]["visual"]["status"], "pass")
            self.assertEqual(second["candidates"][0]["visual"]["status"], "pass")
            cache = json.loads(
                (root / "photo_visual_cache.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(cache["observations"]), 1)

    def test_catalog_accepts_inspect_photo_result_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "meter.png"
            image.write_bytes(b"meter-photo")
            data = {
                "base": {"unit_name": "测试单位"},
                "images": [{
                    "path": str(image),
                    "file_id": 404,
                    "category": "计量器具",
                }],
                "energy_meter": [{
                    "data_type": 1,
                    "device_img": "404",
                }],
            }

            catalog = PHOTO_CATALOG.build_photo_catalog(
                data,
                root,
                visualizer=lambda *_args: {
                    "status": "pass",
                    "reason": "",
                    "observed": {
                        "scene_type": "仪表",
                        "visible_title": "电能表",
                        "object_labels": ["电能表"],
                        "brand": "测试品牌",
                        "model": "DTSD-1",
                        "confidence": 0.97,
                    },
                    "model": "deepseek-flash",
                },
            )

            visual = catalog["candidates"][0]["visual"]
            self.assertEqual(visual["status"], "pass")
            self.assertEqual(visual["observed"]["visible_title"], "电能表")
            self.assertEqual(visual["model"], "deepseek-flash")


class PhotoCatalogContextTests(unittest.TestCase):
    def make_project(self, root: Path) -> Path:
        image = root / "chiller.png"
        image.write_bytes(b"visual-photo")
        data = {
            "base": {
                "unit_name": "测试人民医院",
                "unit_short": "人民医院",
                "institution_category": "医院",
            },
            "images": [{
                "path": str(image),
                "file_id": 202,
                "category": "制冷设备",
            }],
            "equipment": [{
                "name": "冷水机组",
                "category": "冷热源",
                "img_ids": ["202"],
            }],
            "energy_saving": [{
                "award_name": "节水型单位",
                "award_certificate": "303",
                "award_certificate_images": [],
            }],
        }
        (root / "data.json").write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        catalog = {
            "version": 1,
            "candidates": [
                {
                    "candidate_id": "file_id:202",
                    "file_id": "202",
                    "source_path": str(image),
                    "source_sha256": "a" * 64,
                    "categories": ["制冷设备"],
                    "bindings": [{
                        "ref": "equipment[].img_ids",
                        "label": "冷水机组",
                        "chapter": "第6章",
                        "kind": "equipment",
                    }],
                    "visual": {
                        "status": "pass",
                        "observed": {
                            "visible_title": "YZ-1冷水机组",
                            "object_labels": ["冷水机组"],
                            "brand": "测试品牌",
                            "model": "YZ-1",
                            "confidence": 0.94,
                        },
                    },
                    "suggested_caption": "图6.N 冷水机组",
                },
                {
                    "candidate_id": "file_id:303",
                    "file_id": "303",
                    "source_path": "",
                    "source_sha256": "",
                    "categories": ["管理文件/荣誉"],
                    "bindings": [{
                        "ref": "energy_saving[].award_certificate",
                        "label": "节水型单位",
                        "chapter": "第3章",
                        "kind": "award",
                    }],
                    "visual": {
                        "status": "unverified",
                        "observed": {},
                    },
                    "suggested_caption": "图3.N 节水型单位",
                },
            ],
            "warnings": [],
        }
        (root / "photo_catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False),
            encoding="utf-8",
        )
        return image

    def test_writing_context_includes_photo_facts_and_neutral_caption_rule(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)

            rc = WRITING_CONTEXT.main([str(root), "--quiet"])

            self.assertEqual(rc, 0)
            context = (root / "chapter_md" / "_context.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("照片事实目录（写具体图注前必读）", context)
            self.assertIn("file_id:202", context)
            self.assertIn("冷水机组", context)
            self.assertIn("YZ-1冷水机组", context)
            self.assertIn("图6.N 冷水机组", context)
            self.assertIn("中性、由数据库绑定支撑的图注", context)

    def test_catalog_only_builds_catalog_before_chapter_markdown_exists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image = root / "chiller.png"
            image.write_bytes(b"catalog-only-photo")
            (root / "data.json").write_text(
                json.dumps({
                    "base": {"unit_name": "测试单位"},
                    "images": [{
                        "path": str(image),
                        "file_id": 202,
                        "category": "制冷设备",
                    }],
                    "equipment": [{
                        "name": "冷水机组",
                        "img_ids": ["202"],
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([
                str(root),
                "--catalog-only",
                "--quiet",
            ])

            self.assertEqual(rc, 0)
            catalog = json.loads(
                (root / "photo_catalog.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(catalog["candidates"]), 1)
            self.assertEqual(catalog["candidates"][0]["file_id"], "202")


class PhotoCatalogIntegrationTests(unittest.TestCase):
    def test_catalog_to_context_to_final_manifest_to_prune_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chapter_dir = root / "chapter_md"
            chapter_dir.mkdir()
            (chapter_dir / "ch2.md").write_text(
                "# 第2章\n\n图2.1 测试单位单位整体外观\n",
                encoding="utf-8",
            )
            (chapter_dir / "ch6.md").write_text(
                "# 第6章\n\n图6.1 冷水机组\n",
                encoding="utf-8",
            )
            overall = root / "overall.png"
            chiller = root / "chiller.png"
            overall.write_bytes(b"overall-photo")
            chiller.write_bytes(b"chiller-photo")
            images_dir = root / "data" / "images"
            images_dir.mkdir(parents=True)
            (images_dir / "orphan.png").write_bytes(b"orphan-photo")
            data = {
                "base": {
                    "unit_name": "测试单位",
                    "unit_short": "测试单位",
                },
                "images": [
                    {
                        "path": str(overall),
                        "file_id": 101,
                        "category": "单位整体外观",
                    },
                    {
                        "path": str(chiller),
                        "file_id": 202,
                        "category": "制冷设备",
                    },
                ],
                "equipment": [{
                    "name": "冷水机组",
                    "category": "冷热源",
                    "img_ids": ["202"],
                }],
            }
            (root / "data.json").write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "report_images.json").write_text(
                json.dumps({"images": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertEqual(PHOTOS.main([
                str(root), "--catalog-only", "--quiet"
            ]), 0)
            self.assertEqual(WRITING_CONTEXT.main([
                str(root), "--quiet"
            ]), 0)
            self.assertEqual(PHOTOS.main([str(root), "--quiet"]), 0)
            self.assertEqual(PHOTOS.main([
                str(root), "--prune", "report", "--quiet"
            ]), 0)

            context = (chapter_dir / "_context.md").read_text(encoding="utf-8")
            self.assertIn("照片事实目录（写具体图注前必读）", context)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )["images"]
            managed = [
                item for item in manifest
                if item["caption"].startswith(("图2.", "图6."))
            ]
            self.assertEqual(len(managed), 2)
            self.assertTrue(all(item.get("source") for item in managed))
            prune = json.loads(
                (root / "photo_prune_report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(prune["orphans"], ["data/images/orphan.png"])
            self.assertTrue((images_dir / "orphan.png").is_file())


if __name__ == "__main__":
    unittest.main()
