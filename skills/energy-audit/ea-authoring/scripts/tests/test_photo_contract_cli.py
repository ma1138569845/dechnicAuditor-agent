import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[3]


class PhotoContractCliTests(unittest.TestCase):
    def test_chapter6_guide_does_not_template_missing_data_as_pending_verification(self):
        guide = (
            REPO_ROOT
            / "skills"
            / "energy-audit"
            / "ea-authoring"
            / "references"
            / "chapter-guides-6-8.md"
        ).read_text(encoding="utf-8")
        for forbidden_template in (
            "其他用气设备情况需进一步核实【待核实】",
            "供热量及供暖费用资料需进一步补充【待核实】",
        ):
            with self.subTest(template=forbidden_template):
                self.assertNotIn(forbidden_template, guide)

    def test_photo_scripts_help_uses_repo_chapter6_contract(self):
        for name in (
            "prepare_report_photos.py",
            "prepare_writing_context.py",
        ):
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, str(ROOT / name), "--help"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stderr or result.stdout,
                )
                self.assertIn("usage:", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
