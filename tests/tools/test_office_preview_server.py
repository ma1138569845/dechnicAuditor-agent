"""Tests for tools.office_preview_server + the get_preview_url routing.

The preview proxy is the same-origin server that hosts the human editor UI
(``/editor``), the OnlyOffice embed shell (``/onlyoffice``), and forwards
JSON-RPC to editor_sdk's ``/mcp`` (bypassing CORS).
Real SDK traffic is mocked; only the localhost HTTP server itself is exercised.
"""

import io
import json
import os
from unittest.mock import patch
from urllib.parse import quote

import pytest
import urllib.error
import urllib.request

import tools.office_preview_server as pvs
from tools.office_editor_html import EDITOR_HTML


@pytest.fixture(scope="module")
def server_base():
    """Start the real preview server once for the module; stop afterwards."""
    port = pvs.preview_server.ensure_started()
    base = f"http://127.0.0.1:{port}"
    yield base
    pvs.preview_server.stop()


class _FakeResp:
    status = 200

    def __init__(self, body: bytes, headers=None):
        self._body = body
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:  # urllib raises on 4xx/5xx
        return e.code, e.read(), e.headers


def _post(base, path, payload, headers=None):
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------
class TestGetEditorUrl:
    def test_encodes_params_and_keeps_slashes(self):
        url = pvs.preview_server.get_editor_url("a b", "sheet", "C:/dir/x file.xlsx")
        assert url.startswith(f"http://127.0.0.1:{pvs.preview_server.port}/onlyoffice?")
        assert "file_id=a%20b" in url
        assert "doc_type=sheet" in url
        # quote() keeps "/" unescaped by design; URLSearchParams decodes both.
        assert "file_path=C%3A/dir/x%20file.xlsx" in url

    def test_file_path_optional(self):
        url = pvs.preview_server.get_editor_url("abc", "slide")
        assert "file_id=abc" in url and "doc_type=slide" in url
        assert "file_path=" not in url


# ---------------------------------------------------------------------------
# HTTP endpoints (real localhost server; SDK traffic mocked)
# ---------------------------------------------------------------------------
class TestEndpoints:
    def test_editor_page_served(self, server_base):
        status, body, _ = _get(server_base, "/editor")
        assert status == 200
        assert body.decode("utf-8") == EDITOR_HTML
        assert b"saveAll" in body  # our editor dispatch is present

    def test_unknown_route_404(self, server_base):
        status, body, _ = _get(server_base, "/nope")
        assert status == 404

    def test_health_proxies_sdk(self, server_base, monkeypatch):
        monkeypatch.setattr(pvs.sdk_manager, "ensure_started", lambda: 39150)
        monkeypatch.setattr(
            pvs, "_urlopen",
            lambda req, timeout: _FakeResp(b"ok", {"Content-Type": "text/plain"}),
        )
        status, body, headers = _get(server_base, "/api/health")
        assert status == 200
        assert body == b"ok"
        assert headers.get("Access-Control-Allow-Origin") == "*"

    def test_mcp_proxy_forwards_and_echoes(self, server_base, monkeypatch):
        monkeypatch.setattr(pvs.sdk_manager, "ensure_started", lambda: 39150)
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["data"] = req.data
            return _FakeResp(
                b'{"jsonrpc":"2.0","id":1,"result":'
                b'{"content":[{"text":"{\\"ok\\":true}"}]}}'
            )

        monkeypatch.setattr(pvs, "_urlopen", fake_urlopen)

        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "doc_get_outline", "arguments": {"file_id": "x"}},
        }
        status, body, headers = _post(server_base, "/api/mcp", payload)
        assert status == 200
        assert captured["url"] == "http://127.0.0.1:39150/mcp"
        # forwarded body preserves the JSON-RPC payload
        assert json.loads(captured["data"]) == payload
        resp = json.loads(body.decode("utf-8"))
        assert resp["result"]["content"][0]["text"] == '{"ok":true}'
        assert headers.get("Access-Control-Allow-Origin") == "*"

    def test_mcp_proxy_sdk_http_error_becomes_upstream_code(self, server_base, monkeypatch):
        monkeypatch.setattr(pvs.sdk_manager, "ensure_started", lambda: 39150)

        def boom(req, timeout):
            raise urllib.error.HTTPError(
                req.full_url, 503, "Service Unavailable", None, io.BytesIO(b"upstream down")
            )

        monkeypatch.setattr(pvs, "_urlopen", boom)
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "x", "arguments": {}}}
        status, body, _ = _post(server_base, "/api/mcp", payload)
        assert status == 503
        assert json.loads(body.decode("utf-8"))["error"] == "upstream down"

    def test_mcp_proxy_sdk_down_becomes_502(self, server_base, monkeypatch):
        monkeypatch.setattr(pvs.sdk_manager, "ensure_started", lambda: 39150)

        def boom(req, timeout):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(pvs, "_urlopen", boom)
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": "x", "arguments": {}}}
        status, body, _ = _post(server_base, "/api/mcp", payload)
        assert status == 502


