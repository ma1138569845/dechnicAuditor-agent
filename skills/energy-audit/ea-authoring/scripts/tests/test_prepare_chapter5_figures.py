import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "prepare_chapter5_figures.py"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_chapter5_figures", SCRIPT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FigureProject:
    def __init__(self, root: Path):
        self.root = root
        self.charts = root / "charts"
        self.chapter_md = root / "chapter_md"
        self.charts.mkdir()
        self.chapter_md.mkdir()
        (self.charts / "energy_flow.png").write_bytes(PNG)
        (self.charts / "chart_electricity_total.png").write_bytes(PNG + b"\n")
        captions = [
            "图5.1 能源资源流向图",
            "图5.2 2022年-2024年总用电量（单位：kWh）",
        ]
        (self.chapter_md / "ch5_import.md").write_text(
            "# 第5章\n\n" + "\n\n".join(captions) + "\n",
            encoding="utf-8",
        )
        figures = [
            {
                "figure_no": "5.1",
                "caption": captions[0],
                "src": "charts/energy_flow.png",
                "kind": "energy_flow",
                "energy_code": "",
                "sha256": sha256(self.charts / "energy_flow.png"),
            },
            {
                "figure_no": "5.2",
                "caption": captions[1],
                "src": "charts/chart_electricity_total.png",
                "kind": "total",
                "energy_code": "electricity",
                "sha256": sha256(self.charts / "chart_electricity_total.png"),
            },
        ]
        (root / "chapter5_figures.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "batch_id": "test-batch",
                    "figures": figures,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (root / "report_images.json").write_text(
            json.dumps(
                {
                    "images": [
                        {"caption": "图4.1 计量器具照片", "src": "data/images/meter.png"},
                        {"caption": "图5.1 旧图注", "src": "charts/old.png"},
                        {"caption": "图5.2 旧图注", "src": "charts/old2.png"},
                        {"caption": "图6.1 冷水机组", "src": "data/images/chiller.png"},
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def images(self):
        return json.loads(
            (self.root / "report_images.json").read_text(encoding="utf-8")
        )["images"]


class PrepareChapter5FiguresTests(unittest.TestCase):
    def test_rebuilds_only_ch5_entries_and_adds_hashes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as td:
            project = FigureProject(Path(td))
            before = (project.root / "report_images.json").read_bytes()
            self.assertEqual(module.main([str(project.root), "--quiet"]), 0)

            entries = project.images()
            ch5 = [e for e in entries if e["caption"].startswith("图5.")]
            self.assertEqual(
                [e["caption"] for e in ch5],
                [
                    "图5.1 能源资源流向图",
                    "图5.2 2022年-2024年总用电量（单位：kWh）",
                ],
            )
            self.assertEqual(
                [e["src"] for e in ch5],
                ["charts/energy_flow.png", "charts/chart_electricity_total.png"],
            )
            self.assertTrue(all(e["sha256"] for e in ch5))
            self.assertEqual(
                [e["caption"] for e in entries if e["caption"].startswith("图4.")],
                ["图4.1 计量器具照片"],
            )
            self.assertEqual(
                [e["caption"] for e in entries if e["caption"].startswith("图6.")],
                ["图6.1 冷水机组"],
            )
            self.assertEqual(
                (project.root / "report_images.json.bak").read_bytes(), before
            )

    def test_caption_mismatch_exits_two_without_rewriting_manifest(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as td:
            project = FigureProject(Path(td))
            md = project.chapter_md / "ch5_import.md"
            md.write_text(
                md.read_text(encoding="utf-8").replace("总用电量", "用电总量"),
                encoding="utf-8",
            )
            before = (project.root / "report_images.json").read_bytes()
            self.assertEqual(module.main([str(project.root), "--quiet"]), 2)
            self.assertEqual(
                (project.root / "report_images.json").read_bytes(), before
            )

    def test_changed_chart_hash_exits_two(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as td:
            project = FigureProject(Path(td))
            (project.charts / "energy_flow.png").write_bytes(PNG + b"changed")
            self.assertEqual(module.main([str(project.root), "--quiet"]), 2)


if __name__ == "__main__":
    unittest.main()
