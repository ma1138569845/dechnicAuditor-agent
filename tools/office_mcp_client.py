#!/usr/bin/env python3
"""MCP JSON-RPC 2.0 client for editor_sdk.

Provides a synchronous client that communicates with editor_sdk's /mcp
endpoint.  Supports tools/list (enumerate available tools + schemas) and
tools/call (execute a tool).

Usage:
    from tools.office_mcp_client import mcp_client
    tools = mcp_client.list_tools()
    result = mcp_client.call("create_doc", {"file_path": "/abs/path.docx"})
"""

import json
import logging
import threading
import urllib.request
import urllib.error
from typing import Any, Optional

from tools.office_sdk_manager import sdk_manager

logger = logging.getLogger(__name__)


class MCPClient:
    """Synchronous JSON-RPC 2.0 client for editor_sdk."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tools_cache: Optional[list] = None
        self._id_counter = 0

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    def _post(self, payload: dict) -> dict:
        """Send a JSON-RPC request and return the response dict."""
        port = sdk_manager.ensure_started()
        url = f"http://127.0.0.1:{port}/mcp"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {e.code}: {body}") from e

    # -----------------------------------------------------------------
    # tools/list
    # -----------------------------------------------------------------
    def list_tools(self, force_refresh: bool = False) -> list:
        """Return the full list of available MCP tools.

        Results are cached after the first call unless *force_refresh*.
        """
        with self._lock:
            if self._tools_cache and not force_refresh:
                return self._tools_cache
            resp = self._post({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            })
            if "error" in resp:
                raise RuntimeError(f"tools/list error: {resp['error']}")
            self._tools_cache = resp.get("result", {}).get("tools", [])
            return self._tools_cache

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Return the input schema for a specific tool."""
        for t in self.list_tools():
            if t.get("name") == tool_name:
                return t.get("inputSchema")
        return None

    # -----------------------------------------------------------------
    # tools/call
    # -----------------------------------------------------------------
    def call(self, name: str, arguments: dict | None = None) -> dict:
        """Call an MCP tool and return the result.

        Args:
            name: Tool name (e.g. "create_doc", "doc_insert_text").
            arguments: Tool arguments dict.

        Returns:
            The full JSON-RPC response.  On success, the tool output is
            in ``result.content[0].text`` (a JSON string).  Extra fields
            like ``file_id`` are at the top level of ``result``.

        Raises:
            RuntimeError: If the tool returns an error.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments or {},
            },
        }
        resp = self._post(payload)
        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(
                f"Tool '{name}' error [{err.get('code')}]: {err.get('message')}"
            )
        return resp.get("result", {})

    def call_text(self, name: str, arguments: dict | None = None) -> str:
        """Call a tool and return just the text content.

        Convenience wrapper around ``call()`` that extracts the text
        field from the result content.
        """
        result = self.call(name, arguments)
        content = result.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        return ""

    def call_json(self, name: str, arguments: dict | None = None) -> Any:
        """Call a tool and parse the text content as JSON."""
        text = self.call_text(name, arguments)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    # -----------------------------------------------------------------
    # Tool grouping helpers
    # -----------------------------------------------------------------
    def list_tools_by_prefix(self) -> dict:
        """Return tools grouped by prefix (doc_, sheet_, slide_, etc.)."""
        groups = {}
        for t in self.list_tools():
            prefix = t["name"].split("_")[0]
            groups.setdefault(prefix, []).append(t["name"])
        return groups


# Singleton instance
mcp_client = MCPClient()
