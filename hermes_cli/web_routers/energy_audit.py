"""Energy-audit database settings and report REST routes."""

from __future__ import annotations

import socket
from typing import Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter
from pydantic import BaseModel

from hermes_cli.web_routers._common import (
    config_scoped_to_thread,
    config_write_scope,
)

router = APIRouter()

_NON_SECRET_DATABASE_FIELDS = ("host", "port", "database", "user", "sslmode")


class EnergyAuditProjectsRequest(BaseModel):
    keyword: str


class EnergyAuditGenerateRequest(BaseModel):
    project_name: str
    audit_type: str = "公共机构"
    output_dir: Optional[str] = None
    mode: str = "template"
    reference_dir: Optional[str] = None


class EnergyAuditImitateRequest(BaseModel):
    project_name: str
    chapter: str
    section: str = ""
    institution_category: str = ""
    specific_type: str = ""
    audit_type: str = ""
    extra_context: str = ""
    top_k: int = 5
    refresh_from_pg: bool = False


class EnergyAuditSettingsUpdate(BaseModel):
    host: str
    port: str
    database: str
    user: str
    sslmode: str = "prefer"
    password: str = ""
    file_base_url: Optional[str] = None


def _describe_energy_audit_settings() -> dict[str, Any]:
    from tools.energy_audit import db_config

    return {**db_config.describe_pg_config(), "file": db_config.describe_file_config()}


