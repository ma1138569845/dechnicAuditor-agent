"""Feishu Office Tool -- upload a local Office file to Feishu/Lark for online
editing and export the edited cloud document back to the local file.

Only ``.docx`` and ``.xlsx`` are supported. Feishu import/export APIs do not
support ``.pptx``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from tools.registry import registry, tool_error, tool_result

logger = logging.getLogger(__name__)

# Thread-local storage for the lark client injected by feishu_comment handler.
_local = threading.local()

# ---------------------------------------------------------------------------
# Public helpers used by this module and by the desktop HTTP API.
# ---------------------------------------------------------------------------


def set_client(client):
    """Store a lark client for the current thread (called by feishu_comment)."""
    _local.client = client


def get_client():
    """Return a lark client for the current thread, or None."""
    return getattr(_local, "client", None)


# ---------------------------------------------------------------------------
# Constants and file-system helpers
# ---------------------------------------------------------------------------

SUPPORTED_OFFICE_EXTENSIONS = frozenset({".docx", ".xlsx"})

# Feishu document type used by the import_tasks endpoint.
DOCX_IMPORT_TYPE = "docx"
XLSX_IMPORT_TYPE = "sheet"

_IMPORT_POLL_INTERVAL_SECONDS = 2
_IMPORT_POLL_MAX_ATTEMPTS = 60
_EXPORT_POLL_INTERVAL_SECONDS = 2
_EXPORT_POLL_MAX_ATTEMPTS = 60


def _hermes_state_dir() -> Path:
    """Return the persistent state directory under the user's home.

    Mirrors the location used by hermes_state.py for session state.
    """
    home = Path.home()
    state_dir = home / ".hermes"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _office_map_path() -> Path:
    return _hermes_state_dir() / "feishu_office_map.json"


def load_office_map() -> dict[str, dict[str, str]]:
    """Load the local-path -> Feishu cloud document mapping."""
    path = _office_map_path()

    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


def save_office_map(mapping: dict[str, dict[str, str]]) -> None:
    """Persist the local-path -> Feishu cloud document mapping."""
    path = _office_map_path()

    try:
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to persist Feishu office map: %s", exc)


def get_office_mapping(local_path: str) -> dict[str, str] | None:
    """Look up an existing Feishu cloud document for a local file path."""
    mapping = load_office_map()

    return mapping.get(local_path)


def set_office_mapping(local_path: str, token: str, doc_type: str) -> None:
    """Record the Feishu cloud document token/type for a local file path."""
    mapping = load_office_map()
    mapping[local_path] = {"doc_type": doc_type, "token": token}
    save_office_map(mapping)


def clear_office_mapping(local_path: str) -> None:
    """Remove a local-path mapping (e.g. after the file is deleted)."""
    mapping = load_office_map()

    if local_path in mapping:
        del mapping[local_path]
        save_office_map(mapping)


# ---------------------------------------------------------------------------
# Feishu API helpers (low-level)
# ---------------------------------------------------------------------------


def _check_feishu():
    import importlib.util

    try:
        return importlib.util.find_spec("lark_oapi") is not None
    except (ImportError, ValueError):
        return False


def _require_client():
    client = get_client()

    if client is not None:
        return client

    # Desktop / generic contexts don't run inside the Feishu comment event
    # handler, so no client is injected. Build one from environment credentials
    # when FEISHU_APP_ID and FEISHU_APP_SECRET are configured.
    return _build_client_from_env()


def _build_client_from_env():
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")

    if not app_id or not app_secret:
        raise RuntimeError(
            "Feishu client not available: set FEISHU_APP_ID and FEISHU_APP_SECRET, "
            "or invoke from a Feishu bot context."
        )

    try:
        import lark_oapi as lark
    except ImportError as exc:
        raise RuntimeError("lark_oapi not installed") from exc

    # Lark/Feishu Client.builder().domain() expects a full https:// host, not a
    # short domain name. Default to the Feishu China endpoint; override with a
    # full URL (e.g. https://open.larksuite.com) via FEISHU_DOMAIN if needed.
    domain = os.environ.get("FEISHU_DOMAIN", "https://open.feishu.cn")

    if domain in ("feishu", "larksuite"):
        domain = f"https://open.{domain}.cn"

    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .domain(domain)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )


def _require_lark_imports() -> tuple[Any, Any, Any]:
    try:
        from lark_oapi import AccessTokenType
        from lark_oapi.core.enum import HttpMethod
        from lark_oapi.core.model.base_request import BaseRequest
    except ImportError as exc:
        raise RuntimeError("lark_oapi not installed") from exc

    return AccessTokenType, HttpMethod, BaseRequest


def _do_request(client, method: str, uri: str, paths=None, queries=None, body=None):
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()

    builder = (
        BaseRequest.builder()
        .http_method(getattr(HttpMethod, method))
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
    )

    if paths:
        builder = builder.paths(paths)

    if queries:
        builder = builder.queries(queries)

    if body:
        builder = builder.body(body)

    return client.request(builder.build())


def _get_response_body(response) -> dict:
    raw = getattr(response, "raw", None)

    if raw and hasattr(raw, "content"):
        try:
            return json.loads(raw.content)
        except json.JSONDecodeError:
            pass

    data = getattr(response, "data", None)

    if isinstance(data, dict):
        return data

    return {}


def _api_error_message(response) -> str:
    code = getattr(response, "code", None)
    msg = getattr(response, "msg", "unknown error")
    status = getattr(response, "status_code", None)
    raw = getattr(response, "raw", None)
    raw_text = ""

    if raw and hasattr(raw, "content"):
        try:
            raw_text = raw.content.decode("utf-8", errors="replace")[:500]
        except Exception:
            raw_text = str(raw.content)[:500]

    return f"status={status} code={code} msg={msg} raw={raw_text}"


# ---------------------------------------------------------------------------
# Upload -> Import -> Cloud document
# ---------------------------------------------------------------------------


def _read_file_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def _get_tenant_access_token(client) -> str:
    """Return a tenant_access_token for the client's app credentials.

    The lark client caches this internally; reach through its public config to
    the token manager so we reuse the cache rather than minting a fresh token.
    """
    config = client.config

    try:
        from lark_oapi.core.token.manager import TokenManager
    except ImportError as exc:
        raise RuntimeError("lark_oapi not installed") from exc

    return TokenManager.get_self_tenant_token(config)


def _post_multipart_upload(
    *,
    url: str,
    token: str,
    file_name: str,
    file_content: bytes,
    file_mime_type: str,
    form_fields: dict,
    timeout: float = 30,
) -> dict:
    """POST a multipart/form-data upload to Feishu and return the parsed JSON body.

    Isolated so tests can stub the network call. Uses ``requests`` directly
    because ``lark_oapi``'s synchronous transport ignores ``BaseRequest.files``.
    The file part includes an explicit MIME type because Feishu rejects uploads
    with ``mime: no media type`` when the content-type is omitted.
    """
    import requests  # local import keeps the module importable without it

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        url,
        headers=headers,
        data=form_fields,
        files={"file": (file_name, file_content, file_mime_type)},
        timeout=timeout,
    )

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Upload failed: non-JSON response (status={response.status_code}): {response.text[:300]}"
        ) from exc


def _get_root_folder_token(client) -> str:
    """Return the app's root cloud-space folder token.

    ``upload_all`` with ``parent_type=ccm_import_open`` sometimes returns
    1061004 forbidden because the app has no writable folder context. Uploading
    into the root folder (via its token) is the reliable path. The root token is
    fetched from ``/open-apis/drive/explorer/v2/root_folder/meta``.
    """
    import requests  # local import keeps the module importable without it

    config = client.config
    domain = config.domain.rstrip("/")
    url = f"{domain}/open-apis/drive/explorer/v2/root_folder/meta"
    token = _get_tenant_access_token(client)

    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=config.timeout or 30)

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Root folder meta failed: non-JSON response (status={response.status_code}): {response.text[:300]}"
        ) from exc

    code = body.get("code")
    if code != 0:
        raise RuntimeError(f"Root folder meta failed: code={code} msg={body.get('msg')}")

    token_value = body.get("data", {}).get("token")
    if not token_value:
        raise RuntimeError(f"Root folder meta did not return a token: {body}")

    return token_value


def _upload_file_for_import(client, file_path: str) -> tuple[str, str]:
    """Upload a local file and return the file_token for the import task.

    Uses ``requests`` directly because ``lark_oapi``'s synchronous transport
    (``Transport.execute``) ignores ``BaseRequest.files`` and only sends the
    JSON body -- multipart uploads silently never reach the file bytes. The
    async path handles files, but the desktop HTTP API runs sync. Going through
    ``requests`` with a tenant token is the reliable path.
    """
    import mimetypes  # local import keeps the module importable without it

    config = client.config
    domain = config.domain.rstrip("/")
    uri = "/open-apis/drive/v1/files/upload_all"
    url = f"{domain}{uri}"

    file_name = os.path.basename(file_path)
    file_content = _read_file_bytes(file_path)
    token = _get_tenant_access_token(client)
    parent_node = _get_root_folder_token(client)

    # Feishu requires an explicit media type on the file part; guessing from
    # the extension is sufficient for docx/xlsx.
    ext = Path(file_name).suffix.lower()
    fallback_mimes = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    file_mime_type = mimetypes.guess_type(file_name)[0] or fallback_mimes.get(
        ext, "application/octet-stream"
    )

    # upload_all expects multipart/form-data with file_name + parent_type +
    # parent_node + size as form fields and the raw bytes under "file".
    # parent_type "explorer" uploads into the app's root cloud-space folder;
    # the uploaded file is then fed to import_tasks by file_token.
    form_fields = {
        "file_name": file_name,
        "parent_type": "explorer",
        "parent_node": parent_node,
        "size": str(len(file_content)),
    }

    body = _post_multipart_upload(
        url=url,
        token=token,
        file_name=file_name,
        file_content=file_content,
        file_mime_type=file_mime_type,
        form_fields=form_fields,
        timeout=config.timeout or 30,
    )

    code = body.get("code")
    if code != 0:
        raise RuntimeError(
            f"Upload failed: code={code} msg={body.get('msg')}"
        )

    file_token = body.get("data", {}).get("file_token")
    if not file_token:
        raise RuntimeError(f"Upload did not return a file_token: {body}")

    return file_token, parent_node


def _create_import_task(client, file_token: str, file_extension: str, doc_type: str, mount_key: str) -> str:
    """Create an import task and return the ticket."""
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()
    uri = "/open-apis/drive/v1/import_tasks"

    body = {
        "file_extension": file_extension.lstrip("."),
        "file_token": file_token,
        "type": doc_type,
        "point": {
            "mount_type": 1,
            "mount_key": mount_key,
        },
    }

    request = (
        BaseRequest.builder()
        .http_method(HttpMethod.POST)
        .uri(uri)
        .body(body)
        .token_types({AccessTokenType.TENANT})
        .build()
    )

    response = client.request(request)

    if getattr(response, "code", None) != 0:
        raise RuntimeError(f"Import task creation failed: {_api_error_message(response)}")

    body = _get_response_body(response)
    ticket = body.get("data", {}).get("ticket")

    if not ticket:
        raise RuntimeError("Import task creation did not return a ticket")

    return ticket


def _task_status(result: dict) -> tuple[bool, bool, str]:
    """Interpret an async task result and return (done, success, error_msg).

    Feishu drive import/export tasks report status via ``job_status`` (int):
    0 = success, 1/2 = in progress, other values = failure. Some endpoints also
    use the older string ``status`` field. This helper normalises both.
    """
    job_status = result.get("job_status")
    status = result.get("status")
    error_msg = result.get("job_error_msg", "")

    if job_status == 0 or status == "success":
        return True, True, ""

    if job_status in (1, 2) or status in ("init", "processing", "pending"):
        return False, False, ""

    if job_status is not None:
        return True, False, f"job_status={job_status} {error_msg}".strip()

    if status in ("fail", "failed"):
        return True, False, error_msg or "task failed"

    # Unknown status; keep polling rather than failing immediately.
    return False, False, ""


def _poll_import_task(client, ticket: str) -> dict[str, str]:
    """Poll the import task until success; return {token, url, type}."""
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()
    uri = f"/open-apis/drive/v1/import_tasks/{ticket}"

    for attempt in range(_IMPORT_POLL_MAX_ATTEMPTS):
        request = (
            BaseRequest.builder()
            .http_method(HttpMethod.GET)
            .uri(uri)
            .token_types({AccessTokenType.TENANT})
            .build()
        )
        response = client.request(request)

        if getattr(response, "code", None) != 0:
            raise RuntimeError(f"Import task query failed: {_api_error_message(response)}")

        body = _get_response_body(response)
        result = body.get("data", {}).get("result", {})
        done, success, error_msg = _task_status(result)

        if done:
            if not success:
                raise RuntimeError(f"Import task failed: {error_msg}")
            return {
                "token": result["token"],
                "type": result.get("type", ""),
                "url": result.get("url", ""),
            }

        time.sleep(_IMPORT_POLL_INTERVAL_SECONDS)

    raise RuntimeError("Import task timed out")


def upload_and_import_office_file(local_path: str) -> dict[str, str]:
    """Upload a local .docx/.xlsx to Feishu and convert it to an online document.

    Returns a dict with ``token``, ``type``, and ``url``.
    """
    client = _require_client()
    ext = Path(local_path).suffix.lower()

    if ext not in SUPPORTED_OFFICE_EXTENSIONS:
        raise ValueError(f"Unsupported extension: {ext}")

    doc_type = DOCX_IMPORT_TYPE if ext == ".docx" else XLSX_IMPORT_TYPE
    file_token, mount_key = _upload_file_for_import(client, local_path)
    ticket = _create_import_task(client, file_token, ext, doc_type, mount_key)
    result = _poll_import_task(client, ticket)
    set_office_mapping(local_path, result["token"], result["type"])

    return result


# ---------------------------------------------------------------------------
# Export cloud document -> Download -> Overwrite local file
# ---------------------------------------------------------------------------


def _create_export_task(client, token: str, doc_type: str, file_extension: str) -> str:
    """Create an export task and return the ticket."""
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()
    uri = "/open-apis/drive/v1/export_tasks"

    body = {
        "file_extension": file_extension.lstrip("."),
        "token": token,
        "type": doc_type,
    }

    request = (
        BaseRequest.builder()
        .http_method(HttpMethod.POST)
        .uri(uri)
        .body(body)
        .token_types({AccessTokenType.TENANT})
        .build()
    )

    response = client.request(request)

    if getattr(response, "code", None) != 0:
        raise RuntimeError(f"Export task creation failed: {_api_error_message(response)}")

    body = _get_response_body(response)
    ticket = body.get("data", {}).get("ticket")

    if not ticket:
        raise RuntimeError("Export task creation did not return a ticket")

    return ticket


def _poll_export_task(client, token: str, ticket: str) -> str:
    """Poll the export task until success; return the file_token for download."""
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()
    uri = f"/open-apis/drive/v1/export_tasks/{ticket}"

    for attempt in range(_EXPORT_POLL_MAX_ATTEMPTS):
        request = (
            BaseRequest.builder()
            .http_method(HttpMethod.GET)
            .uri(uri)
            .queries({"token": token})
            .token_types({AccessTokenType.TENANT})
            .build()
        )
        response = client.request(request)

        if getattr(response, "code", None) != 0:
            raise RuntimeError(f"Export task query failed: {_api_error_message(response)}")

        body = _get_response_body(response)
        result = body.get("data", {}).get("result", {})
        done, success, error_msg = _task_status(result)

        if done:
            if not success:
                raise RuntimeError(f"Export task failed: {error_msg}")
            file_token = result.get("file_token")
            if not file_token:
                raise RuntimeError("Export task did not return a file_token")
            return file_token

        time.sleep(_EXPORT_POLL_INTERVAL_SECONDS)

    raise RuntimeError("Export task timed out")


def _download_exported_file(client, file_token: str) -> bytes:
    """Download the exported file bytes from Feishu."""
    AccessTokenType, HttpMethod, BaseRequest = _require_lark_imports()
    uri = f"/open-apis/drive/v1/export_tasks/file/{file_token}/download"

    request = (
        BaseRequest.builder()
        .http_method(HttpMethod.GET)
        .uri(uri)
        .token_types({AccessTokenType.TENANT})
        .build()
    )

    response = client.request(request)

    if getattr(response, "code", None) != 0:
        raise RuntimeError(f"Download failed: {_api_error_message(response)}")

    raw = getattr(response, "raw", None)

    if raw and hasattr(raw, "content"):
        return raw.content

    raise RuntimeError("Download did not return file content")


def export_and_overwrite_office_file(local_path: str) -> dict[str, Any]:
    """Export the Feishu cloud document linked to ``local_path`` and overwrite it.

    Returns a dict with ``bytes_written`` and ``url`` (the cloud document URL).
    """
    client = _require_client()
    mapping = get_office_mapping(local_path)

    if not mapping:
        raise RuntimeError("No Feishu cloud document linked to this file. Open it in Feishu first.")

    token = mapping["token"]
    doc_type = mapping["doc_type"]
    ext = Path(local_path).suffix.lower()
    export_ext = ".docx" if doc_type == DOCX_IMPORT_TYPE else ".xlsx"

    ticket = _create_export_task(client, token, doc_type, export_ext)
    file_token = _poll_export_task(client, token, ticket)
    content = _download_exported_file(client, file_token)

    Path(local_path).write_bytes(content)

    return {"bytes_written": len(content), "url": mapping.get("url", "")}


# ---------------------------------------------------------------------------
# Tool schemas and handlers
# ---------------------------------------------------------------------------

FEISHU_OFFICE_OPEN_SCHEMA = {
    "name": "feishu_office_open",
    "description": (
        "Upload a local .docx or .xlsx file to Feishu/Lark and open it as an "
        "online document. Returns the URL to edit the document in a browser. "
        "Use this when the user wants to collaboratively edit an Office file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "local_path": {
                "type": "string",
                "description": "Absolute path to the local .docx or .xlsx file.",
            },
        },
        "required": ["local_path"],
    },
}

FEISHU_OFFICE_EXPORT_SCHEMA = {
    "name": "feishu_office_export",
    "description": (
        "Export the Feishu/Lark online document linked to a local file back to "
        "the local path, overwriting the original file. Use this after editing "
        "in Feishu to persist changes locally."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "local_path": {
                "type": "string",
                "description": "Absolute path to the local file that was previously opened.",
            },
        },
        "required": ["local_path"],
    },
}


def _handle_feishu_office_open(args: dict, **kwargs) -> str:
    local_path = args.get("local_path", "").strip()

    if not local_path:
        return tool_error("local_path is required")

    ext = Path(local_path).suffix.lower()

    if ext not in SUPPORTED_OFFICE_EXTENSIONS:
        return tool_error(f"Unsupported extension: {ext}. Only .docx and .xlsx are supported.")

    client = get_client()

    if client is None:
        return tool_error("Feishu client not available (not in a Feishu comment context)")

    try:
        result = upload_and_import_office_file(local_path)
    except Exception as exc:
        logger.exception("Failed to open office file in Feishu: %s", local_path)
        return tool_error(f"Failed to open office file in Feishu: {exc}")

    return tool_result(success=True, content=f"Open in Feishu: {result['url']}")


def _handle_feishu_office_export(args: dict, **kwargs) -> str:
    local_path = args.get("local_path", "").strip()

    if not local_path:
        return tool_error("local_path is required")

    client = get_client()

    if client is None:
        return tool_error("Feishu client not available (not in a Feishu comment context)")

    try:
        result = export_and_overwrite_office_file(local_path)
    except Exception as exc:
        logger.exception("Failed to export office file from Feishu: %s", local_path)
        return tool_error(f"Failed to export office file from Feishu: {exc}")

    return tool_result(success=True, content=f"Exported {result['bytes_written']} bytes back to {local_path}")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

registry.register(
    name="feishu_office_open",
    toolset="hermes-feishu",
    schema=FEISHU_OFFICE_OPEN_SCHEMA,
    handler=_handle_feishu_office_open,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Open a local .docx/.xlsx in Feishu for online editing",
    emoji="📝",
)

registry.register(
    name="feishu_office_export",
    toolset="hermes-feishu",
    schema=FEISHU_OFFICE_EXPORT_SCHEMA,
    handler=_handle_feishu_office_export,
    check_fn=_check_feishu,
    requires_env=[],
    is_async=False,
    description="Export the Feishu-edited document back to the local file",
    emoji="💾",
)
