import base64
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PHOTOS = load_module("prepare_report_photos", ROOT / "prepare_report_photos.py")
ASSERTS = load_module(
    "ea_docx_asserts",
    ROOT.parents[1] / "energy-audit-report" / "scripts" / "ea_docx_asserts.py",
)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


class PhotoProject:
    def __init__(self, root: Path, ch4: str = "# 第4章\n\n图4.1 计量器具照片\n"):
        self.root = root
        (root / "chapter_md").mkdir(parents=True)
        (root / "chapter_md" / "ch2.md").write_text("# 第2章\n", encoding="utf-8")
        (root / "chapter_md" / "ch4.md").write_text(ch4, encoding="utf-8")
        self.water = root / "water_meter.png"
        self.electric = root / "electric_meter.png"
        self.water.write_bytes(PNG)
        self.electric.write_bytes(PNG + b"\n")
        data = {
            "base": {"unit_short": "测试单位"},
            "images": [
                {"path": str(self.water), "category": "计量器具",
                 "file_id": 1001, "building_name": ""},
                {"path": str(self.electric), "category": "计量器具",
                 "file_id": 1002, "building_name": ""},
                {"path": str(self.electric), "category": "计量器具",
                 "file_id": 1002, "building_name": ""},
            ],
            "energy_meter": [
                {"data_type": 2, "device_img": "1001"},
                {"data_type": 1, "device_img": "1002"},
            ],
        }
        (root / "data.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        (root / "report_images.json").write_text(
            json.dumps({
                "images": [
                    {"caption": "图4.1 计量器具照片", "src": "images/water_meter.png"},
                    {"caption": "图4.1 计量器具照片", "src": "images/electric_meter.png"},
                    {"caption": "图5.1 能源资源流向图",
                     "src": "charts/energy-flow.png"},
                ]
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    def manifest(self):
        return json.loads(
            (self.root / "report_images.json").read_text(encoding="utf-8")
        )["images"]


class PrepareReportPhotosCh4Tests(unittest.TestCase):
    def test_general_caption_dedupes_and_rebuilds_ch4_paths(self):
        with tempfile.TemporaryDirectory() as td:
            project = PhotoProject(Path(td))
            rc = PHOTOS.main([str(project.root), "--quiet"])
            self.assertEqual(rc, 0)

            entries = project.manifest()
            ch4 = [e for e in entries if e["caption"].startswith("图4.")]
            self.assertEqual(len(ch4), 2)
            self.assertEqual({e["caption"] for e in ch4}, {"图4.1 计量器具照片"})
            self.assertEqual(
                {e["src"] for e in ch4},
                {
                    "data/images/计量器具_水表.png",
                    "data/images/计量器具_电表.png",
                },
            )
            self.assertTrue(all((project.root / e["src"]).is_file() for e in ch4))
            self.assertFalse(any(e["src"].startswith("images/") for e in entries))
            self.assertIn(
                "charts/energy-flow.png",
                {e["src"] for e in entries},
            )

    def test_specific_captions_select_by_meter_type(self):
        with tempfile.TemporaryDirectory() as td:
            project = PhotoProject(
                Path(td), "# 第4章\n\n图4.1 电表\n\n图4.2 水表\n"
            )
            rc = PHOTOS.main([str(project.root), "--quiet"])
            self.assertEqual(rc, 0)
            selected = {
                e["caption"]: e["src"] for e in project.manifest()
                if e["caption"].startswith("图4.")
            }
            self.assertEqual(selected["图4.1 电表"], "data/images/计量器具_电表.png")
            self.assertEqual(selected["图4.2 水表"], "data/images/计量器具_水表.png")

    def test_photos_without_caption_return_warning_code(self):
        with tempfile.TemporaryDirectory() as td:
            project = PhotoProject(Path(td), "# 第4章\n")
            self.assertEqual(PHOTOS.main([str(project.root), "--quiet"]), 2)
            self.assertFalse(any(
                e["caption"].startswith("图4.") for e in project.manifest()
            ))

    def test_caption_without_photos_return_warning_code(self):
        with tempfile.TemporaryDirectory() as td:
            project = PhotoProject(Path(td))
            data_path = project.root / "data.json"
            data = json.loads(data_path.read_text(encoding="utf-8"))
            data["images"] = []
            data["energy_meter"] = []
            data_path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(PHOTOS.main([str(project.root), "--quiet"]), 2)
            self.assertFalse(any(
                e["caption"].startswith("图4.") for e in project.manifest()
            ))


class Ch4PhotoAssertTests(unittest.TestCase):
    @staticmethod
    def para(text="", image=False):
        drawing = '<w:r><w:drawing/></w:r>' if image else ""
        return f'<w:p><w:r><w:t>{text}</w:t></w:r>{drawing}</w:p>'

    def run_assert(self, blocks):
        with mock.patch.object(ASSERTS, "_chapter_region", return_value=blocks):
            return ASSERTS.ch4_photos_ok("<w:body/>")

    def test_one_caption_with_two_images_is_valid(self):
        ok, why = self.run_assert([
            self.para(image=True),
            self.para(image=True),
            self.para("图4.1 计量器具照片"),
        ])
        self.assertTrue(ok, why)

    def test_caption_without_image_fails(self):
        ok, why = self.run_assert([self.para("图4.1 计量器具照片")])
        self.assertFalse(ok)
        self.assertIn("没有图片", why)

    def test_non_continuous_caption_numbers_fail(self):
        ok, why = self.run_assert([
            self.para(image=True),
            self.para("图4.1 电表"),
            self.para(image=True),
            self.para("图4.3 水表"),
        ])
        self.assertFalse(ok)
        self.assertIn("不连续", why)


if __name__ == "__main__":
    unittest.main()
