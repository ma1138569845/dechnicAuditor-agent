import importlib.util
import sys
import types
from pathlib import Path

import pytest


DB_CONFIG_PATH = Path(__file__).resolve().parents[1] / "db_config.py"


def load_db_config():
    spec = importlib.util.spec_from_file_location("_test_db_config", DB_CONFIG_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_secret_scope(monkeypatch, secrets):
    agent_package = types.ModuleType("agent")
    secret_scope = types.ModuleType("agent.secret_scope")
    secret_scope.get_secret = lambda name, default=None: secrets.get(name, default)
    agent_package.secret_scope = secret_scope
    monkeypatch.setitem(sys.modules, "agent", agent_package)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", secret_scope)


def remove_agent_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", None)


def test_profile_scoped_password_takes_precedence_over_process_environment(monkeypatch):
    install_secret_scope(monkeypatch, {"EA_PG_PASSWORD": "profile-password"})
    monkeypatch.setenv("EA_PG_PASSWORD", "process-password")

    config = load_db_config().get_pg_config()

    assert config["password"] == "profile-password"


def test_standalone_package_reads_password_from_process_environment(monkeypatch):
    remove_agent_package(monkeypatch)
    monkeypatch.setenv("EA_PG_PASSWORD", "standalone-password")

    config = load_db_config().get_pg_config()

    assert config["password"] == "standalone-password"


def test_unscoped_secret_error_is_not_swallowed(monkeypatch):
    class UnscopedSecretError(RuntimeError):
        pass

    install_secret_scope(monkeypatch, {})

    def fail_without_scope(name, default=None):
        raise UnscopedSecretError(name)

    sys.modules["agent.secret_scope"].get_secret = fail_without_scope

    with pytest.raises(UnscopedSecretError):
        load_db_config().get_pg_config()


def test_non_password_process_override_remains_visible_with_secret_scope(monkeypatch):
    install_secret_scope(monkeypatch, {"EA_PG_PASSWORD": "profile-password"})
    monkeypatch.setenv("EA_PG_HOST", "192.0.2.10")

    config = load_db_config().get_pg_config()

    assert config["host"] == "192.0.2.10"
    assert config["password"] == "profile-password"


def test_describe_pg_config_reports_password_without_exposing_it(monkeypatch):
    install_secret_scope(monkeypatch, {"EA_PG_PASSWORD": "profile-password"})

    description = load_db_config().describe_pg_config()

    assert description["password_set"] is True
    assert description["sources"]["password"] == "environment"
    assert "password" not in description["values"]
    assert "profile-password" not in repr(description)


def test_hermes_yaml_parser_is_preferred_when_available(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "agent", None)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", None)
    monkeypatch.delenv("EA_PG_PASSWORD", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    hermes_yaml = types.ModuleType("hermes_yaml")
    hermes_yaml.safe_load = lambda stream: {
        "energy_audit": {"database": {"password": "hermes-password"}}
    }
    monkeypatch.setitem(sys.modules, "hermes_yaml", hermes_yaml)

    module = load_db_config()
    monkeypatch.setattr(module, "_hermes_config_path", lambda: config_path)
    monkeypatch.setattr(module, "_LOCAL_CONFIG_YAML", tmp_path / "missing.yaml")

    assert module.get_pg_config()["password"] == "hermes-password"


def test_local_yaml_fallback_works_without_hermes_yaml(monkeypatch, tmp_path):
    remove_agent_package(monkeypatch)
    monkeypatch.delenv("EA_PG_PASSWORD", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.setitem(sys.modules, "hermes_yaml", None)

    local_config = tmp_path / "config.yaml"
    local_config.write_text(
        "database:\n  password: standalone-yaml-password\n",
        encoding="utf-8",
    )

    module = load_db_config()
    monkeypatch.setattr(module, "_LOCAL_CONFIG_YAML", local_config)
    monkeypatch.setattr(module, "_hermes_config_path", lambda: None)

    assert module.get_pg_config()["password"] == "standalone-yaml-password"


def test_describe_file_config_reports_environment_source(monkeypatch):
    monkeypatch.setenv("EA_FILE_BASE_URL", "http://files.example/base/")

    description = load_db_config().describe_file_config()

    assert description == {
        "base_url": "http://files.example/base",
        "source": "environment",
        "environment_override": True,
    }
