import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "sync_ea_skills.py"
SPEC = importlib.util.spec_from_file_location("sync_ea_skills_under_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContentDigestTests(unittest.TestCase):
    def test_text_line_endings_are_equivalent(self):
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "lf.md"
            crlf = Path(tmp) / "crlf.md"
            lf.write_bytes("第一行\n第二行\n".encode("utf-8"))
            crlf.write_bytes("第一行\r\n第二行\r\n".encode("utf-8"))

            self.assertEqual(MODULE.md5(lf), MODULE.md5(crlf))

    def test_text_content_changes_are_still_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.md"
            right = Path(tmp) / "right.md"
            left.write_text("旧内容\n", encoding="utf-8")
            right.write_text("新内容\n", encoding="utf-8")

            self.assertNotEqual(MODULE.md5(left), MODULE.md5(right))

    def test_binary_line_endings_remain_significant(self):
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "lf.bin"
            crlf = Path(tmp) / "crlf.bin"
            lf.write_bytes(b"a\nb")
            crlf.write_bytes(b"a\r\nb")

            self.assertNotEqual(MODULE.md5(lf), MODULE.md5(crlf))


if __name__ == "__main__":
    unittest.main()
