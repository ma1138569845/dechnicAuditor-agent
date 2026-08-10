"""Tests for tools.office_editor_tool — tool registration and handlers.

Unit-level: the editor_sdk MCP client and SDK manager are mocked so the suite
runs on any machine without the binary installed.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import tools.office_editor_tool as oet


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestOfficeEditorRegistration:
    """The office_editor toolset contains all registered Office tools."""

    EXPECTED_TOOLS = {
        "office_create",
        "office_open",
        "office_edit",
        "office_save",
        "office_preview",
        "office_status",
        "office_list_tools",
        "office_render",
        "office_audit",
        "office_template_extract",
    }

    def test_tools_registered_in_office_editor_toolset(self):
        from tools.registry import registry

        engine_tools = {
            "office_create", "office_open", "office_edit", "office_save",
            "office_preview", "office_status", "office_list_tools",
        }
        runtime_tools = {
            "office_render", "office_audit", "office_template_extract",
        }

        for tool_name in self.EXPECTED_TOOLS:
            entry = registry.get_entry(tool_name)
            assert entry is not None, f"{tool_name} not registered"
            assert entry.toolset == "office_editor", f"{tool_name} wrong toolset"
            assert entry.schema is not None
            if tool_name in engine_tools:
                assert entry.check_fn is not None, f"{tool_name} missing check_fn"
            if tool_name in runtime_tools:
                assert entry.check_fn is None, f"{tool_name} should not have check_fn"

    def test_check_fn_requires_an_engine(self):
        """The tools are available when editor_sdk OR officecli is present."""
        from tools.registry import registry

        entry = registry.get_entry("office_create")
        # Neither engine present -> unavailable.
        with patch.object(oet, "_sdk_available", return_value=False), \
             patch.object(oet, "_officecli_available", return_value=False):
            assert entry.check_fn() is False
        # Only officecli present -> available.
        with patch.object(oet, "_sdk_available", return_value=False), \
             patch.object(oet, "_officecli_available", return_value=True):
            assert entry.check_fn() is True
        # Only editor_sdk present -> available.
        with patch.object(oet, "_sdk_available", return_value=True), \
             patch.object(oet, "_officecli_available", return_value=False):
            assert entry.check_fn() is True

    def test_office_editor_toolset_declared_in_toolsets(self):
        from toolsets import TOOLSETS, resolve_toolset

        assert "office_editor" in TOOLSETS
        assert self.EXPECTED_TOOLS == set(resolve_toolset("office_editor"))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestDocTypeFromPath:
    def test_extension_mapping(self):
        assert oet._doc_type_from_path("/tmp/report.docx") == "doc"
        assert oet._doc_type_from_path("/tmp/report.DOCX") == "doc"
        assert oet._doc_type_from_path("/tmp/data.xlsx") == "sheet"
        assert oet._doc_type_from_path("/tmp/data.csv") == "sheet"
        assert oet._doc_type_from_path("/tmp/slides.pptx") == "slide"
        assert oet._doc_type_from_path("/tmp/slides.PPT") == "slide"

    def test_unknown_extension_defaults_to_doc(self):
        assert oet._doc_type_from_path("/tmp/file.odt") == "doc"


# ---------------------------------------------------------------------------
# Handler tests (mocked MCP client + SDK manager)
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp():
    with patch.object(oet, "mcp_client") as mock_mcp:
        mock_mcp.call = MagicMock()
        mock_mcp.call_text = MagicMock()
        mock_mcp.list_tools = MagicMock()
        yield mock_mcp


@pytest.fixture
def sdk():
    with patch.object(oet, "sdk_manager") as mock_sdk:
        mock_sdk.get_editor_status = MagicMock(return_value={
            "code": 0,
            "message": "ok",
            "open_editors": [],
            "pool_size": 0,
        })
        mock_sdk.get_preview_url = MagicMock(return_value="http://127.0.0.1:39099/static/doc/pc.html?file_id=abc&local_edit=1")
        mock_sdk.port = 39099
        mock_sdk.health_check = MagicMock(return_value=True)
        yield mock_sdk


@pytest.fixture(autouse=True)
def _sdk_present():
    """Default to the editor_sdk path so handler tests are deterministic on any
    machine. Officecli-fallback tests override ``oet._sdk_available`` to False."""
    with patch.object(oet, "_sdk_available", return_value=True):
        yield


class TestOfficeCreate:
    def test_create_returns_file_id(self, mcp, sdk):
        # create_doc returns the file_id; the readiness probe then succeeds.
        mcp.call.side_effect = [
            {"file_id": "new_doc_1", "file_path": "/tmp/report.docx"},
            {"content": [{"text": '{"ok":true}'}]},
        ]

        with patch.object(oet, "_try_open_preview", return_value=False) as top:
            out = json.loads(oet._handle_office_create({"doc_type": "doc", "file_path": "/tmp/report.docx"}))

        assert mcp.call.call_args_list[0][0] == ("create_doc", {"file_path": "/tmp/report.docx"})
        # readiness probe ran before returning
        assert mcp.call.call_args_list[1][0] == ("doc_get_outline", {"file_id": "new_doc_1"})
        assert out["success"] is True
        assert out["file_id"] == "new_doc_1"
        assert out["doc_type"] == "doc"
        top.assert_called_once()

    def test_create_requires_file_path(self, mcp, sdk):
        out = json.loads(oet._handle_office_create({"doc_type": "doc"}))
        assert "error" in out
        mcp.call.assert_not_called()

    def test_create_propagates_mcp_error(self, mcp, sdk):
        mcp.call.side_effect = RuntimeError("boom")
        out = json.loads(oet._handle_office_create({"doc_type": "doc", "file_path": "/tmp/a.docx"}))
        assert "error" in out and "boom" in out["error"]


class TestOfficeOpen:
    def test_open_existing_file(self, mcp, sdk, tmp_path):
        f = tmp_path / "real.docx"
        f.write_bytes(b"PK")
        # open_file is streaming: no file_id on the envelope. The editor
        # registers in the pool keyed by its file path; readiness probe then
        # succeeds.
        mcp.call.side_effect = [
            {"content": [{"text": f"open started (doc), streaming for file_id={f}"}]},
            {"content": [{"text": '{"ok":true}'}]},
        ]
        sdk.get_editor_status.return_value = {
            "code": 0, "message": "ok",
            "open_editors": [{"file_id": "opened_9", "file_path": str(f), "type": "doc"}],
            "pool_size": 1,
        }

        out = json.loads(oet._handle_office_open({"file_path": str(f)}))
        assert mcp.call.call_args_list[0][0] == ("open_file", {"file_path": str(f), "file_type": "doc"})
        # the pool-resolved file_id is returned and probed ready
        assert mcp.call.call_args_list[1][0] == ("doc_get_outline", {"file_id": "opened_9"})
        assert out["success"] is True
        assert out["file_id"] == "opened_9"

    def test_open_missing_file_errors(self, mcp, sdk, tmp_path):
        out = json.loads(oet._handle_office_open({"file_path": str(tmp_path / "nope.docx")}))
        assert "error" in out
        mcp.call.assert_not_called()


class TestOfficeEdit:
    def test_injects_file_id_and_parses_json(self, mcp, sdk):
        mcp.call.return_value = {"content": [{"text": '{"last_edit_index": 21, "message": "insert_text ok"}'}]}
        out = json.loads(oet._handle_office_edit({
            "file_id": "doc_1", "operation": "doc_insert_text", "arguments": {"idx": 0, "text": "hi"},
        }))
        mcp.call.assert_called_once_with("doc_insert_text", {"idx": 0, "text": "hi", "file_id": "doc_1"})
        assert out["success"] is True
        assert out["result"] == {"last_edit_index": 21, "message": "insert_text ok"}

    def test_requires_file_id_and_operation(self, mcp, sdk):
        assert "error" in json.loads(oet._handle_office_edit({"operation": "doc_insert_text"}))
        assert "error" in json.loads(oet._handle_office_edit({"file_id": "x"}))


class TestOfficeSave:
    def test_passes_file_path_to_save_file(self, mcp, sdk):
        """editor_sdk's save_file expects 'file_path' — never 'save_path'."""
        mcp.call_text.return_value = "File saved"
        out = json.loads(oet._handle_office_save({"file_id": "doc_1", "save_path": "C:/out.docx"}))
        mcp.call_text.assert_called_once()
        args = mcp.call_text.call_args[0][1]
        assert "file_path" in args and args["file_path"].endswith("out.docx")
        assert "save_path" not in args
        assert out["success"] is True

    def test_save_without_path_omits_file_path(self, mcp, sdk):
        mcp.call_text.return_value = "ok"
        oet._handle_office_save({"file_id": "doc_1"})
        assert mcp.call_text.call_args[0][1] == {"file_id": "doc_1"}

    def test_save_requires_file_id(self, mcp, sdk):
        assert "error" in json.loads(oet._handle_office_save({}))


