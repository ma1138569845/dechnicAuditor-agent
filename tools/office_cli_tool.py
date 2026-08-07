"""OfficeCLI preview server lifecycle manager and command runner.

Spawns a local `officecli` HTTP server for a given Office file and hands the
renderer a localhost URL to load in an Electron webview. The server is killed
when the preview tab is closed, matching AionUi's `officecli watch` lifecycle.

Configuration (environment variables):

    OFFICE_CLI_COMMAND
        Absolute or PATH-resolved command for the officecli binary.
        Default: "officecli"

    OFFICE_CLI_WATCH_TEMPLATE
        Shell command template used to start the watch server.
        Tokens: {office_cli}, {file_path}, {port}, {workspace}
        Default: "{office_cli} watch {file_path} --port {port}"

    OFFICE_CLI_START_TIMEOUT_SECONDS
        How long to wait for the server's listen port to become ready.
        Default: 30

    OFFICE_CLI_COMMAND_TIMEOUT_SECONDS
        Per-command timeout for `run_office_cli_command`.
        Default: 120

    OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES
        Maximum captured stdout/stderr bytes per command. Output beyond this
        is truncated and flagged in the result envelope.
        Default: 1048576 (1 MiB)

The module exposes three optional agent tools:
- `office_preview_start` / `office_preview_stop` (desktop-only): open/close
  Office previews on demand inside the Hermes desktop app.
- `office_cli_command` (all environments): run a single officecli command to
  create, inspect, or edit an Office document with structured output.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_OFFICE_CLI_COMMAND = os.environ.get("OFFICE_CLI_COMMAND", "officecli").strip() or "officecli"
_OFFICE_CLI_WATCH_TEMPLATE = os.environ.get(
    "OFFICE_CLI_WATCH_TEMPLATE",
    "{office_cli} watch {file_path} --port {port}",
).strip()
_OFFICE_CLI_START_TIMEOUT_SECONDS = max(5.0, float(os.environ.get("OFFICE_CLI_START_TIMEOUT_SECONDS", "30")))
_OFFICE_CLI_COMMAND_TIMEOUT_SECONDS = max(5.0, float(os.environ.get("OFFICE_CLI_COMMAND_TIMEOUT_SECONDS", "120")))
_OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES = max(
    1024,
    int(os.environ.get("OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES", str(1024 * 1024))),
)


# In-memory sessions keyed by the local file path they are serving.
_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public error codes (kept in sync with AionUi's renderer expectations)
# ---------------------------------------------------------------------------


class OfficePreviewError:
    NOT_FOUND = "OFFICECLI_NOT_FOUND"
    PORT_TIMEOUT = "OFFICECLI_PORT_TIMEOUT"
    START_FAILED = "OFFICECLI_START_FAILED"
    PATH_OUTSIDE_SANDBOX = "PATH_OUTSIDE_SANDBOX"
    INVALID_COMMAND = "OFFICECLI_INVALID_COMMAND"
    COMMAND_FAILED = "OFFICECLI_COMMAND_FAILED"
    COMMAND_TIMEOUT = "OFFICECLI_COMMAND_TIMEOUT"



# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Return an unused TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _is_port_ready(port: int, timeout: float = 0.5) -> bool:
    """Return True when 127.0.0.1:port accepts a TCP connection."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_command(file_path: str, port: int, workspace: str | None = None) -> list[str]:
    """Build the argv list from the configured watch template."""
    template = _OFFICE_CLI_WATCH_TEMPLATE
    if not template:
        raise RuntimeError("OFFICE_CLI_WATCH_TEMPLATE is empty")

    rendered = template.format(
        office_cli=_OFFICE_CLI_COMMAND,
        file_path=file_path,
        port=port,
        workspace=workspace or "",
    )
    return shlex.split(rendered)


def _check_sandbox(file_path: str) -> bool:
    """Placeholder sandbox check: reject paths outside the workspace if desired.

    Currently permits any absolute path. Expand here if the project needs to
    restrict previews to a configured workspace root.
    """
    return Path(file_path).is_absolute()


