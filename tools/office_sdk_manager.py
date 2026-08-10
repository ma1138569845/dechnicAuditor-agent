#!/usr/bin/env python3
"""editor_sdk.exe lifecycle manager for Hermes.

Manages the local editor_sdk binary: process start/stop, port discovery,
health monitoring, and preview URL generation.

Usage (inside Hermes tool handlers):
    from tools.office_sdk_manager import sdk_manager
    port = sdk_manager.ensure_started()
    preview_url = sdk_manager.get_preview_url(file_id, "doc")

The binary is expected at:
    {HERMES_HOME}/office_sdk/bin/editor_sdk.exe   (Windows)
    {HERMES_HOME}/office_sdk/bin/editor_sdk       (macOS/Linux)
    {HERMES_HOME}/office_sdk/bin/icudt72l.dat     (all platforms)

If the binary is not found, the manager falls back to the repo-local ``bin/``
directory (search order below) so development works without a separate copy.
"""

import atexit
import logging
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_IS_WINDOWS = platform.system() == "Windows"
_IS_MACOS = platform.system() == "Darwin"

def _binary_name() -> str:
    return "editor_sdk.exe" if _IS_WINDOWS else "editor_sdk"

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def _hermes_home() -> Path:
    """Return the Hermes home directory."""
    # Try the standard env var first
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home)
    # Fall back to the known LocalAppData location
    if _IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
    return Path.home() / ".hermes"

def _find_binary() -> Optional[Path]:
    """Locate editor_sdk binary on disk.

    Search order:
      1. {HERMES_HOME}/office_sdk/bin/editor_sdk[.exe]
      2. WorkBuddy install (development fallback)
      3. Adjacent to this file (../bin/editor_sdk[.exe])
    """
    name = _binary_name()

    # 1. Hermes home
    hermes_bin = _hermes_home() / "office_sdk" / "bin" / name
    if hermes_bin.exists():
        return hermes_bin

    # 2. WorkBuddy fallback (dev convenience)
    if _IS_WINDOWS:
        wb_paths = [
            Path("D:/Program Files/WorkBuddy/resources/app.asar.unpacked"
                 "/node_modules/@tencent/tencent-docs-ai-engine/bin/win32-x64"),
            Path("C:/Program Files/WorkBuddy/resources/app.asar.unpacked"
                 "/node_modules/@tencent/tencent-docs-ai-engine/bin/win32-x64"),
        ]
    elif _IS_MACOS:
        wb_paths = [
            Path("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked"
                 "/node_modules/@tencent/tencent-docs-ai-engine/bin/darwin-arm64"),
            Path("/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked"
                 "/node_modules/@tencent/tencent-docs-ai-engine/bin/darwin-x64"),
        ]
    else:
        wb_paths = [
            Path.home() / ".local/share/WorkBuddy/resources/app.asar.unpacked"
            "/node_modules/@tencent/tencent-docs-ai-engine/bin/linux-x64",
        ]
    for p in wb_paths:
        candidate = p / name
        if candidate.exists():
            logger.info("Using editor_sdk from WorkBuddy install: %s", candidate)
            return candidate

    # 3. Adjacent to this file (repo root bin/)
    adjacent = Path(__file__).resolve().parent.parent / "bin" / name
    if adjacent.exists():
        return adjacent

    return None

def _find_icu_data(binary_path: Path) -> Optional[Path]:
    """Locate icudt72l.dat next to the binary."""
    icu = binary_path.parent / "icudt72l.dat"
    return icu if icu.exists() else None

# ---------------------------------------------------------------------------
# Port management
# ---------------------------------------------------------------------------
PORT_RANGE_START = 39099
PORT_RANGE_END = 39198  # 100 ports