def _validated_file_base_url(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("invalid file base url") from exc
    return value


def _safe_diagnostic(exc: BaseException) -> dict[str, str]:
    """Classify a connection failure without echoing DSN, host, or credentials."""
    try:
        import psycopg2
    except ImportError:
        return {
            "code": "driver_missing",
            "message": "PostgreSQL 驱动 psycopg2 未安装，请安装后端 Python 依赖。",
        }

    code = getattr(exc, "pgcode", None)
    if code in {"28P01", "28000"}:
        return {"code": "authentication", "message": "数据库认证失败，请检查用户名或密码。"}
    if code == "3D000":
        return {"code": "database", "message": "数据库不存在，请检查数据库名称。"}
    if code == "08001" or isinstance(exc, (socket.gaierror, ConnectionError, OSError)):
        return {"code": "network", "message": "无法连接数据库主机或端口，请检查地址、端口和网络。"}
    if isinstance(exc, psycopg2.OperationalError):
        if "timeout" in str(exc).lower():
            return {"code": "timeout", "message": "数据库连接超时，请检查网络和数据库服务。"}
        return {"code": "network", "message": "数据库连接失败，请检查地址、端口和数据库服务。"}
    return {"code": "configuration", "message": "数据库连接配置无效，请检查连接参数。"}


def _test_connection() -> dict[str, Any]:
    from tools.energy_audit import db_config

    settings = _describe_energy_audit_settings()
    if not settings["password_set"]:
        return {
            "ok": False,
            "code": "password_missing",
            "message": "数据库密码未配置，请在下方填写密码或设置 EA_PG_PASSWORD。",
            "stages": {"tcp": "skipped", "authentication": "skipped", "database": "skipped"},
            "settings": settings,
        }

    host = settings["values"]["host"]
    port = settings["values"]["port"]
    stages = {"tcp": "failed", "authentication": "skipped", "database": "skipped"}
    try:
        port_number = int(port)
        if not 1 <= port_number <= 65535:
            raise ValueError(port)
        with socket.create_connection((host, port_number), timeout=5):
            stages["tcp"] = "ok"
    except (OSError, ValueError) as exc:
        failure = _safe_diagnostic(exc)
        return {"ok": False, **failure, "stages": stages, "settings": settings}

    try:
        import psycopg2
    except ImportError:
        return {
            "ok": False,
            **_safe_diagnostic(ImportError()),
            "stages": stages,
            "settings": settings,
        }

    connection = None
    try:
        config = db_config.get_pg_config()
        config["connect_timeout"] = 5
        connection = psycopg2.connect(**config)
        stages["authentication"] = "ok"
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        stages["database"] = "ok"
        return {
            "ok": True,
            "code": "ok",
            "message": "连接成功，数据库可访问。",
            "stages": stages,
            "settings": settings,
        }
    except (psycopg2.Error, OSError, ValueError) as exc:
        failure = _safe_diagnostic(exc)
        if failure["code"] not in {"network", "timeout"}:
            stages["authentication"] = "failed"
        return {"ok": False, **failure, "stages": stages, "settings": settings}
    finally:
        if connection is not None:
            connection.close()


def _reset_settings() -> dict[str, Any]:
    """Clear saved non-secret fields; preserve config.yaml and .env passwords."""
    from hermes_cli.config import (
        atomic_config_replace,
        get_config_path,
        read_user_config_raw,
    )
    config_path = get_config_path()
    raw = read_user_config_raw(config_path)
    energy = raw.get("energy_audit")
    preserved = False
    if isinstance(energy, dict):
        database = energy.get("database")
        if isinstance(database, dict):
            preserved = "password" in database
            for key in _NON_SECRET_DATABASE_FIELDS:
                database.pop(key, None)
            if not database:
                energy.pop("database", None)
        file_config = energy.get("file")
        if isinstance(file_config, dict):
            file_config.pop("base_url", None)
            if not file_config:
                energy.pop("file", None)
        if not energy:
            raw.pop("energy_audit", None)
        # Deliberate deletion of only saved non-secret settings. save_config refuses
        # omitted mapping paths, while this wrapper is the sanctioned full-state replacement.
        atomic_config_replace(config_path, raw)

    settings = _describe_energy_audit_settings()
    return {
        "ok": True,
        "password_preserved": preserved,
        **settings,
    }


def _save_settings(update: EnergyAuditSettingsUpdate) -> dict[str, Any]:
    """Save non-secret fields to raw config and a typed password only to ``.env``.

    A blank password keeps both the profile ``.env`` value and any legacy
    ``config.yaml`` password. A typed password replaces the ``.env`` value and
    only then removes the config copy.
    """
    from hermes_cli.config import (
        atomic_config_replace,
        env_write_refusal,
        get_config_path,
        get_env_path,
        read_user_config_raw,
        save_env_value,
    )
    from hermes_cli.web_routers._common import is_redacted_credential_preview
    password = update.password.strip()
    file_base_url = _validated_file_base_url(update.file_base_url)
    if is_redacted_credential_preview(password):
        raise ValueError("redacted credential")
    if password and env_write_refusal("EA_PG_PASSWORD", "set"):
        raise ValueError("managed credential")

    config_path = get_config_path()
    raw = read_user_config_raw(config_path)
    energy = raw.setdefault("energy_audit", {})
    if not isinstance(energy, dict):
        raise ValueError("energy_audit config is not a mapping")
    database = energy.setdefault("database", {})
    if not isinstance(database, dict):
        raise ValueError("energy_audit.database config is not a mapping")

    values = {
        "host": update.host.strip(),
        "port": update.port.strip(),
        "database": update.database.strip(),
        "user": update.user.strip(),
        "sslmode": update.sslmode.strip() or "prefer",
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    if not values["port"].isdigit() or not 1 <= int(values["port"]) <= 65535:
        raise ValueError("invalid port")
    if values["sslmode"] not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ValueError("invalid sslmode")

    if file_base_url is not None:
        file_config = energy.get("file")
        if file_config is None:
            file_config = {}
        if not isinstance(file_config, dict):
            raise ValueError("file config is not a mapping")
        if file_base_url:
            file_config["base_url"] = file_base_url
            energy["file"] = file_config
        else:
            file_config.pop("base_url", None)
            if file_config:
                energy["file"] = file_config
            else:
                energy.pop("file", None)

    database.update(values)
    if password:
        save_env_value("EA_PG_PASSWORD", password)
        database.pop("password", None)
    atomic_config_replace(config_path, raw)

    settings = _describe_energy_audit_settings()
    return {
        "ok": True,
        "profile_env": str(get_env_path()),
        **settings,
    }


@router.get("/api/energy-audit/settings")
async def energy_audit_settings(profile: Optional[str] = None):
    def _read():
        return _describe_energy_audit_settings()

    return {"profile": (profile or "current").strip() or "current", **await config_scoped_to_thread(profile, _read)}


@router.post("/api/energy-audit/test-connection")
async def energy_audit_test_connection(profile: Optional[str] = None):
    return await config_scoped_to_thread(profile, _test_connection)


@router.post("/api/energy-audit/reset-settings")
async def energy_audit_reset_settings(profile: Optional[str] = None):
    def _reset():
        with config_write_scope(profile):
            return _reset_settings()

    import asyncio

    return await asyncio.to_thread(_reset)


@router.put("/api/energy-audit/settings")
async def energy_audit_save_settings(
    body: EnergyAuditSettingsUpdate, profile: Optional[str] = None
):
    from fastapi import HTTPException

    def _save():
        with config_write_scope(profile):
            try:
                return _save_settings(body)
            except ValueError as exc:
                reason = str(exc)
                if reason == "redacted credential":
                    detail = "不能保存已脱敏的密码预览，请重新输入完整密码。"
                elif reason == "managed credential":
                    detail = "密码由管理员托管，不能在这里修改。其他字段也未保存。"
                elif reason == "invalid file base url":
                    detail = "附件文件服务地址必须是包含主机名的 HTTP 或 HTTPS URL。"
                else:
                    detail = "数据库或附件服务配置无效，请检查地址和连接参数。"
                raise HTTPException(status_code=400, detail=detail) from exc

    import asyncio

    return await asyncio.to_thread(_save)


@router.post("/api/energy-audit/projects")
async def energy_audit_projects(
    body: EnergyAuditProjectsRequest, profile: Optional[str] = None
):
    from tools.energy_audit_tool import rest_search_energy_audit_projects

    return await config_scoped_to_thread(
        profile, lambda: rest_search_energy_audit_projects(body.keyword)
    )


@router.post("/api/energy-audit/generate")
async def energy_audit_generate(
    body: EnergyAuditGenerateRequest, profile: Optional[str] = None
):
    from tools.energy_audit_tool import rest_generate_energy_audit_report

    return await config_scoped_to_thread(
        profile,
        lambda: rest_generate_energy_audit_report(
            body.project_name,
            body.audit_type,
            body.output_dir,
            body.mode,
            body.reference_dir,
        ),
    )


@router.post("/api/energy-audit/imitate")
async def energy_audit_imitate(
    body: EnergyAuditImitateRequest, profile: Optional[str] = None
):
    from tools.energy_audit_imitate_tool import rest_imitate_energy_audit_paragraph

    return await config_scoped_to_thread(
        profile,
        lambda: rest_imitate_energy_audit_paragraph(
            body.project_name,
            body.chapter,
            body.section,
            body.institution_category,
            body.specific_type,
            body.audit_type,
            body.extra_context,
            body.top_k,
            body.refresh_from_pg,
        ),
    )
