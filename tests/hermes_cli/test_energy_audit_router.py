"""Energy-audit settings and REST routes honor profile scope and redact secrets."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from starlette.testclient import TestClient


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    root = tmp_path / "hermes"
    root.mkdir()
    (root / "config.yaml").write_text(
        "energy_audit:\n"
        "  database:\n"
        "    host: default-host\n"
        "    port: 5432\n"
        "    password: default-config-secret\n"
        "  imitate:\n"
        "    reference_dir: keep-default\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("EA_PG_PASSWORD=default-env-secret\n", encoding="utf-8")

    profile = root / "profiles" / "audit"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text(
        "energy_audit:\n"
        "  database:\n"
        "    host: audit-host\n"
        "    port: 6543\n"
        "    database: audit-db\n"
        "    user: audit-user\n"
        "    sslmode: require\n"
        "    password: profile-config-secret\n"
        "  imitate:\n"
        "    reference_dir: keep-profile\n",
        encoding="utf-8",
    )
    (profile / ".env").write_text("EA_PG_PASSWORD=profile-env-secret\n", encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.delenv("EA_PG_HOST", raising=False)
    monkeypatch.delenv("EA_PG_PORT", raising=False)
    monkeypatch.delenv("EA_PG_NAME", raising=False)
    monkeypatch.delenv("EA_PG_USER", raising=False)
    monkeypatch.delenv("EA_PG_SSLMODE", raising=False)
    monkeypatch.delenv("EA_PG_PASSWORD", raising=False)
    return root, profile


@pytest.fixture
def client(profiles):
    from hermes_cli import web_server

    with TestClient(web_server.app, raise_server_exceptions=False) as test_client:
        test_client.headers[web_server._SESSION_HEADER_NAME] = web_server._SESSION_TOKEN
        yield test_client


def test_settings_are_profile_scoped_and_never_return_password(client, profiles):
    _root, _profile = profiles
    resp = client.get("/api/energy-audit/settings", params={"profile": "audit"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["profile"] == "audit"
    assert data["values"]["host"] == "audit-host"
    assert data["sources"]["password"] == "environment"
    assert data["password_set"] is True
    assert "profile-env-secret" not in resp.text
    assert "profile-config-secret" not in resp.text
    assert "default-env-secret" not in resp.text

    default = client.get("/api/energy-audit/settings").json()
    assert default["values"]["host"] == "default-host"
    assert "default-env-secret" not in str(default)


def test_reset_removes_only_non_secret_profile_fields_and_keeps_passwords(client, profiles):
    _root, profile = profiles
    resp = client.post("/api/energy-audit/reset-settings", params={"profile": "audit"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["password_preserved"] is True
    raw = (profile / "config.yaml").read_text(encoding="utf-8")
    assert "host: audit-host" not in raw
    assert "port:" not in raw
    assert "database: audit-db" not in raw
    assert "user: audit-user" not in raw
    assert "sslmode:" not in raw
    assert "password: profile-config-secret" in raw
    assert "reference_dir: keep-profile" in raw
    assert "EA_PG_PASSWORD=profile-env-secret" in (profile / ".env").read_text(encoding="utf-8")
    assert body["env_overrides"] == []


def test_reset_reports_environment_fields_that_still_override_defaults(client, profiles, monkeypatch):
    _root, _profile = profiles
    monkeypatch.setenv("EA_PG_HOST", "env-host")

    resp = client.post("/api/energy-audit/reset-settings", params={"profile": "audit"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["env_overrides"] == ["host"]
    assert resp.json()["values"]["host"] == "env-host"


def test_save_writes_non_secrets_to_config_and_password_only_to_env(client, profiles):
    _root, profile = profiles
    resp = client.put(
        "/api/energy-audit/settings",
        params={"profile": "audit"},
        json={
            "host": "saved-host",
            "port": "5433",
            "database": "saved-db",
            "user": "saved-user",
            "sslmode": "require",
            "password": "typed-secret",
        },
    )

    assert resp.status_code == 200, resp.text
    assert "typed-secret" not in resp.text
    raw = (profile / "config.yaml").read_text(encoding="utf-8")
    assert "host: saved-host" in raw
    assert "password:" not in raw
    assert "reference_dir: keep-profile" in raw
    assert "EA_PG_PASSWORD=typed-secret" in (profile / ".env").read_text(encoding="utf-8")
    assert resp.json()["password_set"] is True
    assert resp.json()["sources"]["password"] == "environment"


def test_connection_test_maps_failures_to_safe_diagnostics(client, profiles, monkeypatch):
    _root, _profile = profiles
    from tools.energy_audit import db_config

    monkeypatch.setattr(
        db_config,
        "describe_pg_config",
        lambda: {
            "values": {"host": "db.internal", "port": "5432", "database": "audit", "user": "u", "sslmode": "prefer"},
            "sources": {"password": "environment"},
            "password_set": True,
            "env_vars": {},
            "env_overrides": [],
        },
    )
    monkeypatch.setattr(
        db_config,
        "get_pg_config",
        lambda: {"host": "db.internal", "port": "5432", "database": "audit", "user": "u",
                 "sslmode": "prefer", "password": "do-not-leak-this"},
    )

    def fail(**kwargs):
        assert kwargs["connect_timeout"] == 5
        raise OSError("could not connect to db.internal:5432 with password do-not-leak-this")

    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=fail))
    resp = client.post("/api/energy-audit/test-connection", params={"profile": "audit"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] is False
    assert data["code"] == "network"
    assert "do-not-leak-this" not in resp.text
    assert "db.internal:5432" not in resp.text
    assert data["stages"]["tcp"] in {"ok", "failed"}


def test_blank_password_keeps_config_and_env_secrets(client, profiles):
    _root, profile = profiles
    resp = client.put(
        "/api/energy-audit/settings",
        params={"profile": "audit"},
        json={
            "host": "saved-host",
            "port": "5433",
            "database": "saved-db",
            "user": "auditor",
            "sslmode": "require",
            "password": "",
        },
    )

    assert resp.status_code == 200, resp.text
    raw = (profile / "config.yaml").read_text(encoding="utf-8")
    assert "host: saved-host" in raw
    assert "password: profile-config-secret" in raw
    assert (profile / ".env").read_text(encoding="utf-8") == "EA_PG_PASSWORD=profile-env-secret\n"
    assert "profile-config-secret" not in resp.text
    assert "profile-env-secret" not in resp.text


def test_blank_password_does_not_drop_config_only_secret(client, profiles):
    _root, profile = profiles
    (profile / ".env").write_text("", encoding="utf-8")

    resp = client.put(
        "/api/energy-audit/settings",
        params={"profile": "audit"},
        json={
            "host": "saved-host",
            "port": "5433",
            "database": "saved-db",
            "user": "auditor",
            "sslmode": "require",
            "password": "   ",
        },
    )

    assert resp.status_code == 200, resp.text
    assert "password: profile-config-secret" in (profile / "config.yaml").read_text(encoding="utf-8")
    assert (profile / ".env").read_text(encoding="utf-8") == ""
    assert resp.json()["password_set"] is True
    assert resp.json()["sources"]["password"] == "profile_config"
    assert "profile-config-secret" not in resp.text


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        ("/api/energy-audit/projects", {"keyword": "法院"}),
        ("/api/energy-audit/generate", {"project_name": "法院"}),
        ("/api/energy-audit/imitate", {"project_name": "法院", "chapter": "第1章"}),
    ],
)
def test_existing_energy_audit_routes_execute_inside_requested_profile(
    client, profiles, monkeypatch, endpoint, body
):
    _root, profile = profiles
    from hermes_constants import get_hermes_home

    seen = []

    def fake(*args, **kwargs):
        seen.append(Path(get_hermes_home()).resolve())
        return {"ok": True}

    if endpoint.endswith("projects"):
        monkeypatch.setattr("tools.energy_audit_tool.rest_search_energy_audit_projects", fake)
    elif endpoint.endswith("generate"):
        monkeypatch.setattr("tools.energy_audit_tool.rest_generate_energy_audit_report", fake)
    else:
        monkeypatch.setattr(
            "tools.energy_audit_imitate_tool.rest_imitate_energy_audit_paragraph", fake
        )

    resp = client.post(endpoint, params={"profile": "audit"}, json=body)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}
    assert seen == [profile.resolve()]
