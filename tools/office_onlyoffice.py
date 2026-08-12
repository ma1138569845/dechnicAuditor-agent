#!/usr/bin/env python3
"""ONLYOFFICE DocumentServer integration for Hermes office previews.

When ONLYOFFICE is enabled (``HERMES_OFFICE_DS_URL`` and
``HERMES_OFFICE_JWT_SECRET`` both set), every ``.docx/.xlsx/.pptx`` opens in
the remote DocumentServer instead of the local editor_sdk path. The
remote DS renders the real WYSIWYG editor inside the preview-server shell; the
local backend hosts the file bytes and exposes ``/api/onlyoffice/download`` and
``/api/onlyoffice/save`` that the DS reaches over LAN, so edits land back on the
on-disk file.

Security model
--------------
The DS and this backend share a JWT secret. The editor config is signed with
it (``token`` field); the DS echoes that token back on callbacks and file
downloads. The preview server therefore authenticates every OnlyOffice
endpoint against the same secret:

  * ``GET /api/onlyoffice/download?file_id=&token=`` — self-contained signed
    token (query) so we do not depend on the DS forwarding the header.
  * ``POST /api/onlyoffice/save`` — ``Authorization: Bearer <jwt>`` from the DS
    callback.

When not enabled, every function here returns/falls through so the existing
SDK preview behaviour is preserved unchanged.
"""

import json
import logging
import os
import socket
import threading
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import jwt  # pyjwt
except ImportError:  # pragma: no cover - env should provide pyjwt
    jwt = None

_ENV_DS_URL = "HERMES_OFFICE_DS_URL"
_ENV_JWT_SECRET = "HERMES_OFFICE_JWT_SECRET"
_ENV_CALLBACK_HOST = "HERMES_OFFICE_CALLBACK_HOST"
_ENV_PREVIEW_PORT = "HERMES_OFFICE_PREVIEW_PORT"

_LANG = "zh-CN"
_USER_NAME = "Hermes"

# GUID of the Hermes AI Bridge plugin (see office_preview_server._ONLYOFFICE_PLUGIN_CONFIG).
# Listed in editorConfig.plugins.autostart so the DS runs it on document ready.
_ONLYOFFICE_PLUGIN_GUID = "asc.{hermes-ai-bridge}"

# SDK doc_type (doc/sheet/slide) -> (OnlyOffice documentType, fileType).
_DOC_TYPES = {
    "doc": ("word", "docx"),
    "sheet": ("cell", "xlsx"),
    "slide": ("slide", "pptx"),
}


# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

def ds_url() -> Optional[str]:
    """Base URL of the remote DocumentServer, e.g. ``http://10.10.2.55:8090``."""
    value = os.environ.get(_ENV_DS_URL, "").strip().rstrip("/")
    return value or None


def jwt_secret() -> Optional[str]:
    """Shared HS256 secret between this backend and the DocumentServer."""
    value = os.environ.get(_ENV_JWT_SECRET, "").strip()
    return value or None


def callback_host() -> str:
    """The LAN host the DocumentServer must use to reach *this* machine."""
    value = os.environ.get(_ENV_CALLBACK_HOST, "").strip()
    if value:
        return value
    return _detect_lan_ip()