def _resolve_binary_name() -> str:
    """Return the basename of the configured officecli command."""
    return Path(_OFFICE_CLI_COMMAND).name


def _safe_shlex_split(command: str) -> list[str]:
    """Split a command string while preserving Windows backslash paths.

    ``shlex.split`` in POSIX mode (the default) treats backslashes as escape
    characters, which corrupts Windows paths like ``C:\\Users\\...`` into
    ``C:Users...``. Using ``posix=False`` preserves backslashes but keeps
    surrounding quotes in the tokens, so we strip matched surrounding quotes
    manually afterwards.
    """
    try:
        raw_tokens = shlex.split(command, posix=False)
    except ValueError:
        return []

    tokens: list[str] = []
    for token in raw_tokens:
        # Strip a single pair of matched surrounding quotes (single or double).
        # Inner quotes are left untouched. This mirrors how a POSIX shell would
        # hand the unquoted value to the process when subprocess.run receives a
        # list (no shell interpretation happens at exec time).
        if len(token) >= 2 and token[0] in ('"', "'") and token[-1] == token[0]:
            token = token[1:-1]
        tokens.append(token)
    return tokens


def _extract_command_file_paths(command: str) -> list[str]:
    """Best-effort extraction of absolute file paths from an officecli command.

    officecli commands typically place the target file as the second argument
    (e.g. ``officecli set report.docx ...``). This helper pulls out any token
    that looks like an absolute path so it can be sandbox-checked in addition
    to the explicitly supplied ``file_path``.
    """
    tokens = _safe_shlex_split(command)
    if not tokens:
        return []

    paths: list[str] = []
    for token in tokens[1:]:  # skip the leading "officecli" token
        # Stop at common subcommand-only flags/options that are not files.
        if token.startswith("-"):
            continue
        if Path(token).is_absolute():
            paths.append(token)
    return paths


def _parse_json_output(stdout: str) -> Any | None:
    """Attempt to parse the last JSON object/array in stdout."""
    text = stdout.strip()
    if not text:
        return None
    # Some officecli commands emit multiple JSON documents; try the last line
    # that looks like JSON first, then fall back to the whole stdout.
    for candidate in reversed(text.splitlines()):
        candidate = candidate.strip()
        if candidate.startswith(("{", "[")):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _truncate_output(text: str, max_bytes: int) -> tuple[str, bool]:
    """Truncate text to at most ``max_bytes`` UTF-8 bytes.

    Returns the (possibly truncated) text and a flag indicating whether
    truncation happened. Truncation preserves UTF-8 boundaries by re-encoding
    the truncated bytes and replacing any trailing invalid sequence.
    """
    if not text:
        return text, False
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="replace")
    marker = f"\n... [output truncated at {max_bytes} bytes] ..."
    return truncated + marker, True



# ---------------------------------------------------------------------------
# Public lifecycle API
# ---------------------------------------------------------------------------


