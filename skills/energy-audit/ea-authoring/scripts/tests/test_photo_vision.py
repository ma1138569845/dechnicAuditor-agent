import base64
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII="
)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VISION_PATH = ROOT / "photo_vision.py"
VISION = load_module("photo_vision", VISION_PATH) if VISION_PATH.is_file() else None


class CertificateVerificationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(VISION, "缺少 DeepSeek 证书视觉核验模块")

    def test_matching_title_and_recipient_passes(self):
        result = VISION.evaluate_verification(
            expected_title="节水型单位",
            expected_recipient="日照市岚山区人民医院",
            observed={
                "visible_title": "节水型单位",
                "recipient": "日照市岚山区人民医院",
                "is_single_certificate": True,
                "confidence": 0.96,
            },
        )
        self.assertEqual(result["status"], "pass")

    def test_low_confidence_requires_manual_review(self):
        result = VISION.evaluate_verification(
            expected_title="节水型单位",
            expected_recipient="测试单位",
            observed={
                "visible_title": "节水型单位",
                "recipient": "测试单位",
                "is_single_certificate": True,
                "confidence": 0.55,
            },
        )
        self.assertEqual(result["status"], "review")

    def test_different_visible_title_is_a_conflict(self):
        result = VISION.evaluate_verification(
            expected_title="节水型单位",
            expected_recipient="测试单位",
            observed={
                "visible_title": "节能先进单位",
                "recipient": "测试单位",
                "is_single_certificate": True,
                "confidence": 0.93,
            },
        )
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("证书标题", result["reason"])

    def test_different_recipient_is_a_conflict(self):
        result = VISION.evaluate_verification(
            expected_title="节水型单位",
            expected_recipient="甲单位",
            observed={
                "visible_title": "节水型单位",
                "recipient": "乙单位",
                "is_single_certificate": True,
                "confidence": 0.93,
            },
        )
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("受奖单位", result["reason"])

    def test_verify_certificate_parses_fenced_json(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "certificate.png"
            image.write_bytes(PNG)

            def fake_poster(url, headers, payload, timeout):
                self.assertEqual(payload["model"], "deepseek-flash")
                self.assertEqual(payload["thinking"], {"type": "disabled"})
                self.assertEqual(payload["response_format"], {"type": "json_object"})
                return {
                    "choices": [{
                        "message": {
                            "content": (
                                "```json\n"
                                '{"visible_title":"节水型单位","recipient":"测试单位",'
                                '"is_single_certificate":true,"confidence":0.95}\n'
                                "```"
                            )
                        }
                    }]
                }

            result = VISION.verify_certificate(
                image_path=str(image),
                expected_title="节水型单位",
                expected_recipient="测试单位",
                api_key="test-key",
                poster=fake_poster,
            )
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["observed"]["visible_title"], "节水型单位")

    def test_verify_certificate_accepts_json_from_empty_content_reasoning(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "certificate.png"
            image.write_bytes(PNG)

            def fake_poster(*_args, **_kwargs):
                return {
                    "choices": [{
                        "message": {
                            "content": "",
                            "reasoning_content": (
                                '{"visible_title":"节水型单位","recipient":"测试单位",'
                                '"is_single_certificate":true,"confidence":0.95}'
                            ),
                        }
                    }]
                }

            result = VISION.verify_certificate(
                image_path=str(image),
                expected_title="节水型单位",
                expected_recipient="测试单位",
                api_key="test-key",
                poster=fake_poster,
            )
            self.assertEqual(result["status"], "pass")

    def test_api_failure_degrades_to_unverified(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "certificate.png"
            image.write_bytes(PNG)

            def failing_poster(*_args, **_kwargs):
                raise OSError("network unavailable")

            result = VISION.verify_certificate(
                image_path=str(image),
                expected_title="节水型单位",
                expected_recipient="测试单位",
                api_key="test-key",
                poster=failing_poster,
            )
            self.assertEqual(result["status"], "unverified")

    def test_cache_key_binds_image_and_expected_claim(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "certificate.png"
            image.write_bytes(PNG)
            first = VISION.vision_cache_key(
                image_path=str(image),
                expected_title="节水型单位",
                expected_recipient="测试单位",
                model="deepseek-flash",
            )
            second = VISION.vision_cache_key(
                image_path=str(image),
                expected_title="节能先进单位",
                expected_recipient="测试单位",
                model="deepseek-flash",
            )
            self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
