"""Tests for tools.office_onlyoffice — ONLYOFFICE config/JWT/registry.

Unit-level: env is patched; the preview server singleton is mocked for
``callback_base``; no network or DS is touched.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import tools.office_onlyoffice as oo


_ENV = {
    "HERMES_OFFICE_DS_URL": "http://10.10.2.55:8090",
    "HERMES_OFFICE_JWT_SECRET": "shared-secret-for-tests-0123456789abcdef",
    "HERMES_OFFICE_CALLBACK_HOST": "192.168.0.238",
}


@pytest.fixture(autouse=True)
def _clear_registry():
    oo.registry.clear()
    yield
    oo.registry.clear()


@pytest.fixture(autouse=True)
def _mock_preview_port():
    """callback_base reads the live preview server's port; stub it."""
    fake = MagicMock(port=39250)
    with patch("tools.office_preview_server.preview_server", fake):
        yield


class TestConfig:
    def test_disabled_when_no_ds_url(self):
        with patch.dict(os.environ, {}, clear=True):
            assert oo.is_enabled() is False

    def test_disabled_when_secret_missing(self):
        with patch.dict(os.environ, {"HERMES_OFFICE_DS_URL": "http://x:8090"}, clear=True):
            assert oo.is_enabled() is False

    def test_enabled_when_url_and_secret_set(self):
        with patch.dict(os.environ, _ENV, clear=True):
            assert oo.is_enabled() is True
            assert oo.ds_url() == "http://10.10.2.55:8090"

    def test_callback_host_prefers_env(self):
        with patch.dict(os.environ, _ENV, clear=True):
            assert oo.callback_host() == "192.168.0.238"


class TestJwt:
    def test_sign_verify_roundtrip(self):
        with patch.dict(os.environ, _ENV, clear=True):
            token = oo.sign_jwt({"a": 1})
            assert oo.verify_jwt(token) == {"a": 1}

    def test_verify_rejects_bad_token(self):
        with patch.dict(os.environ, _ENV, clear=True):
            assert oo.verify_jwt("garbage") is None
            assert oo.verify_jwt("") is None

    def test_sign_requires_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError):
                oo.sign_jwt({"a": 1})


class TestRegistry:
    def test_register_and_lookup_by_id_key_path(self):
        rec = oo.registry.register("fid", r"C:\docs\a.docx", "doc")
        assert oo.registry.lookup("fid") is rec
        assert oo.registry.lookup_by_key(rec.key) is rec
        assert oo.registry.find_by_path(r"C:\docs\a.docx") is rec

    def test_rotate_key_invalidates_old(self):
        rec = oo.registry.register("fid", r"C:\docs\a.docx", "doc")
        old = rec.key
        oo.registry.rotate_key("fid")
        assert rec.key != old
        assert oo.registry.lookup_by_key(old) is None
        assert oo.registry.lookup_by_key(rec.key) is rec

    def test_close_removes_all_maps(self):
        rec = oo.registry.register("fid", r"C:\docs\a.docx", "doc")
        oo.registry.close("fid")
        assert oo.registry.lookup("fid") is None
        assert oo.registry.lookup_by_key(rec.key) is None
        assert oo.registry.find_by_path(r"C:\docs\a.docx") is None

    def test_mark_updates_status(self):
        rec = oo.registry.register("fid", r"C:\docs\a.docx", "doc")
        oo.registry.mark("fid", "saved", saved_at="10:00:00")
        assert rec.status == "saved"
        assert rec.saved_at == "10:00:00"


class TestEditorConfig:
    def test_unknown_file_id_returns_error(self):
        with patch.dict(os.environ, _ENV, clear=True):
            assert oo.make_editor_config("nope") == {"error": "file_id not found"}

    def test_config_shape_and_signed_token(self):
        with patch.dict(os.environ, _ENV, clear=True):
            oo.registry.register("fid", r"C:\docs\a.xlsx", "sheet")
            cfg = oo.make_editor_config("fid")
            # The token must verify against the shared secret — check it while
            # the env still carries the secret (verify reads env fresh).
            assert oo.verify_jwt(cfg["token"]) is not None

        assert cfg["documentType"] == "cell"
        assert cfg["document"]["fileType"] == "xlsx"
        assert cfg["document"]["title"] == "a.xlsx"
        assert cfg["document"]["key"]
        assert cfg["editorConfig"]["lang"] == "zh-CN"
        assert cfg["editorConfig"]["mode"] == "edit"
        assert cfg["editorConfig"]["callbackUrl"] == "http://192.168.0.238:39250/api/onlyoffice/save"
        # forcesave makes the DS send a save callback on the Save button/Ctrl+S
        # instead of deferring it to the autosave interval or editor close.
        assert cfg["editorConfig"]["customization"]["forcesave"] is True
        assert cfg["document"]["url"].startswith(
            "http://192.168.0.238:39250/api/onlyoffice/download?file_id=fid&token=")

    def test_doc_type_mapping_word_and_slide(self):
        with patch.dict(os.environ, _ENV, clear=True):
            oo.registry.register("d", r"C:\docs\a.docx", "doc")
            assert oo.make_editor_config("d")["documentType"] == "word"
            oo.registry.register("p", r"C:\docs\a.pptx", "slide")
            assert oo.make_editor_config("p")["documentType"] == "slide"


class TestDownloadToken:
    def test_valid_and_invalid(self):
        with patch.dict(os.environ, _ENV, clear=True):
            good = oo._download_token("fid")
            assert oo.check_download_token("fid", good) is True
            assert oo.check_download_token("other", good) is False
            assert oo.check_download_token("fid", "bad") is False

    def test_callback_auth_parses_bearer(self):
        with patch.dict(os.environ, _ENV, clear=True):
            token = oo.sign_jwt({"status": 2})
            assert oo.check_callback_auth(f"Bearer {token}") is not None
            assert oo.check_callback_auth("") is None
            assert oo.check_callback_auth("Basic abc") is None


class TestForceSave:
    def test_forwards_forcesave_command_to_ds(self):
        with patch.dict(os.environ, _ENV, clear=True):
            oo.registry.register("fid", r"C:\docs\a.docx", "doc")
            key = oo.registry.lookup("fid").key
            calls = []

            class _Resp:
                def read(self):
                    return json.dumps({"key": key, "error": 0}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            def fake_urlopen(req, timeout=10):
                calls.append((req.full_url, req.data))
                return _Resp()

            with patch("tools.office_onlyoffice.urllib.request.urlopen",
                       fake_urlopen):
                result = oo.force_save("fid")
            assert result == {"key": key, "error": 0}
            assert calls[0][0] == "http://10.10.2.55:8090/command"
            sent = json.loads(calls[0][1].decode("utf-8"))
            assert oo.verify_jwt(sent["token"]) == {"c": "forcesave", "key": key}

    def test_unknown_file_raises_keyerror(self):
        with patch.dict(os.environ, _ENV, clear=True):
            with pytest.raises(KeyError):
                oo.force_save("nope")

    def test_disabled_raises_runtimeerror(self):
        with patch.dict(os.environ, {"HERMES_OFFICE_JWT_SECRET": "x"}, clear=True):
            oo.registry.register("fid", r"C:\docs\a.docx", "doc")
            with pytest.raises(RuntimeError):
                oo.force_save("fid")
