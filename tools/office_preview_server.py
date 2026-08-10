#!/usr/bin/env python3
"""Same-origin preview proxy + custom human editor server for Office docs.

Why this exists
---------------
The raw ``editor_sdk.exe`` only serves its editor SPA at ``/static/<type>/pc.html``
and does **not** set CORS headers. That SPA is the Tencent-Docs cloud viewer; its
editable *local* mode requires being loaded from a whitelisted pathname
(``/doc/local_edit`` etc.) that WorkBuddy's desktop proxy provides — the bare SDK
returns 404 for those. So pointing a browser at the SDK directly yields a
**read-only** cloud view, and a custom editor on another origin is blocked by
CORS.

This module solves both problems with a tiny localhost HTTP server:

  * Serves the SDK's real editor SPA (``pc.html``) at its local-edit
    whitelisted pathnames (``/doc/local_edit``, ``/sheet/local_edit``, ...)
    so the SPA's ``isLocalFile()`` check passes and the local editing engine
    (wasm worker) activates. The URL is loaded with ``client=desktop_local``
    (the client mode the SPA treats as editable — ``http_local`` / ``sdk_local``
    are explicitly excluded from local-edit mode).
  * Serves the **ONLYOFFICE embed shell** at ``/onlyoffice`` when the remote
    DocumentServer is configured (``HERMES_OFFICE_DS_URL`` + shared JWT secret).
    The shell drives ``tools.office_onlyoffice`` — the same-origin
    ``/api/onlyoffice/*`` endpoints host the on-disk file, hand the DS the
    signed editor config, and receive its save callbacks so edits land back on
    disk. This is the real WYSIWYG editor path for all three formats.
  * Reverse-proxies the SDK's static asset tree (``/static/*``) and local
    file API (``/localapi/*``) so the SPA's absolute chunk URLs resolve on the
    same origin.
  * Proxies  ``POST /api/mcp``  and  ``GET /api/health``  to the running
    editor_sdk process, adding permissive CORS headers.
  * Keeps the self-contained human editor at ``GET /editor`` as a fallback
    when the SPA route is unavailable.

Run model: a single daemon thread serves one port for the whole Hermes session.
The desktop renderer mounts the preview URL in an iframe. When OnlyOffice is
enabled every ``.docx/.xlsx/.pptx`` opens in the remote DocumentServer (real
WYSIWYG editing); otherwise the SDK's read-only cloud view is served, with
editing via AI (MCP) tools.
"""

import html
import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse

from tools.office_sdk_manager import sdk_manager

logger = logging.getLogger(__name__)

# Module-level alias so tests can patch the proxy's outbound call without
# intercepting the test client's own urllib traffic.
_urlopen = urllib.request.urlopen

PREVIEW_PORT_RANGE_START = 39200
PREVIEW_PORT_RANGE_END = 39299

# Pathnames the SDK SPA's ``isLocalFile()`` treats as local-edit mode.
# ``/doc`` matches its whitelist exactly; ``/sheet`` / ``/slide`` only require
# the pathname to contain ``/local_edit``. Serving pc.html at these paths is
# what flips the SPA from read-only cloud view to local editable mode.
LOCAL_EDIT_PATHS = {
    "/doc/local_edit": "doc",
    "/doc/local_file/local_edit": "doc",
    "/doc/local_file/kaiwu/ai_preview/local_edit": "doc",
    "/doc/ai_preview/local_edit": "doc",
    "/sheet/local_edit": "sheet",
    "/slide/local_edit": "slide",
}

# Self-contained editor HTML (served at GET /editor).  Kept inline so the
# feature works even if the on-disk copy is missing.
from tools.office_editor_html import EDITOR_HTML  # noqa: E402

# OnlyOffice editor content types (served to the DocumentServer on download).
_OFFICE_CONTENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
    ".ppt": "application/vnd.ms-powerpoint",
}

