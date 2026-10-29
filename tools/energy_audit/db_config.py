"""能源审计 PG 数据库连接配置统一解析器。

解析优先级（高到低）：
  1. 显式参数 overrides；
  2. 环境变量 EA_PG_*，兼容旧命名 DB_*；
  3. Hermes config.yaml 的 energy_audit.database.*；
  4. 包内 tools/energy_audit/config.yaml 的 database.*；
  5. 内置非密默认值。

密码不设内置默认值，全部来源缺失时明确报错。源码中不得写入明文密码。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional


try:
    from agent.secret_scope import get_secret as _get_secret
except ModuleNotFoundError as exc:
    if exc.name not in {"agent", "agent.secret_scope"}:
        raise

    def _get_secret(name: str, default=None):
        return os.environ.get(name, default)


_KEYS = {
    "host": ("EA_PG_HOST", "DB_HOST", "10.10.1.165"),
    "port": ("EA_PG_PORT", "DB_PORT", "5432"),
    "database": ("EA_PG_NAME", "DB_NAME", "dc_energy_audit2"),
    "user": ("EA_PG_USER", "DB_USER", "postgres"),
    "password": ("EA_PG_PASSWORD", "DB_PASSWORD", None),
    "sslmode": ("EA_PG_SSLMODE", "DB_SSLMODE", "prefer"),
}

_LOCAL_CONFIG_YAML = Path(__file__).resolve().parent / "config.yaml"
_FILE_ENV_VARS = {
    "base_url": "EA_FILE_BASE_URL",
    "scheme": "EA_FILE_SCHEME",
    "host": "EA_FILE_HOST",
    "port": "EA_FILE_PORT",
}


def _non_blank(value) -> bool:
    return value is not None and str(value).strip() != ""


def _load_yaml():
    """Prefer Hermes' YAML wrapper, then fall back to standalone PyYAML."""
    try:
        import hermes_yaml

        return hermes_yaml
    except ModuleNotFoundError as exc:
        if exc.name != "hermes_yaml":
            raise
    try:
        import yaml

        return yaml
    except ModuleNotFoundError as exc:
        if exc.name != "yaml":
            raise
        return None


