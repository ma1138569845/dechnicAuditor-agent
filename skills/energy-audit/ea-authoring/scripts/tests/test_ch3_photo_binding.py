import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PHOTOS = load_module("prepare_report_photos_ch3", ROOT / "prepare_report_photos.py")


class Chapter3PhotoPoolTests(unittest.TestCase):
    def test_pool_preserves_award_title_year_and_file_id(self):
        build = getattr(PHOTOS, "build_ch3_pools", None)
        self.assertTrue(callable(build), "缺少第3章结构化照片池")
        pools = build(
            saving=[
                {
                    "statistical_year": 2024,
                    "award_name": "节水型单位",
                    "award_certificate": "2002",
                    "award_certificate_images": ["b.png"],
                }
            ],
            images=[
                {"path": "b.png", "file_id": 2002, "category": "管理文件/荣誉"}
            ],
        )
        self.assertEqual(
            pools["award"],
            [{
                "kind": "award",
                "path": "b.png",
                "file_id": "2002",
                "title": "节水型单位",
                "year": 2024,
            }],
        )

    def test_exact_award_title_selects_correct_certificate(self):
        select = getattr(PHOTOS, "select_ch3_candidate", None)
        self.assertTrue(callable(select), "缺少第3章唯一匹配逻辑")
        pools = {
            "management": [],
            "award": [
                {
                    "kind": "award",
                    "path": "a.png",
                    "file_id": "1001",
                    "title": "节能先进单位",
                    "year": 2023,
                },
                {
                    "kind": "award",
                    "path": "b.png",
                    "file_id": "1002",
                    "title": "节水型单位",
                    "year": 2024,
                },
            ],
        }
        selected = select("节水型单位奖牌（2024年）", pools, set())
        self.assertEqual(selected["path"], "b.png")

    def test_multiple_candidates_with_generic_caption_do_not_guess(self):
        select = getattr(PHOTOS, "select_ch3_candidate", None)
        self.assertTrue(callable(select), "缺少第3章唯一匹配逻辑")
        pools = {
            "management": [],
            "award": [
                {
                    "kind": "award",
                    "path": "a.png",
                    "file_id": "1001",
                    "title": "节能先进单位",
                    "year": 2023,
                },
                {
                    "kind": "award",
                    "path": "b.png",
                    "file_id": "1002",
                    "title": "节水型单位",
                    "year": 2024,
                },
            ],
        }
        self.assertIsNone(select("荣誉证书照片", pools, set()))

    def test_single_candidate_can_use_generic_caption(self):
        select = getattr(PHOTOS, "select_ch3_candidate", None)
        self.assertTrue(callable(select), "缺少第3章唯一匹配逻辑")
        pools = {
            "management": [],
            "award": [{
                "kind": "award",
                "path": "only.png",
                "file_id": "1001",
                "title": "节水型单位",
                "year": 2024,
            }],
        }
        selected = select("荣誉证书照片", pools, set())
        self.assertEqual(selected["path"], "only.png")

    def test_same_title_in_multiple_years_requires_year_in_caption(self):
        select = getattr(PHOTOS, "select_ch3_candidate", None)
        self.assertTrue(callable(select), "缺少第3章唯一匹配逻辑")
        pools = {
            "management": [],
            "award": [
                {
                    "kind": "award",
                    "path": "2023.png",
                    "file_id": "1001",
                    "title": "节水型单位",
                    "year": 2023,
                },
                {
                    "kind": "award",
                    "path": "2024.png",
                    "file_id": "1002",
                    "title": "节水型单位",
                    "year": 2024,
                },
            ],
        }
        self.assertIsNone(select("节水型单位奖牌", pools, set()))
        selected = select("节水型单位奖牌（2024年）", pools, set())
        self.assertEqual(selected["path"], "2024.png")


if __name__ == "__main__":
    unittest.main()
