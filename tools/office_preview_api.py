#!/usr/bin/env python3
"""HTTP-facing helpers that bridge the desktop preview pane to an Office engine.

The renderer's ``/api/office-preview/start`` endpoint calls
:func:`open_office_preview` to open a local Office file and get an iframe URL
it can mount. ``close_office_preview`` releases the editor on unmount. Both
return plain dict envelopes (no HTTP) so the web_server wrapper can keep the
existing HTTP-200 error-envelope convention.

Engine preference (per deployment):
  1. ONLYOFFICE DocumentServer (``HERMES_OFFICE_DS_URL`` set) -> remote DS editor.
  2. editor_sdk binary (``bin/editor_sdk.exe``) -> local SDK read-only cloud view.
  3. officecli binary -> local ``officecli watch`` server (tier-3 fallback).

This module does NOT register agent tools — it only serves the desktop UI. The
7 agent-facing tools live in :mod:`tools.office_editor_tool`.
"""

import json
import logging
import os
import urllib.request
import uuid

from tools.office_mcp_client import mcp_client
from tools.office_sdk_manager import _find_binary, sdk_manager
from tools.office_sdk_bridge import resolve_open_file_id, wait_for_editor_ready
from tools.office_preview_server import preview_server

logger = logging.getLogger(__name__)

# Error codes mirrored from the renderer's error mapping. Keep the shape
# ``{"error": code, "message": text}`` so the pane can surface friendly text.
CODE_SDK_NOT_FOUND = "OFFICE_SDK_NOT_FOUND"
CODE_SDK_START_FAILED = "OFFICE_SDK_START_FAILED"
CODE_PATH_OUTSIDE_SANDBOX = "PATH_OUTSIDE_SANDBOX"

_EXT_MAP = {
    ".doc": "doc", ".docx": "doc", ".dot": "doc", ".wps": "doc", ".wpt": "doc", ".docm": "doc",
    ".xls": "sheet", ".xlsx": "sheet", ".xlt": "sheet", ".csv": "sheet", ".tsv": "sheet", ".xlsm": "sheet",
    ".ppt": "slide", ".pptx": "slide", ".pps": "slide", ".pot": "slide", ".pptm": "slide",
}


