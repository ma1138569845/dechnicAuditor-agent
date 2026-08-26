"""Single resolver for knowledge-base / RAG settings.

Desktop knowledge, ``rag/*``, and the energy-audit tool share one implementation.
Non-secret settings live in ``{HERMES_HOME}/config.yaml`` under ``knowledge_base:``.
Secrets stay in ``{HERMES_HOME}/.env``.

Priority (high → low):
  1. Environment variable (compat + secrets)
  2. Hermes ``config.yaml`` → ``knowledge_base.*``
  3. Hermes ``config.yaml`` → ``energy_audit.rag.*`` (legacy alias)
  4. ``tools/energy_audit/config.yaml`` → ``rag.*`` (standalone fallback)
  5. Hardcoded defaults (localhost + ``{HERMES_HOME}/rag/...``)

``qdrant_config.yaml`` is not read.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# Keep in sync with hermes_cli/config_defaults.py → DEFAULT_CONFIG["knowledge_base"].
DEFAULTS: dict[str, Any] = {
    "qdrant_host": "127.0.0.1",
    "qdrant_port": 6334,
    "qdrant_http_port": 6333,
    "embedding_model": "dashscope/text-embedding-v3",
    "summary_provider": "deepseek",
    "summary_model": "deepseek-v4-flash",
    "deepseek_api_base": "https://api.deepseek.com/v1",
    "energy_audit_collection": "knowledge_segment_qwen",
    "reports_collection": "energy_audit_reports",
}

_CACHE: dict[str, Any] | None = None
_CACHE_TOKEN: tuple | None = None
_DOTENV_LOADED = False


def clear_cache() -> None:
    """Drop the in-process snapshot (tests / after a config rewrite)."""
    global _CACHE, _CACHE_TOKEN, _DOTENV_LOADED
    _CACHE = None
    _CACHE_TOKEN = None
    _DOTENV_LOADED = False


def _file_token(path: Path) -> tuple[int, int]:
    try:
        st = path.stat()
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return (0, 0)


def _live_token() -> tuple:
    home = _hermes_home()
    return (
        _file_token(home / "config.yaml"),
        _file_token(home / ".env"),
        os.environ.get("QDRANT_HOST"),
        os.environ.get("QDRANT_PORT"),
        os.environ.get("QDRANT_HTTP_PORT"),
        os.environ.get("QDRANT_URL"),
        os.environ.get("QDRANT_COLLECTION"),
        os.environ.get("HERMES_KNOWLEDGE_ROOT"),
        os.environ.get("HERMES_WIKI_VAULT"),
        os.environ.get("SUMMARY_MODEL"),
        os.environ.get("DEEPSEEK_MODEL"),
        os.environ.get("SUMMARY_PROVIDER"),
        os.environ.get("DEEPSEEK_API_BASE"),
        os.environ.get("EMBEDDING_MODEL"),
    )


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        override = os.environ.get("HERMES_HOME")
        if override:
            return Path(override)
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes"
        if local.exists():
            return local
        return Path.home() / ".hermes"


def _load_dotenv() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    env_path = _hermes_home() / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def _non_blank(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _package_energy_audit_yaml() -> dict:
    return _load_yaml(Path(__file__).resolve().parent.parent / "tools" / "energy_audit" / "config.yaml")


def _parse_url(url: str) -> tuple[Optional[str], Optional[int]]:
    raw = (url or "").strip()
    if not raw:
        return None, None
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname
    port = parsed.port
    return host, port


def _snapshot() -> dict[str, Any]:
    global _CACHE, _CACHE_TOKEN, _DOTENV_LOADED
    token = _live_token()
    if _CACHE is not None and _CACHE_TOKEN == token:
        return _CACHE
    if _CACHE_TOKEN != token:
        _DOTENV_LOADED = False
    _CACHE_TOKEN = token
    _load_dotenv()
    home = _hermes_home()
    hermes_yaml = _load_yaml(home / "config.yaml")
    kb = hermes_yaml.get("knowledge_base") or {}
    if not isinstance(kb, dict):
        kb = {}
    ea_rag = ((hermes_yaml.get("energy_audit") or {}).get("rag") or {}) if isinstance(hermes_yaml.get("energy_audit"), dict) else {}
    if not isinstance(ea_rag, dict):
        ea_rag = {}
    pkg_rag = (_package_energy_audit_yaml().get("rag") or {})
    if not isinstance(pkg_rag, dict):
        pkg_rag = {}

    url_host, url_port = _parse_url(os.environ.get("QDRANT_URL", ""))
    ea_url_host, ea_url_port = _parse_url(str(ea_rag.get("qdrant_url") or ""))
    pkg_url_host, pkg_url_port = _parse_url(str(pkg_rag.get("qdrant_url") or ""))

    host = (
        os.environ.get("QDRANT_HOST")
        or kb.get("qdrant_host")
        or url_host
        or ea_url_host
        or pkg_url_host
        or DEFAULTS["qdrant_host"]
    )
    grpc_port = (
        os.environ.get("QDRANT_PORT")
        or kb.get("qdrant_port")
        or DEFAULTS["qdrant_port"]
    )
    http_port = (
        os.environ.get("QDRANT_HTTP_PORT")
        or kb.get("qdrant_http_port")
        or url_port
        or ea_url_port
        or pkg_url_port
        or DEFAULTS["qdrant_http_port"]
    )

    knowledge_root = (
        os.environ.get("HERMES_KNOWLEDGE_ROOT")
        or kb.get("knowledge_root")
        or str(home / "rag" / "data")
    )
    wiki_vault = (
        os.environ.get("HERMES_WIKI_VAULT")
        or kb.get("wiki_vault")
        or str(home / "rag" / "wiki")
    )

    _CACHE = {
        "qdrant_host": str(host).strip(),
        "qdrant_port": int(grpc_port),
        "qdrant_http_port": int(http_port),
        "qdrant_api_key": os.environ.get("QDRANT_API_KEY", "").strip(),
        "knowledge_root": str(knowledge_root).strip(),
        "wiki_vault": str(wiki_vault).strip(),
        "embedding_model": str(
            os.environ.get("EMBEDDING_MODEL")
            or kb.get("embedding_model")
            or DEFAULTS["embedding_model"]
        ).strip(),
        "summary_provider": str(
            os.environ.get("SUMMARY_PROVIDER")
            or kb.get("summary_provider")
            or DEFAULTS["summary_provider"]
        ).strip(),
        "summary_model": str(
            os.environ.get("SUMMARY_MODEL")
            or os.environ.get("DEEPSEEK_MODEL")
            or kb.get("summary_model")
            or ea_rag.get("deepseek_model")
            or pkg_rag.get("deepseek_model")
            or DEFAULTS["summary_model"]
        ).strip(),
        "deepseek_api_base": str(
            os.environ.get("DEEPSEEK_API_BASE")
            or kb.get("deepseek_api_base")
            or DEFAULTS["deepseek_api_base"]
        ).strip(),
        "energy_audit_collection": str(
            os.environ.get("QDRANT_COLLECTION")
            or kb.get("energy_audit_collection")
            or ea_rag.get("collection_name")
            or pkg_rag.get("collection_name")
            or DEFAULTS["energy_audit_collection"]
        ).strip(),
        "reports_collection": str(
            kb.get("reports_collection") or DEFAULTS["reports_collection"]
        ).strip(),
        "dashscope_api_key": os.environ.get("DASHSCOPE_API_KEY", "").strip(),
        "deepseek_api_key": (
            os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        ).strip(),
    }
    return _CACHE


def qdrant_host() -> str:
    return _snapshot()["qdrant_host"]


def qdrant_grpc_port() -> int:
    return int(_snapshot()["qdrant_port"])


def qdrant_http_port() -> int:
    return int(_snapshot()["qdrant_http_port"])


def qdrant_http_url() -> str:
    return f"http://{qdrant_host()}:{qdrant_http_port()}"


def qdrant_api_key() -> str:
    return _snapshot()["qdrant_api_key"]


def qdrant_client_kwargs(*, prefer_grpc: bool = True, timeout: int | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": qdrant_host(),
        "port": qdrant_grpc_port() if prefer_grpc else qdrant_http_port(),
        "prefer_grpc": prefer_grpc,
        "check_compatibility": False,
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    key = qdrant_api_key()
    if key:
        kwargs["api_key"] = key
    return kwargs


def knowledge_root() -> Path:
    return Path(_snapshot()["knowledge_root"])


def wiki_vault() -> str:
    return _snapshot()["wiki_vault"]


def embedding_model() -> str:
    return _snapshot()["embedding_model"]


def summary_provider() -> str:
    return _snapshot()["summary_provider"]


def summary_model() -> str:
    return _snapshot()["summary_model"]


def deepseek_api_base() -> str:
    return _snapshot()["deepseek_api_base"]


def energy_audit_collection() -> str:
    return _snapshot()["energy_audit_collection"]


def reports_collection() -> str:
    return _snapshot()["reports_collection"]


def dashscope_api_key() -> str:
    return _snapshot()["dashscope_api_key"]


def deepseek_api_key() -> str:
    return _snapshot()["deepseek_api_key"]
