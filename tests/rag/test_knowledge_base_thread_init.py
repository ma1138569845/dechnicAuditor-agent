"""Regression coverage for knowledge-base initialization on worker threads."""

from __future__ import annotations

import threading


def test_worker_thread_creates_default_knowledge_bases(tmp_path, monkeypatch):
    from rag.api import knowledge_base as kb

    root = tmp_path / "rag-data"
    root.mkdir()
    monkeypatch.setattr(kb, "_DEFAULT_KNOWLEDGE_ROOT", root)
    monkeypatch.setattr(kb, "_RAG_DATA_ROOT", root)
    monkeypatch.setattr(kb, "_DB_PATH", root / ".knowledge_meta.db")
    monkeypatch.setattr(kb, "_db_global_conn", None)
    monkeypatch.setattr(kb, "_db_local", threading.local())

    result: dict[str, list[str]] = {}

    def read_defaults() -> None:
        conn = kb._get_db()
        rows = conn.execute("SELECT id FROM knowledge_bases ORDER BY id").fetchall()
        result["ids"] = [row["id"] for row in rows]

    worker = threading.Thread(target=read_defaults)
    worker.start()
    worker.join(timeout=10)

    assert not worker.is_alive()
    assert result["ids"] == sorted(kb._SYSTEM_KB_IDS)
