"""Behavior of the unified knowledge-base / RAG config resolver."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rag import config as rag_config


@pytest.fixture(autouse=True)
def _reset_rag_config(monkeypatch, tmp_path):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    for key in (
        "QDRANT_HOST",
        "QDRANT_PORT",
        "QDRANT_HTTP_PORT",
        "QDRANT_URL",
        "QDRANT_COLLECTION",
        "HERMES_KNOWLEDGE_ROOT",
        "HERMES_WIKI_VAULT",
        "SUMMARY_MODEL",
        "DEEPSEEK_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(rag_config, "_package_energy_audit_yaml", lambda: {})
    rag_config.clear_cache()
    rag_config._DOTENV_LOADED = False
    rag_config._CACHE_TOKEN = None
    yield
    rag_config.clear_cache()
    rag_config._DOTENV_LOADED = False
    rag_config._CACHE_TOKEN = None


def _write_config(home: Path, payload: dict) -> None:
    path = home / "config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


def test_defaults_are_localhost_and_hermes_home_paths(tmp_path):
    home = Path(tmp_path / "hermes-home")
    assert rag_config.qdrant_host() == "127.0.0.1"
    assert rag_config.qdrant_grpc_port() == 6334
    assert rag_config.qdrant_http_port() == 6333
    assert rag_config.qdrant_http_url() == "http://127.0.0.1:6333"
    assert rag_config.knowledge_root() == home / "rag" / "data"
    assert rag_config.wiki_vault() == str(home / "rag" / "wiki")
    assert rag_config.summary_model() == "deepseek-v4-flash"


def test_config_yaml_knowledge_base_wins_over_defaults(tmp_path):
    home = Path(tmp_path / "hermes-home")
    _write_config(
        home,
        {
            "knowledge_base": {
                "qdrant_host": "10.10.2.55",
                "qdrant_port": "6334",
                "qdrant_http_port": 6333,
                "summary_model": "deepseek-v4-pro",
            }
        },
    )
    rag_config.clear_cache()
    assert rag_config.qdrant_host() == "10.10.2.55"
    assert rag_config.qdrant_grpc_port() == 6334
    assert rag_config.summary_model() == "deepseek-v4-pro"
    assert rag_config.qdrant_http_url() == "http://10.10.2.55:6333"


def test_env_overrides_config_yaml(tmp_path, monkeypatch):
    home = Path(tmp_path / "hermes-home")
    _write_config(home, {"knowledge_base": {"qdrant_host": "10.10.2.55"}})
    monkeypatch.setenv("QDRANT_HOST", "127.0.0.1")
    rag_config.clear_cache()
    assert rag_config.qdrant_host() == "127.0.0.1"


def test_legacy_energy_audit_rag_alias_when_knowledge_base_missing(tmp_path):
    home = Path(tmp_path / "hermes-home")
    _write_config(
        home,
        {
            "energy_audit": {
                "rag": {
                    "qdrant_url": "http://10.9.9.9:6333",
                    "deepseek_model": "deepseek-v4-flash",
                    "collection_name": "knowledge_segment_qwen",
                }
            }
        },
    )
    rag_config.clear_cache()
    assert rag_config.qdrant_host() == "10.9.9.9"
    assert rag_config.qdrant_http_port() == 6333
    assert rag_config.energy_audit_collection() == "knowledge_segment_qwen"


def test_knowledge_base_wins_over_legacy_energy_audit_rag(tmp_path):
    home = Path(tmp_path / "hermes-home")
    _write_config(
        home,
        {
            "knowledge_base": {"qdrant_host": "10.10.2.55"},
            "energy_audit": {"rag": {"qdrant_url": "http://1.2.3.4:6333"}},
        },
    )
    rag_config.clear_cache()
    assert rag_config.qdrant_host() == "10.10.2.55"


def test_config_yaml_write_is_picked_up_without_clear_cache(tmp_path):
    home = Path(tmp_path / "hermes-home")
    assert rag_config.qdrant_host() == "127.0.0.1"
    _write_config(home, {"knowledge_base": {"qdrant_host": "10.10.2.55"}})
    assert rag_config.qdrant_host() == "10.10.2.55"
