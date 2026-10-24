import base64
import hashlib
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
WRITING_CONTEXT = load_module(
    "prepare_writing_context_photo_contract",
    ROOT / "prepare_writing_context.py",
)
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
            for entry in ch4:
                source = entry.get("source") or {}
                self.assertEqual(len(entry.get("sha256", "")), 64)
                self.assertEqual(
                    entry["sha256"],
                    hashlib.sha256(
                        (project.root / entry["src"]).read_bytes()
                    ).hexdigest(),
                )
                self.assertTrue(source.get("source_path"))
                self.assertEqual(len(source.get("source_sha256", "")), 64)
                self.assertEqual(
                    source.get("binding", {}).get("ref"),
                    "energy_meter[].device_img",
                )
                self.assertEqual(source.get("category"), "计量器具")
                self.assertEqual(source.get("selection_method"), "file_id")
                self.assertEqual(source.get("verification"), "unverified")
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

    def test_equipment_without_image_fields_does_not_block_photo_finalization(self):
        with tempfile.TemporaryDirectory() as td:
            project = PhotoProject(Path(td))
            data_path = project.root / "data.json"
            data = json.loads(data_path.read_text(encoding="utf-8"))
            data["equipment"] = [{
                "name": "蹲便器",
                "category": "卫生器具",
            }]
            data_path.write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([str(project.root), "--quiet"])

            self.assertEqual(rc, 0)
            status = json.loads(
                (project.root / "photo_finalization_status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(status["clean"])
            self.assertEqual(status["warnings"], [])


class PrepareReportPhotosCh3VisionTests(unittest.TestCase):
    def make_project(self, root: Path):
        (root / "chapter_md").mkdir(parents=True)
        (root / "chapter_md" / "ch2.md").write_text("# 第2章\n", encoding="utf-8")
        (root / "chapter_md" / "ch3.md").write_text(
            "# 第3章\n\n图3.1 节水型单位奖牌\n", encoding="utf-8"
        )
        certificate = root / "节水型单位.png"
        certificate.write_bytes(PNG)
        data = {
            "base": {
                "unit_name": "测试单位",
                "unit_short": "测试单位",
            },
            "images": [{
                "path": str(certificate),
                "file_id": 2002,
                "category": "管理文件/荣誉",
            }],
            "energy_saving": [{
                "statistical_year": 2024,
                "award_name": "节水型单位",
                "award_certificate": "2002",
                "award_certificate_images": [str(certificate)],
            }],
        }
        (root / "data.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        (root / "report_images.json").write_text(
            json.dumps({"images": []}, ensure_ascii=False), encoding="utf-8"
        )
        return certificate

    def test_visual_mismatch_excludes_wrong_certificate_in_strict_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)
            with mock.patch.object(
                PHOTOS,
                "verify_certificate",
                create=True,
                return_value={
                    "status": "mismatch",
                    "reason": "证书标题不一致",
                    "model": "deepseek-flash",
                },
            ):
                rc = PHOTOS.main([
                    str(root), "--quiet", "--certificate-policy", "strict"
                ])
            self.assertEqual(rc, 2)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )
            self.assertFalse(any(
                item["caption"].startswith("图3.")
                for item in manifest.get("images", [])
            ))

    def test_visual_mismatch_is_retained_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)
            with mock.patch.object(
                PHOTOS,
                "verify_certificate",
                return_value={
                    "status": "mismatch",
                    "reason": "证书标题不一致",
                    "model": "deepseek-flash",
                },
            ):
                rc = PHOTOS.main([str(root), "--quiet"])
            self.assertEqual(rc, 2)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any(
                item["caption"].startswith("图3.")
                for item in manifest.get("images", [])
            ))

    def test_visual_unverified_keeps_deterministic_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)
            with mock.patch.object(
                PHOTOS,
                "verify_certificate",
                create=True,
                return_value={
                    "status": "unverified",
                    "reason": "未配置 DEEPSEEK_API_KEY",
                    "model": "deepseek-flash",
                },
            ):
                rc = PHOTOS.main([str(root), "--quiet"])
            self.assertEqual(rc, 2)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any(
                item["caption"].startswith("图3.")
                for item in manifest.get("images", [])
            ))

    def test_visual_pass_is_cached_and_reused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)
            verdict = {
                "status": "pass",
                "reason": "证书标题和受奖单位与数据一致",
                "model": "deepseek-flash",
            }
            with mock.patch.object(
                PHOTOS,
                "verify_certificate",
                return_value=verdict,
            ) as verify:
                self.assertEqual(PHOTOS.main([str(root), "--quiet"]), 0)
                self.assertEqual(PHOTOS.main([str(root), "--quiet"]), 0)
            self.assertEqual(verify.call_count, 1)
            checks = json.loads(
                (root / "photo_vision_checks.json").read_text(encoding="utf-8")
            )["checks"]
            self.assertEqual(len(checks), 1)
            self.assertEqual(next(iter(checks.values()))["status"], "pass")

    def test_visual_review_keeps_candidate_but_returns_warning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_project(root)
            with mock.patch.object(
                PHOTOS,
                "verify_certificate",
                return_value={
                    "status": "review",
                    "reason": "视觉识别置信度不足（0.6）",
                    "model": "deepseek-flash",
                },
            ):
                self.assertEqual(PHOTOS.main([str(root), "--quiet"]), 2)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )
            self.assertTrue(any(
                item["caption"].startswith("图3.")
                for item in manifest.get("images", [])
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


class PhotoSemanticReuseTests(unittest.TestCase):
    def test_guard_reports_same_source_under_different_captions(self):
        entries = [
            {
                "caption": "图6.1 冷水机组",
                "src": "data/images/a.png",
                "source": {"source_sha256": "a" * 64},
            },
            {
                "caption": "图6.2 冷冻水泵",
                "src": "data/images/b.png",
                "source": {"source_sha256": "a" * 64},
            },
        ]

        warnings = PHOTOS.semantic_reuse_warnings(entries)

        self.assertEqual(len(warnings), 1)
        self.assertIn("图6.1 冷水机组", warnings[0])
        self.assertIn("图6.2 冷冻水泵", warnings[0])

    def test_chapter6_does_not_reuse_one_photo_for_a_second_equipment_caption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "chapter_md").mkdir(parents=True)
            (root / "chapter_md" / "ch2.md").write_text("# 第2章\n", encoding="utf-8")
            (root / "chapter_md" / "ch6.md").write_text(
                "# 第6章\n\n图6.1 冷水机组\n\n图6.2 冷冻水泵\n",
                encoding="utf-8",
            )
            photo = root / "设备_冷水机组.png"
            photo.write_bytes(PNG)
            data = {
                "base": {
                    "unit_short": "测试单位",
                    "unit_func": "C",
                    "children_func": "B",
                    "institution_category": "医疗",
                },
                "images": [{
                    "path": str(photo),
                    "category": "制冷设备",
                    "file_id": 5001,
                }],
                "equipment": [
                    {"name": "冷水机组", "img_ids": ["5001"]},
                    {"name": "冷冻水泵", "img_ids": ["5001"]},
                ],
            }
            (root / "data.json").write_text(
                json.dumps(data, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "report_images.json").write_text(
                json.dumps({"images": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([str(root), "--quiet"])

            self.assertEqual(rc, 2)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )["images"]
            ch6 = [item for item in manifest if item["caption"].startswith("图6.")]
            self.assertEqual(
                [item["caption"] for item in ch6],
                ["图6.1 冷水机组"],
            )


class Chapter6FieldCaptionTests(unittest.TestCase):
    def test_one_image_field_requires_one_caption_per_attachment(self):
        equipment = [{
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "img_fields": [{
                "field": "system_img",
                "label": "系统图片",
                "ids": [801, 802],
            }],
            "img_ids": [801, 802],
        }]
        images = [{"file_id": 801}, {"file_id": 802}]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [("图6.1", "img", "数据中心/信息中心")],
            images,
        )

        self.assertEqual(gaps, ["数据中心/信息中心"])
        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [
                ("图6.1", "img", "数据中心/信息中心"),
                ("图6.2", "img", "数据中心/信息中心"),
            ],
            images,
        )
        self.assertEqual(gaps, [])

    def test_equipment_photo_contract_has_one_row_per_attachment(self):
        data = {
            "base": {"unit_short": "测试单位"},
            "images": [
                {"file_id": 801, "path": r"C:\images\801.png"},
                {"file_id": 802, "path": r"C:\images\802.png"},
            ],
            "equipment": [{
                "name": "冷冻水泵",
                "category": "输配设备",
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备整体图片",
                    "ids": [801, 802],
                }],
                "img_ids": [801, 802],
            }],
        }

        rows = WRITING_CONTEXT.equipment_photo_contract(data)

        self.assertEqual(len(rows), 2)
        self.assertEqual([row[5] for row in rows], ["801", "802"])

    def test_same_caption_consumes_attachments_in_attachment_order(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first_path = root / "first.png"
            second_path = root / "second.png"
            first_path.write_bytes(PNG)
            second_path.write_bytes(PNG + b"second")
            images = [
                {
                    "file_id": 801,
                    "path": str(first_path),
                    "category": "制冷设备",
                },
                {
                    "file_id": 802,
                    "path": str(second_path),
                    "category": "制冷设备",
                },
            ]
            equipment = [{
                "name": "冷冻水泵",
                "category": "输配设备",
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备整体图片",
                    "ids": [801, 802],
                }],
                "img_ids": [801, 802],
            }]
            used = set()

            first = PHOTOS.pick_ch6_photo_details(
                "冷冻水泵", images, used, equipment
            )
            used.add(first["src"])
            second = PHOTOS.pick_ch6_photo_details(
                "冷冻水泵", images, used, equipment
            )

        self.assertEqual(first["file_id"], "801")
        self.assertEqual(second["file_id"], "802")
        self.assertEqual(
            second["binding_ref"],
            "equipment[].img_fields[device_img]",
        )

    def test_power_device_with_photo_is_checked_even_when_table_row_is_missing(self):
        equipment = [{
            "name": "生活水泵",
            "category": "动力",
            "img_ids": [901],
        }]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [],
            [{"file_id": 901}],
            table_names=["冷水机组"],
        )

        self.assertEqual(gaps, ["生活水泵"])

    def test_special_device_with_photo_is_checked_even_when_table_row_is_missing(self):
        equipment = [{
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "img_ids": [902],
        }]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [],
            [{"file_id": 902}],
            table_names=["冷水机组"],
        )

        self.assertEqual(gaps, ["数据中心/信息中心"])

    def test_ordinary_device_not_in_table_keeps_legacy_skip(self):
        equipment = [{
            "name": "备用电脑",
            "category": "办公",
            "img_ids": [903],
        }]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [],
            [{"file_id": 903}],
            table_names=["冷水机组"],
        )

        self.assertEqual(gaps, [])

    def test_registered_attachment_without_local_file_is_reported_separately(self):
        equipment = [{
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "img_ids": [904],
        }]

        coverage = PHOTOS.equipment_caption_coverage(
            equipment,
            [(1, "图6.1 数据中心/信息中心", "数据中心/信息中心")],
            [],
        )

        self.assertEqual(coverage["missing_captions"], [])
        self.assertEqual(
            coverage["missing_local_files"],
            ["数据中心/信息中心"],
        )

    def test_registered_attachment_without_local_file_still_requires_caption(self):
        equipment = [{
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "img_ids": [905],
        }]

        coverage = PHOTOS.equipment_caption_coverage(
            equipment,
            [],
            [],
            table_names=["冷水机组"],
        )

        self.assertEqual(
            coverage["missing_captions"],
            ["数据中心/信息中心"],
        )
        self.assertEqual(
            coverage["missing_local_files"],
            ["数据中心/信息中心"],
        )

    def test_water_aux_photo_is_bound_to_6_2_by_attachment_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chapter_dir = root / "chapter_md"
            chapter_dir.mkdir()
            (chapter_dir / "ch2.md").write_text(
                "# 第2章\n\n图2.1 测试单位单位整体外观\n",
                encoding="utf-8",
            )
            (chapter_dir / "ch6.md").write_text(
                "# 第6章\n\n"
                "## 6.2 用水系统运行分析\n\n"
                "图6.1 绿化灌溉设施\n",
                encoding="utf-8",
            )
            overall = root / "overall.png"
            greening = root / "unrelated-upload-name.png"
            overall.write_bytes(PNG + b"overall")
            greening.write_bytes(PNG + b"greening")
            data = {
                "base": {
                    "unit_name": "测试单位",
                    "unit_short": "测试单位",
                },
                "images": [
                    {
                        "path": str(overall),
                        "category": "单位整体外观",
                        "file_id": 700,
                    },
                    {
                        "path": str(greening),
                        "category": "用水设施",
                        "file_id": 701,
                    },
                ],
                "water_aux": {
                    "greening": [{
                        "irrigation_type": "自动喷灌",
                        "img_ids": [701],
                        "img_fields": [{
                            "field": "device_img",
                            "label": "设备图片",
                            "ids": [701],
                        }],
                    }],
                },
            }
            (root / "data.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            (root / "report_images.json").write_text(
                json.dumps({"images": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([str(root), "--quiet"])

            self.assertEqual(rc, 0)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )["images"]
            water_photo = next(
                item for item in manifest
                if item["caption"] == "图6.1 绿化灌溉设施"
            )
            binding = water_photo["source"]["binding"]
            self.assertEqual(
                binding["ref"],
                "water_aux.greening[].img_fields[device_img]",
            )
            self.assertEqual(binding["photo_section_key"], "water_system")

    def test_multiple_upload_fields_keep_device_and_field_names(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "chapter_md").mkdir(parents=True)
            (root / "chapter_md" / "ch2.md").write_text(
                "# 第2章\n", encoding="utf-8"
            )
            (root / "chapter_md" / "ch6.md").write_text(
                "# 第6章\n\n"
                "图6.1 冷冻水泵设备整体图片\n\n"
                "图6.2 冷冻水泵电机铭牌图片\n\n"
                "图6.3 某冷热源\n",
                encoding="utf-8",
            )
            images = []
            for fid, suffix in ((5001, "overall"), (5002, "motor"), (5003, "source")):
                image = root / f"{suffix}.png"
                image.write_bytes(PNG + suffix.encode("ascii"))
                images.append({
                    "path": str(image),
                    "category": "制冷设备",
                    "file_id": fid,
                })
            data = {
                "base": {"unit_short": "测试单位"},
                "images": images,
                "equipment": [
                    {
                        "name": "冷冻水泵",
                        "category": "输配设备",
                        "img_fields": [
                            {
                                "field": "device_img",
                                "label": "设备整体图片",
                                "ids": [5001],
                            },
                            {
                                "field": "motor_img",
                                "label": "电机铭牌图片",
                                "ids": [5002],
                            },
                        ],
                        "img_ids": [5001, 5002],
                    },
                    {
                        "name": "某冷热源",
                        "category": "其他设备",
                        "img_fields": [{
                            "field": "system_img",
                            "label": "系统图片",
                            "ids": [5003],
                        }],
                        "img_ids": [5003],
                    },
                ],
            }
            (root / "data.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            (root / "report_images.json").write_text(
                json.dumps({"images": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([str(root), "--quiet"])

            self.assertEqual(rc, 0)
            manifest = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )["images"]
            ch6 = {
                item["caption"]: item
                for item in manifest
                if item["caption"].startswith("图6.")
            }
            self.assertEqual(
                set(ch6),
                {
                    "图6.1 冷冻水泵设备整体图片",
                    "图6.2 冷冻水泵电机铭牌图片",
                    "图6.3 某冷热源",
                },
            )
            self.assertEqual(
                ch6["图6.1 冷冻水泵设备整体图片"]["source"]["binding"]["ref"],
                "equipment[].img_fields[device_img]",
            )
            self.assertEqual(
                ch6["图6.2 冷冻水泵电机铭牌图片"]["source"]["binding"]["ref"],
                "equipment[].img_fields[motor_img]",
            )
            self.assertEqual(
                ch6["图6.3 某冷热源"]["source"]["binding"]["ref"],
                "equipment[].img_fields[system_img]",
            )
            self.assertEqual(
                ch6["图6.1 冷冻水泵设备整体图片"]["source"]["binding"][
                    "photo_section_key"
                ],
                "air_heating",
            )
            self.assertEqual(
                ch6["图6.1 冷冻水泵设备整体图片"]["source"]["binding"][
                    "photo_section_title"
                ],
                "空调与供暖系统",
            )
            self.assertEqual(
                {
                    Path(item["src"]).stem
                    for item in ch6.values()
                },
                {
                    "设备_冷冻水泵设备整体图片",
                    "设备_冷冻水泵电机铭牌图片",
                    "设备_某冷热源",
                },
            )

    def test_multi_field_coverage_requires_each_exact_field_caption(self):
        equipment = [{
            "name": "冷冻水泵",
            "category": "输配设备",
            "img_fields": [
                {
                    "field": "device_img",
                    "label": "设备整体图片",
                    "ids": [5001],
                },
                {
                    "field": "motor_img",
                    "label": "电机铭牌图片",
                    "ids": [5002],
                },
            ],
            "img_ids": [5001, 5002],
        }]
        images = [{"file_id": 5001}, {"file_id": 5002}]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [("图6.1", "img", "冷冻水泵")],
            images,
        )

        self.assertEqual(
            gaps,
            ["冷冻水泵设备整体图片", "冷冻水泵电机铭牌图片"],
        )
        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [("图6.1", "img", "冷冻水泵设备整体图片")],
            images,
        )
        self.assertEqual(gaps, ["冷冻水泵电机铭牌图片"])

    def test_water_aux_coverage_is_not_hidden_by_device_table_filter(self):
        equipment = PHOTOS.chapter6_water_aux_photo_items({
            "greening": [{
                "img_ids": [701],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": [701],
                }],
            }],
        })

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [],
            [{"file_id": 701}],
            table_names=["冷水机组"],
        )

        self.assertEqual(gaps, ["绿化灌溉设施"])

    def test_duplicate_equipment_names_require_one_caption_per_attachment(self):
        equipment = [
            {
                "name": "供水泵",
                "img_ids": [701],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": [701],
                }],
            },
            {
                "name": "供水泵",
                "img_ids": [702],
                "img_fields": [{
                    "field": "device_img",
                    "label": "设备图片",
                    "ids": [702],
                }],
            },
        ]

        gaps = PHOTOS.equipment_caption_gaps(
            equipment,
            [(1, "图6.1 供水泵", "供水泵")],
            [{"file_id": 701}, {"file_id": 702}],
        )

        self.assertEqual(gaps, ["供水泵"])

    def test_chapter6_caption_locations_track_the_enclosing_system_section(self):
        with tempfile.TemporaryDirectory() as td:
            md = Path(td) / "ch6.md"
            md.write_text(
                "# 第6章\n\n"
                "### （1）空调与供暖系统\n\n"
                "图6.1 冷水机组\n\n"
                "### （5）信息机房系统\n\n"
                "图6.2 数据中心/信息中心\n\n"
                "## 6.2 用水系统运行分析\n\n"
                "图6.3 绿化灌溉设施\n",
                encoding="utf-8",
            )

            sections = PHOTOS.parse_caption_sections(str(md), "6")

            self.assertEqual(
                sections,
                [
                    (1, "冷水机组", "air_heating"),
                    (2, "数据中心/信息中心", "information_room"),
                    (3, "绿化灌溉设施", "water_system"),
                ],
            )

    def test_chapter6_reports_photo_placed_in_the_wrong_system_section(self):
        equipment = [{
            "name": "数据中心/信息中心",
            "category": "特殊设备",
            "total_power_kw": 17.8,
            "img_fields": [{
                "field": "device_img",
                "label": "设备图片",
                "ids": [6001],
            }],
            "img_ids": [6001],
        }]
        captions = [(1, "图6.1 数据中心/信息中心", "数据中心/信息中心")]
        sections = [(1, "数据中心/信息中心", "information_room")]

        warnings = PHOTOS.equipment_caption_section_warnings(
            equipment,
            captions,
            sections,
            unit_func="C",
            children_func="B",
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("6.1 其他用电设备", warnings[0])
        self.assertIn("6.1 信息机房系统", warnings[0])

    def test_chapter6_reports_hygiene_photo_placed_outside_water_system(self):
        equipment = [{
            "name": "蹲便器",
            "category": "卫生器具",
            "img_ids": [6101],
        }]
        captions = [(1, "图6.1 蹲便器", "蹲便器")]
        sections = [(1, "蹲便器", "air_heating")]

        warnings = PHOTOS.equipment_caption_section_warnings(
            equipment,
            captions,
            sections,
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("空调与供暖系统", warnings[0])
        self.assertIn("用水系统", warnings[0])

    def test_life_hotwater_photo_routes_to_water_without_moving_fact(self):
        equipment = [
            {
                "name": "燃气热水锅炉",
                "category": "生活热水",
            },
            {
                "name": "电热水器",
                "category": "生活热水",
            },
            {
                "name": "生活水泵",
                "category": "动力",
            },
        ]

        routed = PHOTOS._route_chapter6_equipment(equipment, {})

        self.assertEqual(routed[0]["equipment_section_key"], "gas_system")
        self.assertEqual(routed[0]["photo_section_key"], "water_system")
        self.assertEqual(routed[0]["photo_category"], "用水设施")
        self.assertEqual(routed[1]["equipment_section_key"], "other_energy")
        self.assertEqual(routed[1]["photo_section_key"], "water_system")
        self.assertEqual(routed[2]["equipment_section_key"], "other_energy")
        self.assertEqual(routed[2]["photo_section_key"], "other_energy")
        self.assertEqual(
            PHOTOS.equipment_caption_gaps(equipment, [], []),
            [],
        )

    def test_chapter6_equipment_without_images_does_not_create_photo_warning(self):
        equipment = [{
            "name": "蹲便器",
            "category": "卫生器具",
        }]

        warnings = PHOTOS.equipment_caption_section_warnings(
            equipment,
            [],
            [],
        )

        self.assertEqual(warnings, [])

    def test_chapter6_pairs_duplicate_caption_names_one_to_one(self):
        equipment = [
            {
                "name": "供水泵",
                "photo_section_key": "other_energy",
                "photo_section_title": "其他用电设备",
            },
            {
                "name": "供水泵",
                "photo_section_key": "water_system",
                "photo_section_title": "用水系统",
            },
        ]
        captions = [
            (1, "图6.1 供水泵", "供水泵"),
            (2, "图6.2 供水泵", "供水泵"),
        ]
        sections = [
            (1, "供水泵", "other_energy"),
            (2, "供水泵", "water_system"),
        ]

        warnings = PHOTOS.equipment_caption_section_warnings(
            equipment,
            captions,
            sections,
        )

        self.assertEqual(warnings, [])


class PhotoPruneTests(unittest.TestCase):
    def make_project(self, root: Path):
        images_dir = root / "data" / "images"
        images_dir.mkdir(parents=True)
        kept = images_dir / "kept.png"
        orphan = images_dir / "orphan.png"
        kept.write_bytes(PNG)
        orphan.write_bytes(PNG + b"orphan")
        (root / "report_images.json").write_text(
            json.dumps({
                "images": [{
                    "caption": "图6.1 冷水机组",
                    "src": "data/images/kept.png",
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        return kept, orphan

    def test_report_mode_moves_nothing_and_apply_mode_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            kept, orphan = self.make_project(root)

            report = PHOTOS.prune_photo_orphans(root, apply=False)

            self.assertEqual(report["orphans"], ["data/images/orphan.png"])
            self.assertTrue(kept.is_file())
            self.assertTrue(orphan.is_file())

            first = PHOTOS.prune_photo_orphans(root, apply=True)

            self.assertFalse(first.get("blocked"))
            self.assertTrue(kept.is_file())
            self.assertFalse(orphan.exists())
            moved = Path(first["trash_dir"]) / "data" / "images" / "orphan.png"
            self.assertTrue(moved.is_file())

            second = PHOTOS.prune_photo_orphans(root, apply=True)

            self.assertEqual(second["orphans"], [])
            self.assertEqual(second["moved"], [])

    def test_apply_is_blocked_when_finalization_has_warnings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _kept, orphan = self.make_project(root)
            (root / "photo_finalization_status.json").write_text(
                json.dumps({
                    "clean": False,
                    "warnings": ["第6章缺图"],
                }, ensure_ascii=False),
                encoding="utf-8",
            )

            result = PHOTOS.prune_photo_orphans(root, apply=True)

            self.assertTrue(result["blocked"])
            self.assertEqual(result["orphans"], ["data/images/orphan.png"])
            self.assertTrue(orphan.is_file())

    def test_apply_is_blocked_when_reference_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _kept, orphan = self.make_project(root)
            (root / "report_images.json").unlink()

            result = PHOTOS.prune_photo_orphans(root, apply=True)

            self.assertTrue(result["blocked"])
            self.assertIn("report_images.json", result["reason"])
            self.assertTrue(orphan.is_file())

    def test_cli_dry_run_never_moves_prune_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _kept, orphan = self.make_project(root)

            rc = PHOTOS.main([
                str(root),
                "--prune",
                "apply",
                "--dry-run",
                "--quiet",
            ])

            self.assertEqual(rc, 0)
            self.assertTrue(orphan.is_file())


class PhotoProvenanceCategoryTests(unittest.TestCase):
    def test_overall_photo_fallback_records_the_actual_building_category(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "chapter_md").mkdir(parents=True)
            (root / "chapter_md" / "ch2.md").write_text(
                "# 第2章\n\n图2.1 测试单位单位整体外观\n",
                encoding="utf-8",
            )
            building = root / "building.png"
            building.write_bytes(PNG)
            (root / "data.json").write_text(
                json.dumps({
                    "base": {"unit_short": "测试单位"},
                    "images": [{
                        "path": str(building),
                        "category": "建筑外观",
                        "building_name": "门诊楼",
                        "file_id": 101,
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            (root / "report_images.json").write_text(
                json.dumps({"images": []}, ensure_ascii=False),
                encoding="utf-8",
            )

            rc = PHOTOS.main([str(root), "--quiet"])

            self.assertEqual(rc, 0)
            entry = json.loads(
                (root / "report_images.json").read_text(encoding="utf-8")
            )["images"][0]
            self.assertEqual(entry["source"]["category"], "建筑外观")


if __name__ == "__main__":
    unittest.main()
