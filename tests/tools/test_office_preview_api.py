"""Tests for tools.office_preview_api — desktop preview bridge to editor_sdk.

Unit-level: the MCP client and SDK manager are mocked.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import tools.office_preview_api as api


@pytest.fixture(autouse=True)
def _mock_sdk():
    with patch.object(api, "sdk_manager") as mock_sdk:
        mock_sdk.get_editor_status = MagicMock(return_value={
            "code": 0, "message": "ok", "open_editors": [], "pool_size": 0,
        })
        mock_sdk.get_preview_url = MagicMock(
            return_value="http://127.0.0.1:39099/static/doc/pc.html?file_id=x&local_edit=1"
        )
        mock_sdk.ensure_started = MagicMock(return_value=39099)
        yield mock_sdk


@pytest.fixture(autouse=True)
def _mock_mcp():
    with patch.object(api, "mcp_client") as mock_mcp:
        mock_mcp.call = MagicMock()
        yield mock_mcp


@pytest.fixture(autouse=True)
def _no_localapi_open():
    """By default /localapi/open is unavailable in unit tests; tests that want
    the UUID path patch this explicitly."""
    with patch.object(api, "_localapi_open_uuid", side_effect=RuntimeError("no sdk in tests")):
        yield


class TestOpenOfficePreview:
    def test_binary_missing_returns_sdk_not_found(self):
        with patch.object(api, "_find_binary", return_value=None):
            out = api.open_office_preview("C:/a.docx")
        assert out["error"] == "OFFICE_SDK_NOT_FOUND"

    def test_relative_path_rejected(self):
        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview("relative/doc.docx")
        assert out["error"] == "PATH_OUTSIDE_SANDBOX"

    def test_missing_file_errors(self):
        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview("C:/no/such/file.docx")
        assert out["error"] == "OFFICE_SDK_START_FAILED"

    def test_open_calls_mcp_and_returns_url(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")

        # Fresh open: the pool starts empty; open_file registers the editor and
        # the ready-wait then observes it.
        state = {"opened": False}

        def status_side_effect():
            if state["opened"]:
                return {"code": 0, "message": "ok",
                        "open_editors": [{"file_id": "doc_1", "file_path": str(f)}],
                        "pool_size": 1}
            return {"code": 0, "message": "ok", "open_editors": [], "pool_size": 0}

        _mock_sdk.get_editor_status.side_effect = status_side_effect

        def mcp_call(name, arguments=None):
            if name == "open_file":
                state["opened"] = True
                return {"file_id": "doc_1"}
            return {}

        _mock_mcp.call.side_effect = mcp_call

        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))

        assert _mock_mcp.call.call_args_list[0][0] == ("open_file", {"file_path": str(f), "file_type": "doc"})
        # a readiness probe (doc_get_outline) follows the open call
        assert _mock_mcp.call.call_args_list[1][0][0] == "doc_get_outline"
        assert out["success"] is True
        assert out["file_id"] == "doc_1"
        assert out["doc_type"] == "doc"
        assert out["engine"] == "editor_sdk"
        assert out["url"].startswith("http://127.0.0.1:")
        assert out["preview_base_url"].startswith("http://127.0.0.1:")

    def test_prefers_localapi_open_uuid_over_path_file_id(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")

        # The SDK converts the docx into chunks keyed by file_id. A raw path
        # file_id makes it derive an invalid Windows temp path (drive-letter
        # colon) and the conversion fails with 1070, so the preview must use the
        # UUID returned by /localapi/open instead of the MCP open_file path.
        with patch.object(api, "_localapi_open_uuid", return_value="1B46B49A-369E-4868-9342-7AE381FF3566"):
            out = api.open_office_preview(str(f))

        assert out["success"] is True
        assert out["file_id"] == "1B46B49A-369E-4868-9342-7AE381FF3566"
        # No MCP open_file call — the UUID path is preferred. (The only MCP
        # traffic is the readiness probe doc_get_outline.)
        call_names = [c[0][0] for c in _mock_mcp.call.call_args_list]
        assert "open_file" not in call_names

    def test_localapi_open_failure_falls_back_to_mcp(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")

        state = {"opened": False}

        def status_side_effect():
            if state["opened"]:
                return {"code": 0, "message": "ok",
                        "open_editors": [{"file_id": "doc_1", "file_path": str(f)}],
                        "pool_size": 1}
            return {"code": 0, "message": "ok", "open_editors": [], "pool_size": 0}

        _mock_sdk.get_editor_status.side_effect = status_side_effect

        def mcp_call(name, arguments=None):
            if name == "open_file":
                state["opened"] = True
                return {"file_id": "doc_1"}
            return {}

        _mock_mcp.call.side_effect = mcp_call

        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))

        assert out["success"] is True
        assert out["file_id"] == "doc_1"

    def test_preview_url_is_read_only(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")

        with patch.object(api, "_localapi_open_uuid", return_value="uuid-1"):
            out = api.open_office_preview(str(f))

        # editor_sdk mode is read-only for the human: get_preview_url is called
        # without file_path / editable so sheets don't route to the Univer WYSIWYG.
        call = _mock_sdk.get_preview_url.call_args
        assert call.kwargs.get("file_path") is None
        assert call.kwargs.get("editable") in (None, False)

    def test_streaming_open_file_resolves_file_id_from_pool(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "stream.docx"
        f.write_bytes(b"PK")

        # open_file is streaming: the envelope carries no file_id; the editor
        # registers in the pool asynchronously keyed by its file path, and the
        # open resolves the file_id by matching that path.
        state = {"opened": False}

        def status_side_effect():
            if state["opened"]:
                return {"code": 0, "message": "ok",
                        "open_editors": [{"file_id": "stream_7", "file_path": str(f)}],
                        "pool_size": 1}
            return {"code": 0, "message": "ok", "open_editors": [], "pool_size": 0}

        _mock_sdk.get_editor_status.side_effect = status_side_effect

        def mcp_call(name, arguments=None):
            if name == "open_file":
                state["opened"] = True
                return {"content": [{"text": "open started (doc), streaming for file_id"}]}
            return {}

        _mock_mcp.call.side_effect = mcp_call

        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))

        assert out["success"] is True
        assert out["file_id"] == "stream_7"
        assert out["doc_type"] == "doc"
        assert out["engine"] == "editor_sdk"
        assert out["url"].startswith("http://127.0.0.1:")
        assert out["preview_base_url"].startswith("http://127.0.0.1:")

    def test_reuses_existing_editor_for_same_path(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        _mock_sdk.get_editor_status.return_value = {
            "code": 0, "message": "ok",
            "open_editors": [{"file_id": "existing_1", "file_path": str(f)}],
            "pool_size": 1,
        }
        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))

        # No open_file call — existing editor reused.
        _mock_mcp.call.assert_not_called()
        assert out["file_id"] == "existing_1"

    def test_mcp_error_becomes_start_failed(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        _mock_mcp.call.side_effect = RuntimeError("SDK unreachable")
        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))
        assert out["error"] == "OFFICE_SDK_START_FAILED"
        assert "SDK unreachable" in out["message"]


class TestCloseOfficePreview:
    def test_closes_matching_editor(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        _mock_sdk.get_editor_status.return_value = {
            "code": 0, "message": "ok",
            "open_editors": [{"file_id": "doc_1", "file_path": str(f)}],
            "pool_size": 1,
        }
        out = api.close_office_preview(str(f))
        _mock_mcp.call.assert_called_once()
        assert _mock_mcp.call.call_args[0] == ("close_file", {"file_id": "doc_1", "force": True})
        assert out == {"ok": True}

    def test_close_no_match_still_ok(self, _mock_mcp, _mock_sdk, tmp_path):
        out = api.close_office_preview(str(tmp_path / "nope.docx"))
        _mock_mcp.call.assert_not_called()
        assert out == {"ok": True}

    def test_close_survives_sdk_error(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        _mock_sdk.get_editor_status.side_effect = RuntimeError("down")
        out = api.close_office_preview(str(f))
        assert out == {"ok": True}


class TestOpenOfficePreviewOnlyOffice:
    """When ONLYOFFICE is enabled, open/close bypass editor_sdk entirely."""

    _ENV = {
        "HERMES_OFFICE_DS_URL": "http://10.10.2.55:8090",
        "HERMES_OFFICE_JWT_SECRET": "shared-secret-for-tests-0123456789abcdef",
        "HERMES_OFFICE_CALLBACK_HOST": "192.168.0.238",
    }

    @pytest.fixture(autouse=True)
    def _onlyoffice_env(self):
        with patch.dict(os.environ, self._ENV, clear=True):
            yield

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        from tools.office_onlyoffice import registry
        registry.clear()
        yield
        registry.clear()

    def test_open_returns_onlyoffice_url_without_sdk(
            self, _mock_mcp, _mock_sdk, tmp_path):
        from tools.office_preview_server import preview_server
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")

        # Even though the SDK binary is missing, OnlyOffice must not care.
        with patch.object(api, "_find_binary", return_value=None):
            out = api.open_office_preview(str(f))

        assert out["success"] is True
        assert out["doc_type"] == "doc"
        assert out["engine"] == "onlyoffice"
        assert f"/onlyoffice?file_id={out['file_id']}" in out["url"]
        assert out["url"].startswith(
            f"http://127.0.0.1:{preview_server.port}/onlyoffice?")
        assert out["preview_base_url"] == f"http://127.0.0.1:{preview_server.port}"
        # The SDK must never have been touched.
        _mock_mcp.call.assert_not_called()

    def test_open_missing_file_still_errors(
            self, _mock_mcp, _mock_sdk, tmp_path):
        out = api.open_office_preview(str(tmp_path / "nope.docx"))
        assert out["error"] == "OFFICE_SDK_START_FAILED"
        _mock_mcp.call.assert_not_called()

    def test_open_relative_path_rejected(self, _mock_mcp, _mock_sdk):
        out = api.open_office_preview("relative/doc.docx")
        assert out["error"] == "PATH_OUTSIDE_SANDBOX"

    def test_close_releases_registry_without_sdk(
            self, _mock_mcp, _mock_sdk, tmp_path):
        from tools.office_onlyoffice import registry
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        opened = api.open_office_preview(str(f))
        file_id = opened["file_id"]
        assert registry.lookup(file_id) is not None

        out = api.close_office_preview(str(f))
        assert out == {"ok": True}
        assert registry.lookup(file_id) is None
        _mock_mcp.call.assert_not_called()


class TestOpenOfficePreviewOfficeCliFallback:
    """Tier-3 fallback: when editor_sdk is absent but officecli is present, the
    preview degrades to the officecli watch server."""

    def test_falls_back_to_officecli_url(self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        with patch.object(api, "_find_binary", return_value=None):
            with patch("tools.office_cli_tool.start_office_preview", return_value={
                "url": "http://127.0.0.1:39200/",
            }) as mock_start:
                out = api.open_office_preview(str(f))

        mock_start.assert_called_once()
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["url"] == "http://127.0.0.1:39200/"
        assert out["file_id"] == os.path.abspath(str(f))
        # The SDK must never have been touched.
        _mock_mcp.call.assert_not_called()

    def test_officecli_also_missing_returns_sdk_not_found(
            self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        with patch.object(api, "_find_binary", return_value=None):
            with patch("tools.office_cli_tool.start_office_preview", return_value={
                "error": "OFFICECLI_NOT_FOUND", "message": "officecli not found",
            }):
                out = api.open_office_preview(str(f))

        assert out["error"] == "OFFICE_SDK_NOT_FOUND"
        assert "officecli" in out["message"].lower()

    def test_close_falls_back_to_officecli_stop(
            self, _mock_mcp, _mock_sdk, tmp_path):
        f = tmp_path / "report.docx"
        f.write_bytes(b"PK")
        with patch.object(api, "_find_binary", return_value=None):
            with patch("tools.office_cli_tool.stop_office_preview", return_value={"ok": True}) as mock_stop:
                out = api.close_office_preview(str(f))

        mock_stop.assert_called_once()
        assert out == {"ok": True}

    def test_sdk_mode_keeps_uniter_off_for_sheets(self, _mock_mcp, _mock_sdk, tmp_path):
        """editor_sdk mode previews are read-only: sheets must NOT route to Univer."""
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"PK")
        _mock_sdk.get_editor_status.return_value = {
            "code": 0, "message": "ok",
            "open_editors": [{"file_id": "sheet_1", "file_path": str(f)}],
            "pool_size": 1,
        }
        with patch.object(api, "_find_binary", return_value=os.path.abspath("bin/editor_sdk.exe")):
            out = api.open_office_preview(str(f))

        assert out["success"] is True
        assert out["doc_type"] == "sheet"
        assert out["engine"] == "editor_sdk"
        # get_preview_url must be called WITHOUT file_path / editable so sheets
        # land on the SDK read-only cloud view instead of the Univer editor.
        call = _mock_sdk.get_preview_url.call_args
        assert call.kwargs.get("file_path") is None
        assert out["preview_base_url"].startswith("http://127.0.0.1:")
        assert call.kwargs.get("editable") in (None, False)
