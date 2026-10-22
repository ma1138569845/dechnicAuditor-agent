import base64
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MIRROR_ROOT = Path(__file__).resolve().parents[5]
CHAPTER5 = MIRROR_ROOT / "tools" / "energy_audit" / "chapter5_agent.py"
DEPLOY_ROOT = Path(
    os.environ.get(
        "EA_TARGET_REPO",
        r"D:\data\pyProject\dc_agent\dechnicAuditor-agent",
    )
)
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def load_chapter5_module():
    # 被测文件来自镜像仓；运行依赖（indicators 等）来自正式部署环境。
    if str(DEPLOY_ROOT) not in sys.path:
        sys.path.insert(0, str(DEPLOY_ROOT))
    spec = importlib.util.spec_from_file_location("chapter5_agent_under_test", CHAPTER5)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {CHAPTER5}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_flow(_en, _config, output_dir):
    path = Path(output_dir) / "energy_flow.png"
    path.write_bytes(PNG)
    return str(path)


class Chapter5FigureGenerationTests(unittest.TestCase):
    def setUp(self):
        self.module = load_chapter5_module()

    @staticmethod
    def data():
        years = {"2022", "2023", "2024"}
        return {
            "energy_data": {
                year: {
                    "electricity": {
                        "total": 1200,
                        "monthly": [100] * 12,
                    },
                    "water": {
                        "total": 240,
                        "monthly": [20] * 12,
                    },
                    "natural_gas": {
                        "total": 100,
                        "monthly": [10] * 12,
                    },
                }
                for year in years
            },
            "cost_data": {
                year: {
                    "electricity": {
                        "name": "电费",
                        "total": 100,
                    },
                    "water": {
                        "name": "水费",
                        "total": 10,
                    },
                }
                for year in years
            },
        }

    def config(self, root):
        charts = root / "charts"
        return {
            "unit_name": "测试单位",
            "building_area": 1000,
            "people_count": 100,
            "beds_count": 0,
            "institution_category": "党政机关",
            "chart_dir": str(charts),
            "chapter5_manifest_path": str(root / "chapter5_figures.json"),
        }

    def test_generates_manifest_with_hashes_and_removes_obsolete_known_charts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            charts = root / "charts"
            charts.mkdir()
            (charts / "chart_stale_total.png").write_bytes(PNG)
            (charts / "cost_pie_2020.png").write_bytes(PNG)
            (charts / "keep.png").write_bytes(PNG)
            config = self.config(root)

            with mock.patch.object(
                self.module, "_generate_flow_diagram", side_effect=write_flow
            ):
                manifest = self.module.generate_charts(
                    self.data(), config, str(charts)
                )

            self.assertEqual(manifest["schema_version"], 1)
            self.assertTrue(manifest["batch_id"])
            captions = [f["caption"] for f in manifest["figures"]]
            self.assertEqual(captions[0], "图5.1 能源资源流向图")
            self.assertEqual(
                captions[-3:],
                [
                    "图5.8 2022年能源费用占比",
                    "图5.9 2023年能源费用占比",
                    "图5.10 2024年能源费用占比",
                ],
            )
            self.assertEqual(
                [f["figure_no"] for f in manifest["figures"]],
                [f"5.{i}" for i in range(1, len(captions) + 1)],
            )
            self.assertTrue(all(len(f["sha256"]) == 64 for f in manifest["figures"]))
            self.assertTrue(all((root / f["src"]).is_file() for f in manifest["figures"]))
            self.assertFalse((charts / "chart_stale_total.png").exists())
            self.assertFalse((charts / "cost_pie_2020.png").exists())
            self.assertTrue((charts / "keep.png").exists())
            on_disk = json.loads(
                (root / "chapter5_figures.json").read_text(encoding="utf-8")
            )
            self.assertEqual(on_disk, manifest)

            markdown = self.module.generate_chapter5_md(
                self.data(), config, manifest
            )
            self.assertIn("图5.1 能源资源流向图\n", markdown)
            self.assertNotIn("![图5.1", markdown)

    def test_expected_chart_failure_is_recorded_as_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            charts = root / "charts"
            charts.mkdir()
            config = self.config(root)

            with mock.patch.object(
                self.module, "_generate_flow_diagram", side_effect=write_flow
            ), mock.patch.object(
                self.module, "_generate_total_bar_chart", return_value=False
            ):
                manifest = self.module.generate_charts(
                    self.data(), config, str(charts)
                )

            self.assertTrue(manifest["figures"])
            missing = [
                figure for figure in manifest["figures"]
                if figure.get("kind") == "total"
            ]
            self.assertTrue(missing)
            self.assertTrue(all(f["status"] == "missing" for f in missing))
            self.assertTrue(all("生成失败" in f["reason"] for f in missing))
            markdown = self.module.generate_chapter5_md(
                self.data(), config, manifest
            )
            for figure in missing:
                self.assertIn(figure["caption"], markdown)


if __name__ == "__main__":
    unittest.main()