def start_office_preview(file_path: str, workspace: str | None = None) -> dict[str, Any]:
    """Start an officecli watch server for `file_path` and return its URL.

    Returns one of:
        {"url": "http://127.0.0.1:<port>/"}
        {"error": "OFFICECLI_*", "message": "..."}
    """
    file_path = os.path.abspath(file_path)

    if not _check_sandbox(file_path):
        return {
            "error": OfficePreviewError.PATH_OUTSIDE_SANDBOX,
            "message": f"File path is outside the allowed sandbox: {file_path}",
        }

    if not Path(file_path).exists():
        return {
            "error": OfficePreviewError.START_FAILED,
            "message": f"File not found: {file_path}",
        }

    # If a session already exists for this file, return its URL.
    with _sessions_lock:
        existing = _sessions.get(file_path)
        if existing is not None and existing["process"].poll() is None:
            return {"url": existing["url"]}

    # Make sure the binary is reachable before allocating resources.
    resolved_binary = shutil.which(_OFFICE_CLI_COMMAND)
    if resolved_binary is None:
        return {
            "error": OfficePreviewError.NOT_FOUND,
            "message": (
                f"officecli not found: {_OFFICE_CLI_COMMAND}. "
                "Set OFFICE_CLI_COMMAND to the binary path or install officecli."
            ),
        }

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}/"

    try:
        argv = _resolve_command(file_path, port, workspace)
    except Exception as exc:
        logger.exception("Failed to build officecli command for %s", file_path)
        return {
            "error": OfficePreviewError.START_FAILED,
            "message": f"Invalid OFFICE_CLI_WATCH_TEMPLATE: {exc}",
        }

    logger.info("Starting officecli preview: %s", " ".join(shlex.quote(a) for a in argv))

    try:
        # Detach on Windows so killing the subprocess tree works cleanly.
        kwargs: dict[str, Any] = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

        process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
    except Exception as exc:
        logger.exception("Failed to start officecli for %s", file_path)
        return {
            "error": OfficePreviewError.START_FAILED,
            "message": f"Failed to start officecli: {exc}",
        }

    # Wait for the HTTP server to be ready.
    deadline = time.monotonic() + _OFFICE_CLI_START_TIMEOUT_SECONDS
    ready = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if _is_port_ready(port):
            ready = True
            break
        time.sleep(0.2)

    if not ready:
        _kill_session(process)
        stdout = _drain_pipe(process.stdout)
        logger.error("officecli failed to listen on port %d. stdout:\n%s", port, stdout)
        if process.poll() is not None:
            return {
                "error": OfficePreviewError.START_FAILED,
                "message": f"officecli exited early. stdout:\n{stdout}",
            }
        return {
            "error": OfficePreviewError.PORT_TIMEOUT,
            "message": f"officecli did not become ready on port {port} within {_OFFICE_CLI_START_TIMEOUT_SECONDS}s",
        }

    with _sessions_lock:
        # If another thread started the same file in parallel, prefer the earlier
        # session and clean ours up.
        earlier = _sessions.get(file_path)
        if earlier is not None and earlier["process"].poll() is None:
            _kill_session(process)
            return {"url": earlier["url"]}

        _sessions[file_path] = {
            "file_path": file_path,
            "port": port,
            "process": process,
            "url": url,
            "workspace": workspace,
        }

    return {"url": url}


def stop_office_preview(file_path: str) -> dict[str, Any]:
    """Stop the officecli watch server for `file_path`.

    Returns {"ok": True} whether or not a session existed.
    """
    file_path = os.path.abspath(file_path)

    with _sessions_lock:
        session = _sessions.pop(file_path, None)

    if session is None:
        return {"ok": True}

    process = session["process"]
    _kill_session(process)
    logger.info("Stopped officecli preview for %s", file_path)
    return {"ok": True}


# ---------------------------------------------------------------------------
# OfficeCLI command execution API
# ---------------------------------------------------------------------------


