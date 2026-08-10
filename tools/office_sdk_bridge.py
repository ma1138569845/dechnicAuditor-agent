#!/usr/bin/env python3
"""Shared editor_sdk pool helpers used by the agent tools and the desktop bridge.

Both ``tools.office_editor_tool`` (7 agent-facing tools) and
``tools.office_preview_api`` (the desktop preview endpoint) wait for editor_sdk
editors to be *actually* open, and both must resolve the ``file_id`` editor_sdk
assigns to streaming ``open_file`` calls. Those two helpers live here so the
logic does not drift between the callers.

The helpers take the MCP client / SDK manager they operate on as arguments, and
each caller passes its own module singleton via a thin wrapper.  That keeps unit
tests that patch ``sdk_manager`` / ``mcp_client`` on the caller module working
without this module having to know about their mocks.
"""

import json
import os
import time

# Cheap read probes used to confirm an editor is *actually* open before an edit.
# The pool may list a file_id before the underlying document/workbook/
# presentation has finished opening, so a probe is the reliable readiness check.
READY_PROBE = {
    "doc": "doc_get_outline",
    "sheet": "sheet_get_sheet_info",
    "slide": "slide_get_info",
}


def probe_open(text: str) -> bool:
    """Decide whether a probe payload means the editor is open.

    Most probes error until open, but ``slide_get_info`` (and others) return a
    success envelope with an ``is_open`` field while the presentation is still
    initializing.  Honour that field when present, otherwise fall back to the
    "no error" signal.
    """
    if "not open" in text or "No workbook" in text:
        return False
    try:
        data = json.loads(text)
    except Exception:
        return True
    stack = [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "is_open" in node:
                return bool(node["is_open"])
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return True


def wait_for_editor_ready(
    mcp_client, file_id: str, doc_type: str = "doc", timeout: float = 15.0
) -> bool:
    """Wait until editor_sdk can actually serve an edit on this editor.

    ``create_*`` / ``open_file`` register the editor asynchronously: the pool
    lists the file_id before the underlying document is open, so issuing an
    edit too early returns "document is not open" / "No workbook open".  Probe
    a cheap read until it reports open instead of trusting the pool entry.
    """
    probe = READY_PROBE.get(doc_type, "doc_get_outline")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = mcp_client.call(probe, {"file_id": file_id})
            text = (result.get("content") or [{}])[0].get("text", "")
            if probe_open(text):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def resolve_open_file_id(sdk_manager, file_path: str, timeout: float = 10.0) -> str:
    """Find the file_id editor_sdk assigned to an ``open_file`` editor.

    ``open_file`` is streaming: the response is a start message with no
    ``file_id``, and the editor registers asynchronously in the pool keyed by
    its file path.  Match on the normalized path and fall back to the path
    itself (which the SDK reports as the file_id for opened files).
    """
    target = os.path.normcase(os.path.normpath(file_path))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status = sdk_manager.get_editor_status()
            for ed in status.get("open_editors", []):
                p = os.path.normcase(os.path.normpath(ed.get("file_path", "")))
                if p == target:
                    return ed.get("file_id") or file_path
        except Exception:
            pass
        time.sleep(0.2)
    return file_path