# ---------------------------------------------------------------------------
# get_preview_url routing (sheet->OnlyOffice, else read-only SDK SPA)
# ---------------------------------------------------------------------------
class TestGetPreviewUrlRouting:
    def test_sheet_with_file_path_routes_to_onlyoffice_when_enabled(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)
        monkeypatch.setattr(
            pvs.preview_server, "get_editor_url",
            lambda fid, dt, fp: "http://127.0.0.1:39200/onlyoffice?file_id=%s" % fid,
        )
        with patch.dict(os.environ, _ONLYOFFICE_ENV, clear=True):
            url = sdk_manager.get_preview_url("abc", "sheet", True, "C:/f.xlsx")
        assert url == "http://127.0.0.1:39200/onlyoffice?file_id=abc"

    def test_sheet_with_file_path_stays_spa_when_onlyoffice_disabled(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)
        url = sdk_manager.get_preview_url("abc", "sheet", True, "C:/f.xlsx")
        assert url == "http://127.0.0.1:39150/static/sheet/pc.html?file_id=abc"
        assert "local_edit" not in url

    def test_doc_with_file_path_stays_read_only_spa(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)
        url = sdk_manager.get_preview_url("abc", "doc", True, "C:/f.docx")
        assert url == "http://127.0.0.1:39150/static/doc/pc.html?file_id=abc"
        # read-only: no local_edit / no http-local client binding
        assert "local_edit" not in url
        assert "client=" not in url

    def test_slide_stays_spa(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)
        url = sdk_manager.get_preview_url("abc", "slide", True, "C:/f.pptx")
        assert "/static/slide/pc.html" in url

    def test_proxy_failure_falls_back_to_spa(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)

        def boom(*a, **k):
            raise RuntimeError("proxy unavailable")

        monkeypatch.setattr(pvs.preview_server, "get_editor_url", boom)
        with patch.dict(os.environ, _ONLYOFFICE_ENV, clear=True):
            url = sdk_manager.get_preview_url("abc", "sheet", True, "C:/f.xlsx")
        assert "/static/sheet/pc.html" in url
        assert "local_edit" not in url

    def test_no_file_path_keeps_spa(self, monkeypatch):
        from tools.office_sdk_manager import sdk_manager
        monkeypatch.setattr(sdk_manager, "ensure_started", lambda: 39150)
        url = sdk_manager.get_preview_url("abc", "doc", True)
        assert url == "http://127.0.0.1:39150/static/doc/pc.html?file_id=abc"


# ---------------------------------------------------------------------------
# ONLYOFFICE editor (remote DocumentServer) endpoints
# ---------------------------------------------------------------------------
_ONLYOFFICE_ENV = {
    "HERMES_OFFICE_DS_URL": "http://10.10.2.55:8090",
    "HERMES_OFFICE_JWT_SECRET": "shared-secret-for-tests-0123456789abcdef",
    "HERMES_OFFICE_CALLBACK_HOST": "192.168.0.238",
}