def preview_port() -> Optional[int]:
    """Optional fixed preview-server port (so the firewall rule is one port)."""
    value = os.environ.get(_ENV_PREVIEW_PORT, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("invalid %s=%r; ignoring", _ENV_PREVIEW_PORT, value)
        return None


def is_enabled() -> bool:
    """OnlyOffice mode is on when the DS URL *and* the shared secret are set."""
    return bool(ds_url() and jwt_secret())


def _detect_lan_ip() -> str:
    """Best-effort local IP reachable by the DS (outbound route to it)."""
    host = None
    if ds_url():
        try:
            host = urllib.parse.urlparse(ds_url()).hostname
        except Exception:  # pragma: no cover - malformed URL
            host = None
    if host:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                # A UDP connect() never sends a packet; it just pins the route
                # so getsockname() reports the outbound interface toward DS.
                sock.connect((host, 9))
                return sock.getsockname()[0]
        except OSError:  # pragma: no cover - no route toward DS
            pass
    try:  # pragma: no cover - fallback
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# JWT signing / verification (HS256 via pyjwt)
# ---------------------------------------------------------------------------

def sign_jwt(payload: dict, secret: Optional[str] = None) -> str:
    """Sign *payload* with the shared secret. Raises if not configured."""
    secret = secret or jwt_secret()
    if not secret:
        raise RuntimeError(f"{_ENV_JWT_SECRET} not configured")
    if jwt is None:  # pragma: no cover - env should provide pyjwt
        raise RuntimeError("pyjwt is required for ONLYOFFICE integration")
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_jwt(token: str, secret: Optional[str] = None) -> Optional[dict]:
    """Verify *token* against the shared secret; None when invalid."""
    secret = secret or jwt_secret()
    if not secret or not token or jwt is None:
        return None
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Open-document registry (file_id <-> on-disk path + OnlyOffice key)
# ---------------------------------------------------------------------------

@dataclass
class DocRecord:
    file_id: str
    file_path: str
    doc_type: str  # doc / sheet / slide
    key: str       # OnlyOffice key; rotated after every save callback
    status: str = field(default="pending")  # pending / saving / saved / error
    message: str = field(default="")
    saved_at: Optional[str] = field(default=None)
    # File mtime when the editor was opened. Together with
    # ``ds_saved_mtime_ns`` it forms the "what the editor currently shows"
    # baseline the renderer compares the on-disk mtime against.
    open_mtime_ns: Optional[int] = field(default=None)
    # File mtime right after the last DocumentServer save callback wrote the
    # bytes. Lets the desktop renderer tell "the DS itself just saved" apart
    # from an external write (an agent edit landing on disk) so it only
    # refreshes the editor for the latter.
    ds_saved_mtime_ns: Optional[int] = field(default=None)
    # The embed shell's latch: True once the user edited after the last real
    # save (status-6 callback). DS 9.x onDocumentStateChange(false) fires as
    # soon as its co-authoring service acknowledges changes — long before
    # anything hits disk — so the raw flag alone cannot protect unsaved edits
    # from an external refresh. The shell mirrors this latch here so the
    # renderer can read it straight from /status at refresh-decision time.
    editor_dirty: bool = field(default=False)


class _Registry:
    """Thread-safe registry mapping file_id (and OnlyOffice key) -> DocRecord."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_id: dict[str, DocRecord] = {}
        self._by_key: dict[str, str] = {}  # onlyoffice key -> file_id
        self._by_path: dict[str, str] = {}  # normalized path -> file_id

    def register(self, file_id: str, file_path: str, doc_type: str,
                 key: Optional[str] = None) -> DocRecord:
        rec = DocRecord(file_id=file_id, file_path=file_path,
                        doc_type=doc_type, key=key or str(uuid.uuid4()))
        try:
            rec.open_mtime_ns = os.stat(file_path).st_mtime_ns
        except OSError:  # pragma: no cover - file vanished between open calls
            rec.open_mtime_ns = None
        with self._lock:
            self._by_id[file_id] = rec
            self._by_key[rec.key] = file_id
            self._by_path[os.path.normpath(file_path)] = file_id
        return rec

    def find_by_path(self, file_path: str) -> Optional[DocRecord]:
        with self._lock:
            fid = self._by_path.get(os.path.normpath(file_path))
            return self._by_id.get(fid) if fid else None

    def lookup(self, file_id: str) -> Optional[DocRecord]:
        with self._lock:
            return self._by_id.get(file_id)

    def lookup_by_key(self, key: str) -> Optional[DocRecord]:
        with self._lock:
            fid = self._by_key.get(key)
            return self._by_id.get(fid) if fid else None

    def close(self, file_id: str) -> None:
        with self._lock:
            rec = self._by_id.pop(file_id, None)
            if rec:
                self._by_key.pop(rec.key, None)
                self._by_path.pop(os.path.normpath(rec.file_path), None)

    def clear(self) -> None:
        """Drop every open document (used on server teardown / tests)."""
        with self._lock:
            self._by_id.clear()
            self._by_key.clear()
            self._by_path.clear()

    def rotate_key(self, file_id: str) -> None:
        """Give the document a fresh OnlyOffice key after a save."""
        with self._lock:
            rec = self._by_id.get(file_id)
            if rec:
                old = rec.key
                rec.key = str(uuid.uuid4())
                self._by_key.pop(old, None)
                self._by_key[rec.key] = file_id

    def mark(self, file_id: str, status: str, message: str = "",
             saved_at: Optional[str] = None,
             ds_saved_mtime_ns: Optional[int] = None) -> None:
        with self._lock:
            rec = self._by_id.get(file_id)
            if rec:
                rec.status = status
                rec.message = message
                rec.saved_at = saved_at
                if ds_saved_mtime_ns is not None:
                    rec.ds_saved_mtime_ns = ds_saved_mtime_ns


registry = _Registry()


def _user() -> dict:
    return {"id": "hermes-desktop", "name": _USER_NAME}


# ---------------------------------------------------------------------------
# Editor config construction
# ---------------------------------------------------------------------------

def callback_base() -> str:
    """The LAN base URL the DS uses for download/save callbacks to this host."""
    from tools.office_preview_server import preview_server
    if preview_server.port is None:
        raise RuntimeError("preview server not started")
    return f"http://{callback_host()}:{preview_server.port}"


def _document_type(file_id: str) -> tuple[str, str]:
    rec = registry.lookup(file_id)
    if not rec:
        raise KeyError(f"unknown file_id {file_id}")
    return _DOC_TYPES.get(rec.doc_type, ("word", "docx"))


def make_editor_config(file_id: str) -> dict:
    """Build the signed OnlyOffice editor config for *file_id*.

    Returns the config dict (including the signed ``token``). The shell page
    fetches it from ``/api/onlyoffice/config?file_id=`` and passes it to
    ``DocsAPI.DocEditor``.
    """
    rec = registry.lookup(file_id)
    if not rec:
        return {"error": "file_id not found"}
    document_type, file_type = _DOC_TYPES.get(rec.doc_type, ("word", "docx"))
    base = callback_base()
    config = {
        "document": {
            "fileType": file_type,
            "key": rec.key,
            "title": os.path.basename(rec.file_path),
            "url": f"{base}/api/onlyoffice/download?file_id="
                   f"{urllib.parse.quote(file_id)}"
                   f"&token={urllib.parse.quote(_download_token(file_id))}",
        },
        "documentType": document_type,
        "editorConfig": {
            "callbackUrl": f"{base}/api/onlyoffice/save",
            "lang": _LANG,
            "mode": "edit",
            # Strict co-editing: edits are sent to the document editing
            # service only when the user saves. In the default fast mode DS
            # streams changes out almost immediately, so onDocumentStateChange
            # flips dirty=false right after typing and the preview's
            # "external change while dirty" conflict banner can never fire.
            # With strict mode dirty=true persists until the user saves, which
            # is exactly the state the banner must protect against.
            "coediting": "strict",
            "user": _user(),
            "customization": {
                # With forcesave the DS sends a status-6 save callback the
                # moment the user clicks the toolbar Save button or presses
                # Ctrl+S. Without it the callback is deferred to the autosave
                # interval (~10 min) or editor close, so an explicit "save"
                # would not land on disk until then.
                "forcesave": True,
            },
        },
        "height": "100%",
        "width": "100%",
    }
    # Load the Hermes AI bridge plugin so the Community Edition (which lacks the
    # Automation API connector) can still report text selections to the shell.
    # ``autostart`` lists plugin GUIDs the DS runs automatically on document
    # ready (asc_pluginRun(guid, 0, '')); without it the plugin is registered
    # but never started, so window.Asc.plugin stays undefined.
    config["editorConfig"]["plugins"] = {
        "pluginsData": [f"{base}/onlyoffice-plugin/config.json"],
        "autostart": [_ONLYOFFICE_PLUGIN_GUID],
    }
    # Tag config tokens so they cannot be reused as save-callback auth.
    config["token"] = sign_jwt({**config, "purpose": "config"})
    return config


def _callback_token_payload(token: str) -> Optional[dict]:
    """Return the callback payload from a DS JWT, or None if invalid.

    Rejects config tokens (purpose == config) and tokens without a status.
    Handles both flat and DS 7.2+ nested ``{"payload": {...}}`` shapes.
    """
    payload = verify_jwt(token or "")
    if not payload:
        return None
    if payload.get("purpose") == "config":
        return None
    inner = payload.get("payload")
    if isinstance(inner, dict):
        if inner.get("purpose") == "config":
            return None
        if "status" in inner:
            return inner
    if "status" in payload:
        return payload
    return None


def check_callback_auth(authorization: str) -> Optional[dict]:
    """Verify the DS callback's ``Authorization: Bearer <jwt>`` header."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return _callback_token_payload(token.strip())


def _download_token(file_id: str) -> str:
    """Short-lived signed token proving this file_id was opened by us."""
    return sign_jwt({"file_id": file_id, "purpose": "download"})


def check_download_token(file_id: str, token: str) -> bool:
    """True when *token* is a valid signed download token for *file_id*."""
    payload = verify_jwt(token or "")
    if not payload:
        return False
    return payload.get("purpose") == "download" and payload.get("file_id") == file_id


# ---------------------------------------------------------------------------
# Force save via the DocumentServer command service
# ---------------------------------------------------------------------------

def force_save(file_id: str) -> dict:
    """Ask the DocumentServer to flush *file_id* to disk right now.

    POSTs ``{c: forcesave, key}`` to the DS ``/command`` endpoint (the
    server-side command service). The DS then saves the currently-open editor
    session and delivers a status-6 callback to our save handler, which writes
    the bytes back to the on-disk file. This is the reliable force-save path
    used by the shell's 强制保存 button — the client-side
    ``serviceCommand('mc:forceSave')`` does not fire a callback in DS 9.4.

    Returns the command-service response dict; ``error: 0`` means the save was
    scheduled (a callback will follow). ``error: 4`` means the document had no
    changes to save. Raises :class:`KeyError` for an unknown file_id and a
    network/HTTP error for DS-unreachable situations.
    """
    rec = registry.lookup(file_id)
    if not rec:
        raise KeyError(f"unknown file_id {file_id}")
    ds = ds_url()
    if not ds:
        raise RuntimeError(f"{_ENV_DS_URL} not configured")
    body = {"c": "forcesave", "key": rec.key}
    payload = json.dumps({"token": sign_jwt(body)}).encode("utf-8")
    req = urllib.request.Request(
        f"{ds}/command",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))