def _from_env(key: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(value, env_var)`` for the first non-blank EA/legacy variable."""
    ea_var, db_var, _ = _KEYS[key]
    for var in (ea_var, db_var):
        value = _get_secret(var)
        if _non_blank(value):
            return str(value).strip(), var
    # Non-secret process overrides remain visible to a routed profile even after
    # its temporary secret scope is reset. Password stays fail-closed.
    if key != "password":
        for var in (ea_var, db_var):
            value = os.environ.get(var)
            if _non_blank(value):
                return str(value).strip(), var
    return None, None


def _hermes_config_path() -> Optional[Path]:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home()) / "config.yaml"
    except Exception:
        pass
    for candidate in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "config.yaml",
        Path.home() / ".hermes" / "config.yaml",
    ):
        if candidate.exists():
            return candidate
    return None


def _from_hermes_config(section: str, key: str) -> Optional[str]:
    try:
        path = _hermes_config_path()
        if not path or not path.exists():
            return None
        yaml = _load_yaml()
        if yaml is None:
            return None

        with open(path, encoding="utf-8-sig") as fh:
            cfg = yaml.safe_load(fh) or {}
        value = ((cfg.get("energy_audit") or {}).get(section) or {}).get(key)
        if _non_blank(value):
            return str(value).strip()
    except Exception:
        pass
    return None


def _from_local_config(section: str, key: str) -> Optional[str]:
    try:
        if not _LOCAL_CONFIG_YAML.exists():
            return None
        yaml = _load_yaml()
        if yaml is None:
            return None

        with open(_LOCAL_CONFIG_YAML, encoding="utf-8-sig") as fh:
            cfg = yaml.safe_load(fh) or {}
        value = (cfg.get(section) or {}).get(key)
        if _non_blank(value):
            return str(value).strip()
    except Exception:
        pass
    return None


def _resolve_pg_field(key: str, overrides: dict) -> tuple[Optional[str], Optional[str]]:
    value = overrides.get(key)
    if _non_blank(value):
        return str(value).strip(), "override"

    value, _ = _from_env(key)
    if _non_blank(value):
        return str(value).strip(), "environment"

    value = _from_hermes_config("database", key)
    if _non_blank(value):
        return str(value).strip(), "profile_config"

    value = _from_local_config("database", key)
    if _non_blank(value):
        return str(value).strip(), "package_config"

    value = _KEYS[key][2]
    if _non_blank(value):
        return str(value).strip(), "default"
    return None, None


def get_pg_config(overrides: Optional[Dict] = None) -> Dict:
    """返回可直接传给 ``psycopg2.connect`` 的配置字典。"""
    overrides = overrides or {}
    resolved = {}
    for key in _KEYS:
        value, _ = _resolve_pg_field(key, overrides)
        if value is not None:
            resolved[key] = value

    if "password" not in resolved:
        raise RuntimeError(
            "PG 数据库密码未配置。请通过以下任一方式提供：\n"
            "  1. 环境变量 EA_PG_PASSWORD（或 DB_PASSWORD）\n"
            "  2. Hermes config.yaml → energy_audit.database.password\n"
            "  3. tools/energy_audit/config.yaml → database.password（本地开发）"
        )
    return resolved


def describe_pg_config(overrides: Optional[Dict] = None) -> Dict:
    """Describe effective PG settings without returning the password."""
    overrides = overrides or {}
    values = {}
    sources = {}
    env_vars = {}
    env_overrides = []

    for key in _KEYS:
        value, source = _resolve_pg_field(key, overrides)
        if source == "environment":
            _, env_var = _from_env(key)
            if env_var:
                env_vars[key] = env_var
                if key != "password":
                    env_overrides.append(key)
        if source:
            sources[key] = source
        if value is not None and key != "password":
            values[key] = value

    return {
        "values": values,
        "sources": sources,
        "password_set": "password" in sources,
        "env_vars": env_vars,
        "env_overrides": env_overrides,
    }


def _file_value(overrides: Dict, env_var: str, key: str) -> Optional[str]:
    value = overrides.get(key)
    if not _non_blank(value):
        value = os.environ.get(env_var)
    if not _non_blank(value):
        value = _from_hermes_config("file", key)
    if not _non_blank(value):
        value = _from_local_config("file", key)
    return str(value).strip() if _non_blank(value) else None


def _file_value_source(key: str) -> Optional[str]:
    if _non_blank(os.environ.get(_FILE_ENV_VARS[key])):
        return "environment"
    if _non_blank(_from_hermes_config("file", key)):
        return "profile_config"
    if _non_blank(_from_local_config("file", key)):
        return "package_config"
    return None


def _file_config_source(base_url: str) -> str:
    source = _file_value_source("base_url")
    if source:
        return source
    if not base_url:
        return ""
    for candidate in ("environment", "profile_config", "package_config"):
        if any(
            _file_value_source(key) == candidate
            for key in ("scheme", "host", "port")
        ):
            return candidate
    return "default"


def _db_host() -> Optional[str]:
    env_host, _ = _from_env("host")
    return (env_host
            or _from_hermes_config("database", "host")
            or _from_local_config("database", "host")
            or _KEYS["host"][2])


def get_file_base_url(overrides: Optional[Dict] = None) -> str:
    """解析附件文件服务基础地址；未显式配置时返回空字符串。"""
    overrides = overrides or {}
    base_url = _file_value(overrides, "EA_FILE_BASE_URL", "base_url")
    if base_url:
        return base_url.rstrip("/")

    explicit_host = _file_value(overrides, "EA_FILE_HOST", "host")
    explicit_port = _file_value(overrides, "EA_FILE_PORT", "port")
    if not explicit_host and not explicit_port:
        return ""

    scheme = _file_value(overrides, "EA_FILE_SCHEME", "scheme") or "http"
    host = explicit_host or _db_host()
    if not host:
        return ""

    url = f"{scheme}://{host}"
    if explicit_port:
        url += f":{explicit_port}"
    return url.rstrip("/")


def describe_file_config() -> Dict[str, str | bool]:
    """Describe the effective file service URL without exposing unrelated config."""
    base_url = get_file_base_url()
    return {
        "base_url": base_url,
        "source": _file_config_source(base_url),
        "environment_override": _non_blank(os.environ.get("EA_FILE_BASE_URL")),
    }