class TestOnlyOfficeRoutes:
    @pytest.fixture(autouse=True)
    def _onlyoffice_env(self):
        with patch.dict(os.environ, _ONLYOFFICE_ENV, clear=True):
            yield

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        from tools.office_onlyoffice import registry
        registry.clear()
        yield
        registry.clear()

    def _register(self, file_path, doc_type):
        import uuid
        from tools.office_onlyoffice import registry
        file_id = str(uuid.uuid4())
        registry.register(file_id, str(file_path), doc_type)
        return file_id

    def test_shell_served_with_ds_api_url(self, server_base):
        status, body, _ = _get(server_base, "/onlyoffice")
        assert status == 200
        html = body.decode("utf-8")
        assert "web-apps/apps/api/documents/api.js" in html
        assert "10.10.2.55:8090" in html
        assert "/api/onlyoffice/config" in html
        # The shell exposes postAiSelection on window so the same-origin plugin
        # iframe (Community Edition fallback) can report selection directly.
        assert "window.postAiSelection = postAiSelection" in html
        # The shell reports selection to the desktop renderer itself (same
        # origin as preview_base_url), so it posts office-ai-selection via
        # window.parent.postMessage and reads text via GetSelectedText.
        assert "office-ai-selection" in html
        assert "window.parent.postMessage" in html
        assert "onSelectionChanged" in html
        assert "GetSelectedText" in html
        # The manual AI-edit fallback button was removed (the plugin's auto
        # selection reporting makes it redundant). Guard that it does not come
        # back — the shell must not re-add a chrome button for it.
        assert 'id="ai-edit"' not in html
        # Structural guards: these catch a broken/regressed inline script (a
        # missing helper or renamed symbol previously slipped past the substring
        # assertions and broke the selection reporting at runtime).
        assert "function postAiSelection" in html
        # The shell measures its editor iframe and sends a document-area anchor
        # with every selection report, so the desktop AI-edit pill floats inside
        # the document (below the DS ribbon) instead of stacked on the DS chrome.
        assert "function editorDocumentAnchor" in html
        assert "msg.anchorX = anchor.anchorX" in html
        assert "msg.anchorY = anchor.anchorY" in html
        assert "function readAiSelection" in html
        assert "executeMethod('GetSelectedText'" in html
        # The shell forwards the plugin's mouse-up flag so the renderer can
        # dismiss the AI pill when the user clicks without changing the
        # selection (e.g. the DS ribbon keeps the selection text unchanged).
        assert "msg.mouseUp = true" in html
        assert "postAiSelection(data.text, data.mouseUp)" in html
        # The Automation API (executeMethod / attachEvent) is exposed through a
        # connector created with editor.createConnector(), not directly on the
        # DocEditor instance. These guards detect the wrong-object regression.
        assert "var connector" in html
        assert "editor.createConnector" in html
        assert "connector.attachEvent('onSelectionChanged'" in html
        assert "exec.executeMethod('GetSelectedText'" in html
        # The shell also reports whether the editor holds unsaved edits, so the
        # desktop renderer can decide whether an external (agent) change may
        # reload the editor or must ask first.
        assert "office-editor-state" in html
        assert "function postEditorState" in html
        assert "onDocumentStateChange" in html
        # The shell latches "edited since the last real save". DS 9.x fires
        # onDocumentStateChange(false) as soon as its co-authoring service
        # acknowledges the changes — not when the file is saved — so the raw
        # flag must not clear the latch; only a status-6 save does.
        assert "var editedSinceSave = false" in html
        assert "editedSinceSave = true" in html
        assert "/api/onlyoffice/state?file_id=" in html
        assert "body: JSON.stringify({ dirty: dirty })" in html
        # A real save (status poll sees 'saved') clears the latch.
        assert html.count("editedSinceSave = false") >= 2
        # forceSave is not a hard failure on non-zero errors: DS 9.x answers
        # error 1 even when it delivers the status-6 callback (and error 4 for
        # no changes), so the save outcome is decided by the callback — the
        # bar flips to 已保存 via the status poll, or concludeSave() reports
        # 无更改 after the wait window instead of a bogus failure banner.
        assert "function concludeSave" in html
        assert "无更改" in html
        assert "setTimeout(concludeSave, 6000)" in html
        assert "保存失败: 文档未在编辑器中打开" in html

    def test_shell_404_when_disabled(self, server_base):
        with patch.dict(os.environ, {}, clear=True):
            status, body, _ = _get(server_base, "/onlyoffice")
        assert status == 404
        with patch.dict(os.environ, {}, clear=True):
            for path in ("/onlyoffice-plugin/config.json",
                         "/onlyoffice-plugin/index.html",
                         "/onlyoffice-plugin/plugin.js"):
                status, _, _ = _get(server_base, path)
                assert status == 404, path

    def test_plugin_routes_served_when_enabled(self, server_base):
        # Community Edition lacks the Automation API connector, so the preview
        # server provides a same-origin plugin that uses the Plugin API to read
        # the selection and hand it to the shell page.
        status, body, _ = _get(server_base, "/onlyoffice-plugin/config.json")
        assert status == 200
        cfg = json.loads(body.decode("utf-8"))
        assert cfg["name"] == "Hermes AI Bridge"
        assert "index.html" in cfg["variations"][0]["url"]

        status, body, _ = _get(server_base, "/onlyoffice-plugin/index.html")
        assert status == 200
        html = body.decode("utf-8")
        assert "Hermes AI Bridge" in html
        assert "plugin.js" in html
        assert "10.10.2.55:8090" in html

        status, body, _ = _get(server_base, "/onlyoffice-plugin/plugin.js")
        assert status == 200
        js = body.decode("utf-8")
        assert "window.Asc.plugin" in js
        assert "executeMethod('GetSelectedText'" in js
        assert "postAiSelection" in js
        # Every editor mouse-up force-reports the selection (bypassing the
        # lastText dedup) so the renderer hears about clicks that keep the same
        # selection and can dismiss the pill — the polling timer still dedups.
        assert "readSelection(null, true)" in js
        assert "if (!force && value === lastText)" in js
        assert "mouseUp: mouseUp" in js

        status, _, _ = _get(server_base, "/onlyoffice-plugin/icon.png")
        assert status == 200

    def test_config_returns_signed_editor_config(self, server_base, tmp_path):
        from tools.office_onlyoffice import verify_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        file_id = self._register(f, "doc")
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/config?file_id={file_id}")
        assert status == 200
        cfg = json.loads(body.decode("utf-8"))
        assert cfg["documentType"] == "word"
        assert cfg["document"]["title"] == "a.docx"
        assert cfg["document"]["url"].startswith(
            f"http://192.168.0.238:{pvs.preview_server.port}"
            f"/api/onlyoffice/download?file_id={file_id}&token=")
        assert cfg["editorConfig"]["callbackUrl"].endswith("/api/onlyoffice/save")
        # The Community Edition fallback plugin is registered in the editor
        # config so it loads inside the DS editor iframe.
        assert "plugins" in cfg["editorConfig"]
        plugins = cfg["editorConfig"]["plugins"]
        plugins_data = plugins["pluginsData"]
        assert any("/onlyoffice-plugin/config.json" in url for url in plugins_data)
        # The plugin GUID must be in autostart: without it the DS registers the
        # plugin but never runs it, so window.Asc.plugin stays undefined and the
        # AI-edit selection bridge silently never fires.
        assert "asc.{hermes-ai-bridge}" in plugins["autostart"]
        assert verify_jwt(cfg["token"]) is not None

    def test_config_unknown_file_returns_error_envelope(self, server_base):
        status, body, _ = _get(server_base, "/api/onlyoffice/config?file_id=nope")
        assert status == 200  # envelope error so the shell can show it
        assert json.loads(body.decode("utf-8")) == {"error": "file_id not found"}

    def test_download_returns_bytes_with_valid_token(self, server_base, tmp_path):
        from tools.office_onlyoffice import _download_token
        f = tmp_path / "a.xlsx"
        f.write_bytes(b"XLSXBYTES")
        file_id = self._register(f, "sheet")
        token = _download_token(file_id)
        status, body, headers = _get(
            server_base,
            f"/api/onlyoffice/download?file_id={file_id}&token={quote(token)}")
        assert status == 200
        assert body == b"XLSXBYTES"
        assert "spreadsheetml" in headers.get("Content-Type", "")

    def test_download_rejects_bad_token(self, server_base, tmp_path):
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        file_id = self._register(f, "doc")
        status, body, _ = _get(
            server_base, f"/api/onlyoffice/download?file_id={file_id}&token=bad")
        assert status == 401

    def test_save_writes_edited_bytes(self, server_base, tmp_path, monkeypatch):
        from tools.office_onlyoffice import registry, sign_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        rec = registry.lookup(file_id)
        old_key = rec.key

        def fake_urlopen(req, timeout=60):
            return _FakeResp(b"EDITEDBYDS")

        monkeypatch.setattr(pvs, "_urlopen", fake_urlopen)
        body = {
            "status": 2,
            "key": old_key,
            "url": "http://10.10.2.55:8090/cache/edited.docx",
            "users": ["hermes"],
        }
        token = sign_jwt(body)
        status, resp, _ = _post(server_base, "/api/onlyoffice/save", body,
                                headers={"Authorization": f"Bearer {token}"})
        assert status == 200
        assert json.loads(resp.decode("utf-8")) == {"error": 0}
        assert f.read_bytes() == b"EDITEDBYDS"
        # Key is kept for the current editing session; rotation happens on close.
        assert registry.lookup(file_id).key == old_key
        assert registry.lookup(file_id).status == "saved"

    def test_save_rejects_config_token(self, server_base, tmp_path):
        from tools.office_onlyoffice import registry
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        rec = registry.lookup(file_id)
        # Obtain the config token a client would see in /api/onlyoffice/config.
        cfg_status, cfg_body, _ = _get(
            server_base, f"/api/onlyoffice/config?file_id={file_id}")
        assert cfg_status == 200
        config_token = json.loads(cfg_body.decode("utf-8"))["token"]
        body = {
            "status": 2,
            "key": rec.key,
            "url": "http://10.10.2.55:8090/cache/edited.docx",
            "users": ["hermes"],
        }
        status, resp, _ = _post(server_base, "/api/onlyoffice/save", body,
                                headers={"Authorization": f"Bearer {config_token}"})
        assert status == 401

    def test_save_rejects_untrusted_url(self, server_base, tmp_path):
        from tools.office_onlyoffice import registry, sign_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        rec = registry.lookup(file_id)
        body = {
            "status": 2,
            "key": rec.key,
            "url": "file:///etc/passwd",
            "users": ["hermes"],
        }
        token = sign_jwt(body)
        status, resp, _ = _post(server_base, "/api/onlyoffice/save", body,
                                headers={"Authorization": f"Bearer {token}"})
        assert status == 200
        assert json.loads(resp.decode("utf-8")) == {"error": 1}
        assert f.read_bytes() == b"ORIGINAL"
        assert registry.lookup(file_id).status == "error"

    def test_second_save_with_same_key_writes(self, server_base, tmp_path, monkeypatch):
        from tools.office_onlyoffice import registry, sign_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        old_key = registry.lookup(file_id).key

        calls = []

        def fake_urlopen(req, timeout=60):
            calls.append(req.full_url if hasattr(req, "full_url") else req)
            return _FakeResp(b"EDITED" + str(len(calls)).encode())

        monkeypatch.setattr(pvs, "_urlopen", fake_urlopen)
        url = "http://10.10.2.55:8090/cache/edited.docx"
        for _ in range(2):
            body = {"status": 2, "key": old_key, "url": url,
                    "users": ["hermes"]}
            token = sign_jwt(body)
            status, resp, _ = _post(server_base, "/api/onlyoffice/save", body,
                                    headers={"Authorization": f"Bearer {token}"})
            assert status == 200
            assert json.loads(resp.decode("utf-8")) == {"error": 0}
        assert f.read_bytes() == b"EDITED2"

    def test_save_rotates_key_on_editor_close(self, server_base, tmp_path, monkeypatch):
        from tools.office_onlyoffice import registry, sign_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        old_key = registry.lookup(file_id).key

        monkeypatch.setattr(pvs, "_urlopen",
                            lambda req, timeout: _FakeResp(b"EDITED"))
        body = {
            "status": 2,
            "key": old_key,
            "url": "http://10.10.2.55:8090/cache/edited.docx",
            "users": ["hermes"],
        }
        token = sign_jwt(body)
        _post(server_base, "/api/onlyoffice/save", body,
              headers={"Authorization": f"Bearer {token}"})
        assert registry.lookup(file_id).key == old_key

        close_body = {"status": 1, "key": old_key}
        close_token = sign_jwt(close_body)
        status, resp, _ = _post(server_base, "/api/onlyoffice/save",
                                close_body,
                                headers={"Authorization": f"Bearer {close_token}"})
        assert status == 200
        assert json.loads(resp.decode("utf-8")) == {"error": 0}
        assert registry.lookup(file_id).key != old_key

    def test_save_requires_jwt(self, server_base, tmp_path):
        from tools.office_onlyoffice import registry
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        body = {"status": 2, "key": registry.lookup(file_id).key,
                "url": f.as_uri()}
        status, body, _ = _post(server_base, "/api/onlyoffice/save", body)
        assert status == 401

    def test_status_endpoint(self, server_base, tmp_path):
        from tools.office_onlyoffice import registry
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        file_id = self._register(f, "doc")
        registry.mark(file_id, "saved", saved_at="09:30:00")
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert status == 200
        s = json.loads(body.decode("utf-8"))
        assert s["status"] == "saved" and s["saved_at"] == "09:30:00"
        # No DS save yet -> the baseline is the mtime at open. The file is
        # unchanged since then, so nothing counts as external.
        assert s["changed_externally"] is False
        # The shell latch starts clean.
        assert s["dirty"] is False

    def test_state_endpoint_sets_dirty_and_status_echoes_it(
            self, server_base, tmp_path):
        """The shell mirrors its unsaved-edits latch; /status hands it back."""
        from tools.office_onlyoffice import registry
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        file_id = self._register(f, "doc")

        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert json.loads(body.decode("utf-8"))["dirty"] is False

        status, body, _ = _post(
            server_base, f"/api/onlyoffice/state?file_id={file_id}",
            {"dirty": True})
        assert status == 200
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert json.loads(body.decode("utf-8"))["dirty"] is True

        # The latch can clear again after a real save.
        status, body, _ = _post(
            server_base, f"/api/onlyoffice/state?file_id={file_id}",
            {"dirty": False})
        assert status == 200
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert json.loads(body.decode("utf-8"))["dirty"] is False

    def test_state_endpoint_unknown_file_id(self, server_base):
        status, _, _ = _post(
            server_base,
            "/api/onlyoffice/state?file_id=does-not-exist",
            {"dirty": True})
        assert status == 404

    def test_status_reports_external_write_before_any_ds_save(
            self, server_base, tmp_path):
        """An agent write right after open is external even before the DS saves."""
        from tools.office_onlyoffice import registry
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")

        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert status == 200
        assert json.loads(body.decode("utf-8"))["changed_externally"] is False

        # The agent edits the file directly (no DS involved) -> external.
        f.write_bytes(b"EDITEDBYAGENT")
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert status == 200
        assert json.loads(body.decode("utf-8"))["changed_externally"] is True

    def test_status_distinguishes_ds_save_from_external_write(
            self, server_base, tmp_path, monkeypatch):
        """changed_externally flips only when someone other than the DS wrote.

        Before any DS save the baseline is the mtime at open, so a direct
        rewrite of the file counts as external even though the DS never saved.
        """
        from tools.office_onlyoffice import registry, sign_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"ORIGINAL")
        file_id = self._register(f, "doc")
        rec = registry.lookup(file_id)

        monkeypatch.setattr(pvs, "_urlopen",
                            lambda req, timeout: _FakeResp(b"EDITEDBYDS"))
        body = {
            "status": 2,
            "key": rec.key,
            "url": "http://10.10.2.55:8090/cache/edited.docx",
            "users": ["hermes"],
        }
        token = sign_jwt(body)
        status, resp, _ = _post(server_base, "/api/onlyoffice/save", body,
                                headers={"Authorization": f"Bearer {token}"})
        assert status == 200
        assert json.loads(resp.decode("utf-8")) == {"error": 0}

        # Right after the DS save, the on-disk bytes match the editor's view.
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert status == 200
        assert json.loads(body.decode("utf-8"))["changed_externally"] is False

        # An external write (an agent edit landing on disk) flips the flag.
        f.write_bytes(b"EDITEDBYAGENT")
        status, body, _ = _get(server_base,
                               f"/api/onlyoffice/status?file_id={file_id}")
        assert status == 200
        s = json.loads(body.decode("utf-8"))
        assert s["changed_externally"] is True
        assert s["status"] == "saved"

    def test_force_save_forwards_command_service_and_returns_result(
            self, server_base, tmp_path):
        from tools.office_onlyoffice import registry, verify_jwt
        f = tmp_path / "a.docx"
        f.write_bytes(b"PK")
        file_id = self._register(f, "doc")
        key = registry.lookup(file_id).key
        calls = []
        real_urlopen = urllib.request.urlopen

        def fake_urlopen(req, timeout=10):
            # Only mock the DS command-service call; everything else (the test
            # client's own _post to the preview server) passes through.
            if req.full_url.startswith("http://10.10.2.55"):
                calls.append((req.full_url, req.data))
                return _FakeResp(json.dumps({"key": key, "error": 0}).encode())
            return real_urlopen(req, timeout=timeout)

        with patch("tools.office_onlyoffice.urllib.request.urlopen", fake_urlopen):
            status, body, _ = _post(server_base,
                                    f"/api/onlyoffice/force-save?file_id={file_id}",
                                    {})
        assert status == 200
        assert json.loads(body.decode("utf-8")) == {"key": key, "error": 0}
        assert calls and calls[0][0] == "http://10.10.2.55:8090/command"
        sent = json.loads(calls[0][1].decode("utf-8"))
        assert verify_jwt(sent["token"]) == {"c": "forcesave", "key": key}

    def test_force_save_unknown_file_returns_404(self, server_base):
        status, body, _ = _post(server_base,
                                "/api/onlyoffice/force-save?file_id=nope", {})
        assert status == 404