def _doc_type_from_path(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return _EXT_MAP.get(ext, "doc")


def _existing_editor_for(file_path: str) -> dict | None:
    """Return the pool entry for *file_path* if it is already open, else None."""
    try:
        status = sdk_manager.get_editor_status()
    except Exception:
        return None
    norm = os.path.normpath(file_path)
    for ed in status.get("open_editors", []):
        if ed.get("file_path") and os.path.normpath(ed["file_path"]) == norm:
            return ed
    return None


def _localapi_open_uuid(file_path: str, doc_type: str) -> str:
    """Open *file_path* via ``POST /localapi/open`` and return the UUID file_id.

    editor_sdk keys its chunk conversion off the file_id: a UUID works, but the
    raw file path does not (the SDK builds ``<tmp>/doc/<port>/<file_id>`` and a
    drive-letter colon yields an invalid path -> conversion error 1070 -> empty
    editor). This helper exists so the desktop preview always uses a UUID.

    Raises on transport or envelope errors; the caller falls back to MCP.
    """
    port = sdk_manager.ensure_started()
    body = json.dumps({
        "file_path": file_path,
        "file_type": doc_type,
        "doc_type": doc_type,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/localapi/open",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    file_id = data.get("file_id")
    if not file_id:
        raise RuntimeError(f"/localapi/open returned no file_id: {data}")
    return file_id


def _open_onlyoffice(file_path: str) -> dict:
    """Open *file_path* through the remote DocumentServer (no SDK required).

    Registers the path in the OnlyOffice registry (reusing an already-open
    editor for the same path, mirroring the SDK pool) and returns the
    ``/onlyoffice`` embed-shell URL for the renderer's iframe.
    """
    from tools.office_onlyoffice import registry
    from tools.office_preview_server import preview_server

    if not os.path.exists(file_path):
        return {
            "error": CODE_SDK_START_FAILED,
            "message": f"File not found: {file_path}",
        }

    doc_type = _doc_type_from_path(file_path)
    existing = registry.find_by_path(file_path)
    if existing:
        file_id = existing.file_id
    else:
        file_id = str(uuid.uuid4())
        registry.register(file_id, file_path, doc_type)
    preview_server.ensure_started()
    url = preview_server.get_editor_url(file_id, doc_type, file_path)
    return {
        "success": True,
        "url": url,
        "file_id": file_id,
        "doc_type": doc_type,
        "engine": "onlyoffice",
        "preview_base_url": preview_server.base_url,
    }


def _open_officecli_fallback(file_path: str, workspace: str | None = None) -> dict:
    """Tier-3 fallback: open *file_path* via the officecli watch server.

    Reached only when ONLYOFFICE is disabled *and* the editor_sdk binary is
    missing. The officecli server renders the document at ``http://127.0.0.1:<port>/``
    which the renderer mounts in the same iframe as the SDK/DS URLs.
    """
    from tools.office_cli_tool import start_office_preview

    result = start_office_preview(file_path, workspace)
    if "url" in result:
        return {
            "success": True,
            "url": result["url"],
            "file_id": os.path.abspath(file_path),
            "doc_type": _doc_type_from_path(file_path),
            "engine": "officecli",
        }
    return {
        "error": CODE_SDK_NOT_FOUND,
        "message": "No Office preview engine available: editor_sdk and officecli are both missing.",
    }


def open_office_preview(file_path: str, workspace: str | None = None) -> dict:
    """Open an Office file and return an iframe preview URL.

    When ONLYOFFICE is enabled (``HERMES_OFFICE_DS_URL`` set), the file opens
    in the remote DocumentServer via the ``/onlyoffice`` embed shell — no
    editor_sdk binary is needed. Otherwise it opens in editor_sdk as before.

    Returns a dict envelope. On success:
        {"success": True, "url": "<iframe url>", "file_id": "...", "doc_type": "doc"}
    On failure (HTTP 200 envelope):
        {"error": code, "message": "..."}
    """
    if not os.path.isabs(file_path):
        return {
            "error": CODE_PATH_OUTSIDE_SANDBOX,
            "message": f"Only absolute paths are allowed: {file_path}",
        }

    from tools.office_onlyoffice import is_enabled
    if is_enabled():
        return _open_onlyoffice(file_path)

    if _find_binary() is None:
        return _open_officecli_fallback(file_path, workspace)

    if not os.path.exists(file_path):
        return {
            "error": CODE_SDK_START_FAILED,
            "message": f"File not found: {file_path}",
        }

    # Reuse an already-open editor for the same path so repeated clicks do not
    # pile up duplicate editors in the pool.
    existing = _existing_editor_for(file_path)
    if existing and existing.get("file_id"):
        file_id = existing["file_id"]
    else:
        doc_type = _doc_type_from_path(file_path)
        try:
            # Prefer /localapi/open: it returns a UUID file_id. Using the raw
            # file path as file_id makes the SDK derive an invalid Windows temp
            # path (drive-letter colon) and the docx conversion fails with
            # error 1070 — the editor then renders empty ("0 个字").
            uuid = _localapi_open_uuid(file_path, doc_type)
        except Exception as exc:
            uuid = None
            logger.warning("localapi/open failed for %s: %s", file_path, exc)
        if uuid:
            file_id = uuid
            if not wait_for_editor_ready(mcp_client, file_id, doc_type):
                logger.warning("editor %s not ready within timeout", file_id)
        else:
            # Fallback to MCP open_file (streaming: no file_id on the envelope;
            # the editor registers in the pool keyed by its file path).
            try:
                result = mcp_client.call("open_file", {"file_path": file_path, "file_type": doc_type})
            except Exception as exc:  # network / JSON-RPC error from the SDK
                logger.warning("open_file failed for %s: %s", file_path, exc)
                return {"error": CODE_SDK_START_FAILED, "message": str(exc)}
            file_id = result.get("file_id") or resolve_open_file_id(sdk_manager, file_path)
            if not file_id:
                return {
                    "error": CODE_SDK_START_FAILED,
                    "message": "editor_sdk did not return a file_id",
                }
            if not wait_for_editor_ready(mcp_client, file_id, doc_type):
                logger.warning("editor %s not ready within timeout", file_id)

    doc_type = _doc_type_from_path(file_path)
    # editor_sdk mode is read-only for the human: no file_path / editable arg,
    # so sheets route to the SDK read-only cloud view (not the Univer WYSIWYG).
    url = sdk_manager.get_preview_url(file_id, doc_type)
    preview_server.ensure_started()
    return {
        "success": True,
        "url": url,
        "file_id": file_id,
        "doc_type": doc_type,
        "engine": "editor_sdk",
        "preview_base_url": preview_server.base_url,
    }


def close_office_preview(file_path: str) -> dict:
    """Best-effort release of the editor for *file_path*.

    In OnlyOffice mode the local registry entry is dropped (the remote DS keeps
    its own server-side copy, so unsaved in-pane changes are still recoverable
    there). Otherwise the editor_sdk editor is released via MCP. Returns
    ``{"ok": True}`` even when nothing matched — stopping a preview is never
    fatal.
    """
    from tools.office_onlyoffice import is_enabled, registry
    if is_enabled():
        rec = registry.find_by_path(file_path)
        if rec:
            registry.close(rec.file_id)
        return {"ok": True}
    if _find_binary() is not None:
        try:
            entry = _existing_editor_for(file_path)
            if entry and entry.get("file_id"):
                mcp_client.call("close_file", {"file_id": entry["file_id"], "force": True})
        except Exception as exc:  # SDK unreachable / already closed
            logger.warning("close_office_preview failed for %s: %s", file_path, exc)
        return {"ok": True}
    # officecli session (tier-3 fallback engine)
    from tools.office_cli_tool import stop_office_preview
    return stop_office_preview(file_path)