class TestOfficePreview:
    def test_no_desktop_returns_url(self, mcp, sdk):
        with patch.object(oet, "_try_open_preview", return_value=False):
            out = json.loads(oet._handle_office_preview({"file_id": "doc_1", "doc_type": "doc"}))
        assert out["success"] is True
        assert out["preview_url"].startswith("http://127.0.0.1:")

    def test_desktop_emits_preview_open(self, mcp, sdk):
        with patch.object(oet, "_try_open_preview", return_value=True) as top:
            out = json.loads(oet._handle_office_preview({"file_id": "doc_1", "doc_type": "doc"}))
        top.assert_called_once_with("doc_1", "doc")


class TestOfficeStatus:
    def test_returns_pool_status(self, mcp, sdk):
        sdk.get_editor_status.return_value = {"code": 0, "message": "ok", "open_editors": [], "pool_size": 2}
        out = json.loads(oet._handle_office_status({}))
        assert out["success"] is True
        assert out["pool_size"] == 2
        assert out["healthy"] is True

    def test_errors_are_caught(self, mcp, sdk):
        sdk.get_editor_status.side_effect = RuntimeError("down")
        out = json.loads(oet._handle_office_status({}))
        assert "error" in out


class TestOfficeListTools:
    def test_prefix_filter(self, mcp, sdk):
        mcp.list_tools.return_value = [
            {"name": "doc_insert_text", "inputSchema": {"required": ["idx"], "properties": {"idx": {"type": "integer"}}}},
            {"name": "sheet_set_cell_value", "inputSchema": {"properties": {}}},
        ]
        out = json.loads(oet._handle_office_list_tools({"prefix": "doc_"}))
        assert out["total"] == 1
        assert out["tools"][0]["name"] == "doc_insert_text"