class TestOfficeSelection:
    """GET /api/office-selection bridges spreadsheet cell selection."""

    def test_returns_selection_text_and_range(self, server_base, monkeypatch):
        from tools.office_mcp_client import mcp_client
        from tools.office_sdk_manager import sdk_manager

        monkeypatch.setattr(
            sdk_manager, "get_editor_status",
            lambda: {
                "open_editors": [
                    {"file_path": "C:/dir/report.xlsx", "file_id": "sheet_123"}
                ]
            },
        )
        monkeypatch.setattr(
            mcp_client, "call_json",
            lambda name, args: {"ranges": ["A1:B2"], "sheet_id": "0"},
        )

        status, body, _ = _get(
            server_base, "/api/office-selection?file_path=C%3A/dir/report.xlsx")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert data["text"] == "A1:B2"
        assert data["range"] == "A1:B2"
        assert data["sheet_id"] == "0"

    def test_returns_null_when_file_not_open(self, server_base, monkeypatch):
        from tools.office_sdk_manager import sdk_manager

        monkeypatch.setattr(
            sdk_manager, "get_editor_status",
            lambda: {"open_editors": []},
        )

        status, body, _ = _get(
            server_base, "/api/office-selection?file_path=C%3A/dir/missing.xlsx")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert data["text"] is None
        assert data["range"] is None

    def test_returns_null_when_no_range_selected(self, server_base, monkeypatch):
        from tools.office_mcp_client import mcp_client
        from tools.office_sdk_manager import sdk_manager

        monkeypatch.setattr(
            sdk_manager, "get_editor_status",
            lambda: {
                "open_editors": [
                    {"file_path": "C:/dir/report.xlsx", "file_id": "sheet_123"}
                ]
            },
        )
        monkeypatch.setattr(
            mcp_client, "call_json",
            lambda name, args: {},
        )

        status, body, _ = _get(
            server_base, "/api/office-selection?file_path=C%3A/dir/report.xlsx")
        assert status == 200
        data = json.loads(body.decode("utf-8"))
        assert data["text"] is None
        assert data["range"] is None

    def test_rejects_missing_file_path(self, server_base):
        status, body, _ = _get(server_base, "/api/office-selection")
        assert status == 400
        assert b"missing file_path" in body

    def test_binds_loopback_when_disabled(self):
        server = pvs.PreviewServer()
        with patch.dict(os.environ, {}, clear=True):
            server.ensure_started()
        try:
            assert server._http.server_address[0] == "127.0.0.1"
        finally:
            server.stop()

    def test_binds_lan_when_enabled_with_fixed_port(self):
        server = pvs.PreviewServer()
        env = dict(_ONLYOFFICE_ENV)
        env["HERMES_OFFICE_PREVIEW_PORT"] = "39251"
        with patch.dict(os.environ, env, clear=True):
            port = server.ensure_started()
        try:
            assert port == 39251
            assert server._http.server_address[0] == "0.0.0.0"
        finally:
            server.stop()
