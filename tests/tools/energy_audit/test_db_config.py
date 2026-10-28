"""Energy-audit PostgreSQL resolution and profile isolation contracts."""

from pathlib import Path

import pytest

from tools.energy_audit import db_config


def _write_config(home: Path, body: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(body, encoding="utf-8")


def test_describe_reports_per_field_sources_without_exposing_password(tmp_path, monkeypatch):
    home = tmp_path / "profile-a"
    _write_config(
        home,
        "energy_audit:\n"
        "  database:\n"
        "    host: config-host\n"
        "    password: config-secret\n",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("EA_PG_PORT", "6543")
    monkeypatch.setenv("EA_PG_PASSWORD", "env-secret")
    monkeypatch.delenv("DB_HOST", raising=False)

    result = db_config.describe_pg_config()

    assert result["values"] == {
        "host": "config-host",
        "port": "6543",
        "database": "dc_energy_audit2",
        "user": "postgres",
        "sslmode": "prefer",
    }
    assert result["sources"] == {
        "host": "profile_config",
        "port": "environment",
        "database": "package_config",
        "user": "package_config",
        "sslmode": "package_config",
        "password": "environment",
    }
    assert result["password_set"] is True
    assert "env-secret" not in repr(result)
    assert "config-secret" not in repr(result)


def test_ea_password_wins_over_legacy_db_password(monkeypatch):
    monkeypatch.setenv("EA_PG_PASSWORD", "new-secret")
    monkeypatch.setenv("DB_PASSWORD", "legacy-secret")

    resolved = db_config.get_pg_config()

    assert resolved["password"] == "new-secret"


def test_profile_scope_password_does_not_fall_back_to_launch_environment(tmp_path, monkeypatch):
    home = tmp_path / "profile-b"
    home.mkdir()
    monkeypatch.setenv("EA_PG_PASSWORD", "launch-profile-secret")

    from agent.secret_scope import reset_secret_scope, set_secret_scope

    token = set_secret_scope({"EA_PG_PASSWORD": "profile-b-secret"}, profile_home=str(home))
    try:
        assert db_config.get_pg_config()["password"] == "profile-b-secret"
    finally:
        reset_secret_scope(token)


def test_scoped_profile_keeps_non_secret_process_override_but_not_password(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setenv("EA_PG_HOST", "process-host")
    monkeypatch.setenv("EA_PG_PASSWORD", "process-secret")

    from agent.secret_scope import reset_secret_scope, set_secret_scope

    token = set_secret_scope({}, profile_home=str(home))
    try:
        described = db_config.describe_pg_config()
    finally:
        reset_secret_scope(token)

    assert described["values"]["host"] == "process-host"
    assert described["env_overrides"] == ["host"]
    assert "password" not in described["sources"]


def test_missing_password_raises_actionable_error(monkeypatch):
    monkeypatch.delenv("EA_PG_PASSWORD", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="EA_PG_PASSWORD"):
        db_config.get_pg_config()