def run_office_cli_command(
    command: str,
    file_path: str | None = None,
    workspace: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Run a single officecli command and return structured output.

    The ``command`` string must start with the configured officecli binary name
    (default ``officecli``). Arbitrary shell commands are rejected to keep this
    tool scoped to Office document editing.

    Args:
        command: Full officecli command, e.g. ``officecli set report.docx ...``.
        file_path: Optional absolute path to the target file for sandbox checks.
        workspace: Optional workspace/root directory context.
        timeout: Per-command timeout in seconds (default 120).

    Returns:
        Structured result with ``success``, ``stdout``, ``stderr``,
        ``exit_code``, optional ``error`` code, and parsed ``json_output``.
    """
    if not command or not command.strip():
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.INVALID_COMMAND,
            "message": "command is required",
        }

    command = command.strip()

    # Validate that the command targets officecli only.
    tokens = _safe_shlex_split(command)
    if not tokens:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.INVALID_COMMAND,
            "message": "command is empty",
        }

    # Accept any invocation whose first token resolves to the configured
    # officecli binary: bare "officecli", "./officecli", "officecli.exe",
    # or an absolute path like "C:\tools\officecli.exe".
    binary_name = _resolve_binary_name()
    binary_stem = Path(binary_name).stem
    first_token = tokens[0]
    first_name = Path(first_token).name
    first_stem = Path(first_name).stem
    if first_token != binary_name and first_name != binary_name and first_stem != binary_stem:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.INVALID_COMMAND,
            "message": f"Command must start with '{binary_name}', got: {first_token}",
        }

    # Resolve the binary on PATH.
    resolved_binary = shutil.which(_OFFICE_CLI_COMMAND)
    if resolved_binary is None:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.NOT_FOUND,
            "message": (
                f"officecli not found: {_OFFICE_CLI_COMMAND}. "
                "Set OFFICE_CLI_COMMAND to the binary path or install officecli."
            ),
        }

    # Sandbox checks: explicit file_path plus any absolute paths found in args.
    paths_to_check: list[str] = []
    if file_path:
        paths_to_check.append(os.path.abspath(file_path))
    paths_to_check.extend(_extract_command_file_paths(command))

    for path in paths_to_check:
        if not _check_sandbox(path):
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "error": OfficePreviewError.PATH_OUTSIDE_SANDBOX,
                "message": f"File path is outside the allowed sandbox: {path}",
            }

    # Validate caller-supplied timeout. Negative or zero values would make
    # subprocess.run return immediately, so reject them explicitly.
    if timeout is not None and timeout <= 0:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.INVALID_COMMAND,
            "message": f"timeout must be a positive number of seconds, got: {timeout}",
        }

    effective_timeout = timeout if timeout is not None else _OFFICE_CLI_COMMAND_TIMEOUT_SECONDS

    # Use the resolved binary path so the subprocess honors OFFICE_CLI_COMMAND
    # even when the tokens[0] from the command string is just "officecli".
    argv = list(tokens)
    argv[0] = resolved_binary

    logger.info("Running officecli command: %s", command)

    try:
        result = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=effective_timeout,
            cwd=workspace or None,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        stdout, _ = _truncate_output(stdout, _OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES)
        stderr, _ = _truncate_output(stderr, _OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES)
        return {
            "success": False,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": -1,
            "error": OfficePreviewError.COMMAND_TIMEOUT,
            "message": f"officecli command timed out after {effective_timeout}s",
        }
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "error": OfficePreviewError.COMMAND_FAILED,
            "message": f"Failed to run officecli command: {exc}",
        }

    # Bound captured output so a runaway command cannot exhaust memory.
    stdout_text, stdout_truncated = _truncate_output(result.stdout, _OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES)
    stderr_text, stderr_truncated = _truncate_output(result.stderr, _OFFICE_CLI_COMMAND_MAX_OUTPUT_BYTES)
    json_output = _parse_json_output(stdout_text)

    result_envelope: dict[str, Any] = {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "exit_code": result.returncode,
    }
    if stdout_truncated or stderr_truncated:
        result_envelope["output_truncated"] = True

    if result.returncode != 0:
        return {
            "success": False,
            **result_envelope,
            "error": OfficePreviewError.COMMAND_FAILED,
            "message": stderr_text or f"officecli exited with code {result.returncode}",
            "json_output": json_output,
        }

    return {
        "success": True,
        **result_envelope,
        "json_output": json_output,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _kill_session(process: subprocess.Popen) -> None:
    """Kill a subprocess and its children, defensive against already-dead processes."""
    try:
        if process.poll() is None:
            if os.name == "nt":
                process.terminate()
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    except Exception:
        logger.exception("Error while killing officecli process")


def _drain_pipe(pipe) -> str:
    """Best-effort drain of the process stdout pipe after a failure."""
    if pipe is None:
        return ""
    try:
        # Non-blocking read is not worth the complexity; just close the pipe.
        pipe.close()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Agent tool bindings (desktop-only)
# ---------------------------------------------------------------------------


def _check_desktop() -> bool:
    """Only expose these tools when running inside the Hermes desktop gateway."""
    from utils import env_var_enabled

    return env_var_enabled("HERMES_DESKTOP")


_START_OFFICE_PREVIEW_SCHEMA = {
    "name": "office_preview_start",
    "description": (
        "Start a local officecli preview server for a Word/Excel/PowerPoint file "
        "and return a localhost URL the desktop preview pane can load."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the local .docx, .xlsx, or .pptx file.",
            },
            "workspace": {
                "type": "string",
                "description": "Optional workspace/root directory context.",
            },
        },
        "required": ["file_path"],
    },
}

_STOP_OFFICE_PREVIEW_SCHEMA = {
    "name": "office_preview_stop",
    "description": (
        "Stop the officecli preview server previously started for a file. "
        "Call this when the preview tab is closed to avoid leaking processes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file whose preview server should stop.",
            },
        },
        "required": ["file_path"],
    },
}


def _handle_office_preview_start(args: dict, **kwargs) -> str:
    file_path = args.get("file_path", "").strip()
    workspace = args.get("workspace", "").strip() or None

    if not file_path:
        return tool_error("file_path is required")

    try:
        result = start_office_preview(file_path, workspace)
    except Exception as exc:
        logger.exception("office_preview_start failed: %s", file_path)
        return tool_error(f"Failed to start office preview: {exc}")

    if "error" in result:
        return tool_error(result.get("message", result["error"]), **result)

    return tool_result(result)


def _handle_office_preview_stop(args: dict, **kwargs) -> str:
    file_path = args.get("file_path", "").strip()

    if not file_path:
        return tool_error("file_path is required")

    try:
        result = stop_office_preview(file_path)
    except Exception as exc:
        logger.exception("office_preview_stop failed: %s", file_path)
        return tool_error(f"Failed to stop office preview: {exc}")

    return tool_result(result)


_OFFICE_CLI_COMMAND_SCHEMA = {
    "name": "office_cli_command",
    "description": (
        "Run a single officecli command to create, inspect, or edit an Office "
        "document (.docx, .xlsx, .pptx). The command string must start with "
        "'officecli'. Returns structured stdout, stderr, exit_code, and parsed "
        "JSON output if available. Prefer this over the generic terminal tool "
        "for all Office document operations."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "Complete officecli command starting with 'officecli', e.g. "
                    "\"officecli set report.docx '/body/p[1]' --prop text=Hello\". "
                    "Only officecli commands are allowed."
                ),
            },
            "file_path": {
                "type": "string",
                "description": "Optional absolute path to the target Office file for sandbox checks.",
            },
            "workspace": {
                "type": "string",
                "description": "Optional working directory for the command.",
            },
            "timeout": {
                "type": "number",
                "description": "Optional per-command timeout in seconds (default 120).",
            },
        },
        "required": ["command"],
    },
}


def _handle_office_cli_command(args: dict, **kwargs) -> str:
    command = args.get("command", "").strip()
    file_path = args.get("file_path", "").strip() or None
    workspace = args.get("workspace", "").strip() or None
    timeout = args.get("timeout")

    if not command:
        return tool_error("command is required")

    if timeout is not None:
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            return tool_error("timeout must be a number")

    try:
        result = run_office_cli_command(command, file_path, workspace, timeout)
    except Exception as exc:
        logger.exception("office_cli_command failed: %s", command)
        return tool_error(f"Failed to run officecli command: {exc}")

    if not result.get("success"):
        return tool_error(result.get("message", "officecli command failed"), **result)

    return tool_result(result)


registry.register(
    name="office_preview_start",
    toolset="hermes-office",
    schema=_START_OFFICE_PREVIEW_SCHEMA,
    handler=_handle_office_preview_start,
    check_fn=_check_desktop,
    description="Start an officecli preview server for a local Office file",
    emoji="📄",
)

registry.register(
    name="office_preview_stop",
    toolset="hermes-office",
    schema=_STOP_OFFICE_PREVIEW_SCHEMA,
    handler=_handle_office_preview_stop,
    check_fn=_check_desktop,
    description="Stop the officecli preview server for a local Office file",
    emoji="🛑",
)

registry.register(
    name="office_cli_command",
    toolset="hermes-office",
    schema=_OFFICE_CLI_COMMAND_SCHEMA,
    handler=_handle_office_cli_command,
    description="Run an officecli command to create, inspect, or edit an Office document",
    emoji="🛠️",
)