class TestWaitForEditorReady:
    def test_returns_true_when_probe_succeeds(self, mcp):
        """Readiness is decided by probing a cheap read, not the pool entry."""
        mcp.call.return_value = {"content": [{"text": '{"ok":true}'}]}
        assert oet._wait_for_editor_ready("doc_1", "doc", timeout=5) is True
        assert mcp.call.call_args_list[0][0] == ("doc_get_outline", {"file_id": "doc_1"})

    def test_returns_false_on_timeout(self, mcp):
        mcp.call.side_effect = RuntimeError("not open")
        assert oet._wait_for_editor_ready("missing", "doc", timeout=0.3) is False

    def test_survives_probe_errors(self, mcp):
        mcp.call.side_effect = [RuntimeError("boom"), {"content": [{"text": '{"ok":true}'}]}]
        assert oet._wait_for_editor_ready("doc_1", "doc", timeout=5) is True

    def test_sheet_probe_uses_sheet_get_sheet_info(self, mcp):
        mcp.call.return_value = {"content": [{"text": '{"sheets":[]}'}]}
        assert oet._wait_for_editor_ready("sheet_1", "sheet", timeout=5) is True
        assert mcp.call.call_args_list[0][0][0] == "sheet_get_sheet_info"

    def test_slide_probe_honours_is_open_field(self, mcp):
        """slide_get_info succeeds with is_open:false until the presentation
        opens — the readiness check must honour that field."""
        mcp.call.side_effect = [
            {"content": [{"text": '{"is_open":false,"slide_count":0}'}]},
            {"content": [{"text": '{"is_open":true,"slide_count":2}'}]},
        ]
        assert oet._wait_for_editor_ready("slide_1", "slide", timeout=5) is True
        assert mcp.call.call_args_list[0][0][0] == "slide_get_info"

    def test_text_marked_not_open_is_not_ready(self, mcp):
        mcp.call.side_effect = [
            {"content": [{"text": "document is not open"}]},
            {"content": [{"text": '{"ok":true}'}]},
        ]
        assert oet._wait_for_editor_ready("doc_1", "doc", timeout=5) is True