def _try_port(port: int) -> bool:
    """Return True if the SDK responds on this port."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=1) as resp:
            return resp.status == 200
    except Exception:
        return False

def _find_running_instance() -> Optional[int]:
    """Scan the port range for an already-running editor_sdk."""
    for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
        if _try_port(port):
            return port
    return None

# ---------------------------------------------------------------------------
# SDK Manager (singleton)
# ---------------------------------------------------------------------------
class EditorSDKManager:
    """Manages a single editor_sdk.exe process for the Hermes session."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._binary_path: Optional[Path] = None
        self._log_dir: Optional[Path] = None
        self._started_by_us = False

    @property
    def port(self) -> Optional[int]:
        return self._port

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise RuntimeError("editor_sdk not started; call ensure_started() first")
        return f"http://127.0.0.1:{self._port}"

    def ensure_started(self, timeout: float = 15.0) -> int:
        """Start editor_sdk if not running; return the port number.

        If an instance is already running on some port in the range, reuse it.
        Otherwise launch a new process on the first free port.
        """
        with self._lock:
            # Fast path: already running (by us or someone else)
            if self._port and _try_port(self._port):
                return self._port

            # Check for an externally running instance
            existing = _find_running_instance()
            if existing is not None:
                self._port = existing
                self._started_by_us = False
                logger.info("Reusing existing editor_sdk on port %d", existing)
                return existing

            # Start a new process
            return self._start_new(timeout)

    def _start_new(self, timeout: float) -> int:
        binary = _find_binary()
        if binary is None:
            raise FileNotFoundError(
                "editor_sdk binary not found. Place it at "
                f"{_hermes_home() / 'office_sdk' / 'bin' / _binary_name()} "
                "or in the repo-local bin/ directory."
            )
        self._binary_path = binary

        # Log directory
        self._log_dir = _hermes_home() / "office_sdk" / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # Find a free port
        import socket
        for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                try:
                    s.bind(("127.0.0.1", port))
                except OSError:
                    continue  # port in use
                break
        else:
            raise RuntimeError(f"No free port in range {PORT_RANGE_START}-{PORT_RANGE_END}")

        # Build launch command
        cmd = [
            str(binary),
            "--port", str(port),
            "--log_dir", str(self._log_dir),
        ]

        # On Windows, set the working directory to the binary's folder
        # so it can find icudt72l.dat
        cwd = str(binary.parent)

        logger.info("Starting editor_sdk: %s (cwd=%s)", " ".join(cmd), cwd)
        self._process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            # On Windows, create without a console window
            creationflags=(subprocess.CREATE_NO_WINDOW if _IS_WINDOWS else 0),
        )
        self._port = port
        self._started_by_us = True

        # Wait for health check
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"editor_sdk exited with code {self._process.returncode}"
                )
            if _try_port(port):
                logger.info("editor_sdk started on port %d (PID %d)",
                            port, self._process.pid)
                return port
            time.sleep(0.3)

        # Timeout
        self.stop()
        raise TimeoutError(f"editor_sdk did not become healthy within {timeout}s")

    def stop(self):
        """Stop the editor_sdk process if we started it."""
        with self._lock:
            if self._process and self._started_by_us:
                try:
                    # Try graceful shutdown via the API
                    try:
                        req = urllib.request.Request(
                            f"http://127.0.0.1:{self._port}/mcp",
                            data=b'{"jsonrpc":"2.0","id":0,"method":"tools/call",'
                                  b'"params":{"name":"shutdown","arguments":{}}}',
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        urllib.request.urlopen(req, timeout=2)
                    except Exception:
                        pass
                    # Force kill if still alive
                    if self._process.poll() is None:
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                    logger.info("editor_sdk stopped (port %d)", self._port)
                except Exception as e:
                    logger.warning("Error stopping editor_sdk: %s", e)
                finally:
                    self._process = None
                    self._port = None
                    self._started_by_us = False

    def get_preview_url(self, file_id: str, doc_type: str, editable: bool = True,
                        file_path: str | None = None) -> str:
        """Build the preview URL for an open document.

        Args:
            file_id: The file_id returned by create_*/open_file.
            doc_type: "doc", "sheet", or "slide".
            editable: If True, the preview is editable (local_edit=1).
            file_path: Optional absolute path of the local file.

        Routing:
          * ``sheet`` + ``file_path`` + OnlyOffice enabled -> the
            ``/onlyoffice`` embed shell (``tools.office_preview_server``
            ``get_editor_url``), which drives the remote DocumentServer so the
            on-disk xlsx is edited WYSIWYG and saved back.
          * anything else -> the SDK's ``pc.html`` read-only cloud view. The
            SPA's editable *local* mode cannot run standalone (it needs a
            whitelisted pathname + WorkBuddy's host bridge), so previews are
            read-only here and editing happens via AI (MCP) tools.

        Note:
            file_id must be a UUID-like id (e.g. from ``/localapi/open``);
            using the raw file path as file_id makes the SDK derive an invalid
            Windows temp path (colon in the drive letter) and the docx
            conversion fails with code 1070, leaving an empty editor.
        """
        port = self.ensure_started()
        if doc_type == "sheet" and file_path:
            try:
                from tools.office_onlyoffice import is_enabled
                if is_enabled():
                    from tools.office_preview_server import preview_server
                    return preview_server.get_editor_url(
                        file_id, doc_type, file_path)
            except Exception as exc:
                logger.warning("OnlyOffice editor unavailable (%s); "
                               "falling back to SDK SPA", exc)
        url = f"http://127.0.0.1:{port}/static/{doc_type}/pc.html?file_id={file_id}"
        return url

    def health_check(self) -> bool:
        """Return True if the SDK is healthy."""
        if not self._port:
            return False
        return _try_port(self._port)

    def get_editor_status(self) -> dict:
        """Return the editor pool status."""
        import json
        port = self.ensure_started()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/localapi/editor/status"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}


# Singleton instance
sdk_manager = EditorSDKManager()

# Clean up on exit
atexit.register(sdk_manager.stop)