# ONLYOFFICE editor shell (served at GET /onlyoffice). Loads the DS editor
# API script, fetches the signed config from /api/onlyoffice/config, mounts
# DocsAPI.DocEditor, and exposes a 强制保存 button + save-status polling.
_ONLYOFFICE_SHELL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>文档编辑</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { display: flex; flex-direction: column; overflow: hidden; background: #fff;
         font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; }
  #oo-bar {
    display: flex; align-items: center; gap: 12px; flex: 0 0 auto;
    padding: 6px 12px; background: #f5f6f8; border-bottom: 1px solid #e0e0e0;
  }
  .bar-title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar-status { color: #666; }
  .bar-status[data-kind="error"] { color: #d93025; }
  .bar-status[data-kind="saved"] { color: #188038; }
  .bar-save {
    margin-left: auto; padding: 4px 16px; border: 1px solid #ccc; border-radius: 4px;
    background: #fff; cursor: pointer; font: inherit;
  }
  .bar-save:hover:not(:disabled) { background: #f0f0f0; }
  .bar-save:disabled { opacity: .5; cursor: default; }
  #placeholder { flex: 1 1 auto; min-height: 0; }
</style>
</head>
<body>
<div id="oo-bar">
  <span id="title" class="bar-title">文档</span>
  <span id="status" class="bar-status" data-kind="loading">加载中…</span>
  <button id="save" class="bar-save" disabled>保存</button>
</div>
<div id="placeholder"></div>
<script src="{DS_API_JS}"></script>
<script>
(function () {
  var params = new URLSearchParams(window.location.search);
  var fileId = params.get('file_id');
  var titleEl = document.getElementById('title');
  var statusEl = document.getElementById('status');
  var saveBtn = document.getElementById('save');
  var editor = null;

  function setStatus(kind, msg) {
    statusEl.dataset.kind = kind;
    statusEl.textContent = msg;
  }

  if (!fileId) { setStatus('error', '缺少 file_id 参数'); return; }

  fetch('/api/onlyoffice/config?file_id=' + encodeURIComponent(fileId))
    .then(function (r) { if (!r.ok) throw new Error('加载配置失败 (HTTP ' + r.status + ')'); return r.json(); })
    .then(function (cfg) {
      if (!cfg || cfg.error) throw new Error((cfg && cfg.error) || '加载配置失败');
      titleEl.textContent = cfg.document.title;
      editor = new DocsAPI.DocEditor('placeholder', Object.assign({}, cfg, {
        events: {
          onDocumentReady: function () { setStatus('ready', '已就绪'); saveBtn.disabled = false; },
          onError: function (e) { setStatus('error', '编辑器错误: ' + (e && e.message ? e.message : '未知')); },
          onRequestClose: function () { try { editor.destroyEditor(); } catch (err) {} },
          onSelectionChanged: function (event) {
            // Report the current selection to the desktop renderer (the parent
            // frame) so the AI-edit toolbar can anchor on it. selectionType is
            // 'none' | 'range' | 'text'; only 'text' carries actual text.
            var d = event && event.data;
            window.parent.postMessage({
              type: 'office-ai-selection',
              text: d && d.selectionType === 'text' ? d.text : null,
              selectionType: d ? d.selectionType : 'none'
            }, '*');
          }
        }
      }));
      window.__onlyofficeEditor = editor;
      saveBtn.addEventListener('click', function () {
        // The client-side serviceCommand('mc:forceSave') fires no callback in
        // DS 9.4, so ask the preview server to forward a forcesave command to
        // the DS command service instead. The status-6 callback lands within
        // ~1s and the polling loop flips the bar to 已保存.
        setStatus('saving', '保存中…');
        fetch('/api/onlyoffice/force-save?file_id=' + encodeURIComponent(fileId),
              { method: 'POST' })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            if (data && data.error && data.error !== 4) {
              // error 4 = no changes to save; harmless.
              setStatus('error', '保存失败: ' + data.error);
            }
          })
          .catch(function (err) { setStatus('error', '保存失败: ' + err); });
      });
      setInterval(function () {
        fetch('/api/onlyoffice/status?file_id=' + encodeURIComponent(fileId))
          .then(function (r) { return r.json(); })
          .then(function (s) {
            if (!s) return;
            if (s.status === 'saved') setStatus('saved', '已保存 ' + (s.saved_at || ''));
            else if (s.status === 'saving') setStatus('saving', '保存中…');
            else if (s.status === 'error') setStatus('error', s.message || '保存失败');
          }).catch(function () {});
      }, 3000);
    })
    .catch(function (err) {
      setStatus('error', String(err && err.message ? err.message : err));
    });
})();
</script>
</body>
</html>
"""


def _onlyoffice_shell() -> str:
    """Fill the DS API script URL into the ONLYOFFICE shell template."""
    from tools.office_onlyoffice import ds_url
    return _ONLYOFFICE_SHELL.replace(
        "{DS_API_JS}", html.escape(ds_url() + "/web-apps/apps/api/documents/api.js"))


def _atomic_write(path: str, data: bytes) -> None:
    """Atomically replace *path* with *data* (write temp file then os.replace)."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".onlyoffice-tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:  # pragma: no cover - tmp already gone
            pass
        raise


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # Quieter logging for the preview server.
    def log_message(self, fmt, *args):  # pragma: no cover - logging noise
        logger.debug("[preview] " + fmt, *args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/editor"):
            # Self-contained fallback editor (crude but dependency-free).
            self._send_bytes(EDITOR_HTML.encode("utf-8"),
                             "text/html; charset=utf-8")
            return
        if path == "/onlyoffice":
            self._onlyoffice_page()
            return
        if path == "/api/onlyoffice/config":
            self._api_onlyoffice_config()
            return
        if path == "/api/onlyoffice/download":
            self._api_onlyoffice_download()
            return
        if path == "/api/onlyoffice/status":
            self._api_onlyoffice_status()
            return
        if path == "/api/office-selection":
            self._api_office_selection()
            return
        local_type = LOCAL_EDIT_PATHS.get(path)
        if local_type is not None:
            # Serve the SDK's real editor SPA at a local-edit whitelisted
            # pathname so isLocalFile() passes and the local editing engine
            # (wasm worker) activates instead of the read-only cloud view.
            self._proxy_passthrough(
                f"/static/{local_type}/pc.html",
                force_content_type="text/html; charset=utf-8",
            )
            return
        if path == "/api/health":
            self._proxy_get("/health")
            return
        if path.startswith("/static/") or path.startswith("/localapi/"):
            # SDK static assets (JS/CSS chunks) + local file API — must stay
            # same-origin with the SPA page, so proxy them.
            self._proxy_passthrough(path)
            return
        self._send_not_found()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/mcp":
            self._proxy_mcp()
            return
        if path == "/api/onlyoffice/save":
            self._api_onlyoffice_save()
            return
        if path == "/api/onlyoffice/force-save":
            self._api_onlyoffice_force_save()
            return
        if path.startswith("/localapi/") or path in ("/mcp", "/api/health"):
            # SDK local file API + raw MCP endpoint, same origin.
            self._proxy_passthrough(path, body=self._read_body())
            return
        self._send_not_found()

    # ------------------------------------------------------------------
    # Proxy helpers
    # ------------------------------------------------------------------
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(length) if length else b""

    def _sdk_port(self) -> int:
        """Resolve the SDK port, reusing a running instance if possible."""
        return sdk_manager.ensure_started()

    def _proxy_get(self, target_path: str):
        try:
            port = self._sdk_port()
        except Exception as e:  # pragma: no cover
            self._json_error(502, f"sdk not started: {e}")
            return
        url = f"http://127.0.0.1:{port}{target_path}"
        try:
            with _urlopen(url, timeout=5) as resp:
                data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self._json_error(e.code, e.read().decode("utf-8", "replace"))
        except Exception as e:  # pragma: no cover
            self._json_error(502, str(e))

    def _proxy_mcp(self):
        raw = self._read_body()
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json_error(400, "invalid JSON")
            return
        try:
            port = self._sdk_port()
        except Exception as e:  # pragma: no cover
            self._json_error(502, f"sdk not started: {e}")
            return
        url = f"http://127.0.0.1:{port}/mcp"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _urlopen(req, timeout=60) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self._json_error(e.code, e.read().decode("utf-8", "replace"))
        except Exception as e:  # pragma: no cover
            self._json_error(502, str(e))

    def _json_error(self, code: int, msg: str):
        body = json.dumps({"error": msg}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str):
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError,
                ConnectionResetError):  # pragma: no cover - client vanished
            logger.debug("client aborted while sending %d bytes", len(body))

    def _send_not_found(self):
        body = b"not found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _proxy_passthrough(self, path: str, body: bytes | None = None,
                           force_content_type: str | None = None):
        """Forward any SDK path verbatim (GET or POST) with CORS added."""
        try:
            port = self._sdk_port()
        except Exception as e:  # pragma: no cover
            self._json_error(502, f"sdk not started: {e}")
            return
        url = f"http://127.0.0.1:{port}{path}"
        try:
            if body is None:
                resp = _urlopen(url, timeout=30)
            else:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = _urlopen(req, timeout=60)
            with resp:
                data = resp.read()
            content_type = (force_content_type
                            or resp.headers.get("Content-Type")
                            or "application/octet-stream")
            self._send_bytes(data, content_type)
        except urllib.error.HTTPError as e:
            self._json_error(e.code, e.read().decode("utf-8", "replace"))
        except Exception as e:  # pragma: no cover
            self._json_error(502, str(e))

    # ------------------------------------------------------------------
    # ONLYOFFICE editor (remote DocumentServer)
    # ------------------------------------------------------------------
    def _onlyoffice_page(self):
        """GET /onlyoffice — the embed shell for the remote DS editor."""
        from tools.office_onlyoffice import is_enabled
        if not is_enabled():
            self._send_not_found()
            return
        self._send_bytes(_onlyoffice_shell().encode("utf-8"),
                         "text/html; charset=utf-8")

    def _api_office_selection(self):
        """GET /api/office-selection?file_path= — current sheet cell selection.

        Resolves the SDK editor for *file_path* and queries ``sheet_get_selection``
        so the renderer can anchor the AI-edit toolbar on a spreadsheet range in
        the editor_sdk sheet preview (the cross-origin iframe cannot be read
        directly). Returns ``{text, range, sheet_id}``; text is null when no
        range is selected or the editor is not open.
        """
        qs = parse_qs(urlparse(self.path).query)
        file_path = (qs.get("file_path") or [""])[0]
        if not file_path:
            self._json_error(400, "missing file_path")
            return

        file_id = None
        try:
            status = sdk_manager.get_editor_status()
            norm = os.path.normpath(file_path)
            for ed in status.get("open_editors", []):
                if ed.get("file_path") and os.path.normpath(ed["file_path"]) == norm:
                    file_id = ed.get("file_id")
                    break
        except Exception:
            file_id = None
        if not file_id:
            self._send_bytes(
                json.dumps({"text": None, "range": None, "sheet_id": None}).encode("utf-8"),
                "application/json")
            return

        try:
            from tools.office_mcp_client import mcp_client
            payload = mcp_client.call_json("sheet_get_selection", {"file_id": file_id})
        except Exception as exc:
            self._json_error(502, f"selection query failed: {exc}")
            return

        ranges = payload.get("ranges")
        if ranges is None:
            ranges = payload.get("range")
        if ranges is None:
            ranges = payload.get("selected_ranges")
        if isinstance(ranges, str):
            ranges = [ranges]
        range_str = ", ".join(str(r) for r in ranges) if ranges else ""
        text = payload.get("text") or range_str or None
        self._send_bytes(
            json.dumps({
                "text": text,
                "range": range_str or None,
                "sheet_id": payload.get("sheet_id"),
            }, ensure_ascii=False).encode("utf-8"),
            "application/json")

    def _api_onlyoffice_config(self):
        """GET /api/onlyoffice/config?file_id= — signed editor config."""
        from tools.office_onlyoffice import is_enabled, make_editor_config
        if not is_enabled():
            self._send_not_found()
            return
        qs = parse_qs(urlparse(self.path).query)
        file_id = (qs.get("file_id") or [""])[0]
        if not file_id:
            self._json_error(400, "missing file_id")
            return
        self._send_bytes(
            json.dumps(make_editor_config(file_id)).encode("utf-8"),
            "application/json")

    def _api_onlyoffice_download(self):
        """GET /onlyoffice/download?file_id=&token= — stream the file bytes.

        Called by the DocumentServer when it opens a document; authenticated by
        the self-contained signed download token so we do not depend on the DS
        forwarding an Authorization header.
        """
        from tools.office_onlyoffice import check_download_token, is_enabled, registry
        if not is_enabled():
            self._send_not_found()
            return
        qs = parse_qs(urlparse(self.path).query)
        file_id = (qs.get("file_id") or [""])[0]
        token = (qs.get("token") or [""])[0]
        if not file_id or not check_download_token(file_id, token):
            self._json_error(401, "unauthorized")
            return
        rec = registry.lookup(file_id)
        if not rec or not os.path.isfile(rec.file_path):
            self._json_error(404, "file not found")
            return
        ext = os.path.splitext(rec.file_path)[1].lower()
        content_type = _OFFICE_CONTENT_TYPES.get(
            ext, "application/octet-stream")
        try:
            with open(rec.file_path, "rb") as handle:
                self._send_bytes(handle.read(), content_type)
        except OSError as exc:  # pragma: no cover - disk error
            self._json_error(500, f"read failed: {exc}")

    def _api_onlyoffice_save(self):
        """POST /onlyoffice/save — DocumentServer save callback.

        The DS posts ``{status, url, key, ...}`` (authenticated by its JWT).
        For status 2 (normal save) / 6 (force save) we fetch the edited bytes
        from the DS-hosted ``url`` and atomically replace the on-disk file,
        then rotate the OnlyOffice key so the next open bypasses the DS cache.
        """
        from tools.office_onlyoffice import (
            check_callback_auth, is_enabled, registry,
        )
        if not is_enabled():
            self._send_not_found()
            return
        if not check_callback_auth(self.headers.get("Authorization", "")):
            self._json_error(401, "unauthorized")
            return
        try:
            payload = json.loads(self._read_body() or b"{}")
        except json.JSONDecodeError:
            self._json_error(400, "invalid JSON")
            return
        rec = registry.lookup_by_key(payload.get("key", ""))
        if rec and payload.get("status") in (2, 6) and payload.get("url"):
            try:
                registry.mark(rec.file_id, "saving")
                with _urlopen(payload["url"], timeout=60) as resp:
                    data = resp.read()
                _atomic_write(rec.file_path, data)
                registry.rotate_key(rec.file_id)
                registry.mark(rec.file_id, "saved",
                              saved_at=time.strftime("%H:%M:%S"))
            except Exception as exc:  # pragma: no cover - DS/disk error
                logger.warning("onlyoffice save failed for %s: %s",
                               rec.file_path, exc)
                registry.mark(rec.file_id, "error", f"保存失败: {exc}")
        elif rec and payload.get("status") in (3, 7):
            registry.mark(rec.file_id, "error",
                          f"DocumentServer 保存出错 (status {payload.get('status')})")
        # Always ack so the DS does not retry; errors are surfaced via /status.
        self._send_bytes(json.dumps({"error": 0}).encode("utf-8"),
                         "application/json")

    def _api_onlyoffice_force_save(self):
        """POST /api/onlyoffice/force-save?file_id= — flush the DS editor now.

        Forwards a ``forcesave`` command to the DS command service so the
        currently-open editor flushes to our save handler (a status-6 callback
        follows and writes the bytes to disk). This is the shell 保存 button's
        reliable path — the client-side ``mc:forceSave`` fires no callback.
        """
        from tools.office_onlyoffice import force_save, is_enabled
        if not is_enabled():
            self._send_not_found()
            return
        qs = parse_qs(urlparse(self.path).query)
        file_id = (qs.get("file_id") or [""])[0]
        if not file_id:
            self._json_error(400, "missing file_id")
            return
        try:
            result = force_save(file_id)
        except KeyError:
            self._json_error(404, "file_id not found")
            return
        except Exception as exc:  # pragma: no cover - DS unreachable
            logger.warning("onlyoffice force-save failed for %s: %s",
                           file_id, exc)
            self._json_error(502, f"force-save failed: {exc}")
            return
        self._send_bytes(json.dumps(result).encode("utf-8"),
                         "application/json")

    def _api_onlyoffice_status(self):
        """GET /api/onlyoffice/status?file_id= — last save state for the shell."""
        from tools.office_onlyoffice import is_enabled, registry
        if not is_enabled():
            self._send_not_found()
            return
        qs = parse_qs(urlparse(self.path).query)
        file_id = (qs.get("file_id") or [""])[0]
        rec = registry.lookup(file_id)
        if not rec:
            self._json_error(404, "file_id not found")
            return
        self._send_bytes(json.dumps({
            "status": rec.status,
            "message": rec.message,
            "saved_at": rec.saved_at,
        }).encode("utf-8"), "application/json")


class PreviewServer:
    """Single-port localhost server hosting the human editor + MCP proxy."""

    def __init__(self):
        self._lock = threading.Lock()
        self._http: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._port: Optional[int] = None

    @property
    def port(self) -> Optional[int]:
        return self._port

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("preview server not started")
        return f"http://127.0.0.1:{self._port}"

    def ensure_started(self, timeout: float = 5.0) -> int:
        """Start the proxy server (if needed) and return its port.

        When ONLYOFFICE is enabled the DocumentServer reaches this host over
        LAN for its download/save callbacks, so the server binds ``0.0.0.0``
        instead of loopback (a fixed ``HERMES_OFFICE_PREVIEW_PORT`` keeps the
        firewall rule to a single port). Otherwise it stays loopback-only.
        """
        with self._lock:
            if self._http is not None:
                return self._port  # type: ignore[return-value]
            import socket

            from tools.office_onlyoffice import is_enabled, preview_port

            bind_host = "0.0.0.0" if is_enabled() else "127.0.0.1"
            fixed = preview_port()
            if fixed is not None:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind((bind_host, fixed))
                except OSError as exc:
                    raise RuntimeError(
                        f"preview port {fixed} in use: {exc}") from exc
                self._port = fixed
            else:
                for port in range(PREVIEW_PORT_RANGE_START, PREVIEW_PORT_RANGE_END + 1):
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.bind((bind_host, port))
                    except OSError:
                        continue
                    self._port = port
                    break
                if self._port is None:
                    raise RuntimeError("No free port for preview server")
            self._http = ThreadingHTTPServer((bind_host, self._port), _Handler)
            self._http.daemon_threads = True
            self._thread = threading.Thread(
                target=self._http.serve_forever, daemon=True
            )
            self._thread.start()
            logger.info("Preview editor server started on %s:%d",
                        bind_host, self._port)
            return self._port

    def get_editor_url(self, file_id: str, doc_type: str,
                       file_path: str | None = None) -> str:
        """Return the URL the desktop renderer mounts in its preview iframe.

        Always the OnlyOffice embed shell (``/onlyoffice``), which drives the
        remote DocumentServer. Callers must only reach this when OnlyOffice is
        enabled (``office_preview_api._open_onlyoffice`` and the
        ``office_sdk_manager.get_preview_url`` sheet branch both gate on
        ``is_enabled()``). ``file_path`` is URL-encoded into the query so the
        editor can write back to the exact on-disk file.
        """
        self.ensure_started()
        editor = "/onlyoffice"
        url = (f"http://127.0.0.1:{self._port}{editor}"
               f"?file_id={quote(file_id)}&doc_type={quote(doc_type)}")
        if file_path:
            url += f"&file_path={quote(file_path)}"
        return url

    def get_local_edit_url(self, file_id: str, doc_type: str,
                           file_path: str | None = None) -> str:
        """Return the SDK real editor's local-edit URL for the preview iframe.

        Uses one of the SPA's local-edit whitelisted pathnames
        (``/doc/local_edit`` etc.) plus ``client=desktop_local`` — the client
        mode ``checkIfLocalEdit()`` treats as editable (``http_local`` /
        ``sdk_local`` are explicitly excluded). The wasm local editing engine
        only boots when ``isLocalFile()`` passes, so the pathname matters as
        much as the client param.
        """
        self.ensure_started()
        url = (f"http://127.0.0.1:{self._port}/{doc_type}/local_edit"
               f"?file_id={quote(file_id)}&local_edit=1&client=desktop_local")
        if file_path:
            url += f"&localFilePath={quote(file_path)}"
        return url

    def stop(self):
        with self._lock:
            if self._http is not None:
                self._http.shutdown()
                self._http.server_close()
                self._http = None
                self._port = None


# Singleton
preview_server = PreviewServer()