# ---------------------------------------------------------------------------
# Officecli fallback engine (tier-3): no editor_sdk, handlers route via officecli
# ---------------------------------------------------------------------------


class TestOfficeCliFallback:
    """When editor_sdk is absent, the 7 office_editor tools degrade to officecli."""

    def test_open_returns_path_file_id(self, mcp, sdk, tmp_path):
        f = tmp_path / "real.docx"
        f.write_bytes(b"PK")
        with patch.object(oet, "_sdk_available", return_value=False):
            out = json.loads(oet._handle_office_open({"file_path": str(f)}))
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["file_id"] == os.path.abspath(str(f))
        mcp.call.assert_not_called()

    def test_create_runs_officecli(self, mcp, sdk, tmp_path):
        f = tmp_path / "new.docx"
        with patch.object(oet, "_sdk_available", return_value=False):
            with patch.object(oet, "_run_officecli", return_value={"success": True, "stdout": "", "stderr": ""}) as mock_run:
                out = json.loads(oet._handle_office_create({"doc_type": "doc", "file_path": str(f)}))
        mock_run.assert_called_once()
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["file_id"] == os.path.abspath(str(f))

    def test_edit_directs_to_office_cli_command(self, mcp, sdk):
        with patch.object(oet, "_sdk_available", return_value=False):
            out = json.loads(oet._handle_office_edit({
                "file_id": "C:/a.docx",
                "operation": "doc_insert_text",
                "arguments": {"text": "hi"},
            }))
        assert out["success"] is False
        assert "office_cli_command" in out["message"]
        mcp.call.assert_not_called()

    def test_save_runs_officecli(self, mcp, sdk, tmp_path):
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        with patch.object(oet, "_sdk_available", return_value=False):
            with patch.object(oet, "_run_officecli", return_value={"success": True, "stdout": "", "stderr": ""}) as mock_run:
                out = json.loads(oet._handle_office_save({"file_id": str(f)}))
        mock_run.assert_called_once()
        assert out["success"] is True
        assert out["engine"] == "officecli"

    def test_preview_starts_officecli_watch(self, mcp, sdk):
        with patch.object(oet, "_sdk_available", return_value=False):
            with patch("tools.office_cli_tool.start_office_preview", return_value={"url": "http://127.0.0.1:39200/"}) as mock_start:
                out = json.loads(oet._handle_office_preview({"file_id": "C:/a.docx", "doc_type": "doc"}))
        mock_start.assert_called_once_with("C:/a.docx")
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["preview_url"] == "http://127.0.0.1:39200/"

    def test_status_lists_officecli_sessions(self, mcp, sdk):
        from tools.office_cli_tool import _sessions, _sessions_lock
        proc = MagicMock()
        proc.poll.return_value = None
        # Seed a session WITHOUT holding the lock while the handler runs —
        # _sessions_lock is a plain (non-reentrant) threading.Lock.
        with _sessions_lock:
            _sessions["C:/a.docx"] = {"process": proc}
        try:
            with patch.object(oet, "_sdk_available", return_value=False):
                out = json.loads(oet._handle_office_status({}))
        finally:
            with _sessions_lock:
                _sessions.pop("C:/a.docx", None)
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["open_count"] == 1

    def test_list_tools_reports_officecli_mode(self, mcp, sdk):
        with patch.object(oet, "_sdk_available", return_value=False):
            out = json.loads(oet._handle_office_list_tools({}))
        assert out["success"] is True
        assert out["engine"] == "officecli"
        assert out["total"] == 0
