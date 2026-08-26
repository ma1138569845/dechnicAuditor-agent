"""Smoke the `/api/knowledge/*` surface the desktop knowledge page calls.

Isolates the SQLite knowledge store under a temp root so the developer's
real HERMES_HOME is never touched. LLM and Qdrant are stubbed so the test
proves route wiring and response envelopes, not live embedding/LLM quality.
"""

from __future__ import annotations

import rag.api.knowledge_base as kbmod
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_cli.knowledge_http import router


def _client(tmp_path, monkeypatch) -> TestClient:
    root = tmp_path / "kroot"
    root.mkdir()
    from hermes_constants import get_hermes_home

    vault = get_hermes_home() / "rag" / "wiki"
    vault.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(kbmod, "_DEFAULT_KNOWLEDGE_ROOT", root)
    monkeypatch.setattr(kbmod, "_KNOWLEDGE_BASE_ROOT", root)
    monkeypatch.setattr(kbmod, "_DB_PATH", root / ".knowledge_meta.db")
    monkeypatch.setattr(kbmod, "_DEFAULT_WIKI_VAULT", str(vault))
    kbmod._db_global_conn = None
    kbmod._qdrant_client_cache = None

    class _DummyExec:
        def submit(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(kbmod, "_get_executor", lambda: _DummyExec())

    def fake_llm(_messages, **kwargs):
        task = str(kwargs.get("task") or "")
        if "wiki" in task:
            return '{"title": "Test Wiki", "content": "# Test\\n\\nPipeline body."}'
        if "graph" in task:
            return (
                '{"entities": [{"name": "Boiler", "type": "equipment", "description": "x"}],'
                ' "relationships": [{"source": "Boiler", "target": "Steam", "type": "produces", "description": "y"}]}'
            )
        if "quality" in task or "eval" in task:
            return (
                '{"completeness": 80, "accuracy": 80, "structure": 80,'
                ' "readability": 80, "overall": 80, "suggestions": "ok"}'
            )
        return "这是一段测试摘要，覆盖文档核心内容。"

    monkeypatch.setattr(kbmod, "_call_llm_with_fallback", fake_llm)

    empty = {"results": [], "source": "none", "count": 0}
    monkeypatch.setattr(kbmod, "_search_qdrant_for_kb", lambda *a, **k: empty)
    monkeypatch.setattr(kbmod, "_search_graph_for_kb", lambda *a, **k: empty)
    monkeypatch.setattr(kbmod, "_search_wiki_for_kb", lambda *a, **k: empty)
    monkeypatch.setattr(kbmod, "_embed_doc_summary", lambda *a, **k: None)
    monkeypatch.setattr(kbmod, "_embed_kb_entities", lambda *a, **k: None)
    monkeypatch.setattr(kbmod, "_embed_kb_wiki_page", lambda *a, **k: None)
    monkeypatch.setattr(kbmod, "_ensure_qdrant_collection", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_knowledge_desktop_surface_is_usable(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    listed = client.get("/api/knowledge/bases")
    assert listed.status_code == 200
    assert "bases" in listed.json()

    created = client.post("/api/knowledge/bases", json={"name": "Smoke KB", "description": "probe"})
    assert created.status_code == 201, created.text
    kb_id = created.json()["id"]

    got = client.get(f"/api/knowledge/bases/{kb_id}")
    assert got.status_code == 200
    assert got.json()["name"] == "Smoke KB"

    stats = client.get(f"/api/knowledge/bases/{kb_id}/stats")
    assert stats.status_code == 200
    assert "total_documents" in stats.json()

    folder = client.post(f"/api/knowledge/bases/{kb_id}/folders", json={"name": "Reports"})
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]

    folders = client.get(f"/api/knowledge/bases/{kb_id}/folders?all=true")
    assert folders.status_code == 200
    assert any(item["id"] == folder_id for item in folders.json()["folders"])

    body = ("# Energy audit note\n\nSteam boiler consumption and office HVAC.\n" * 8).encode()
    uploaded = client.post(
        f"/api/knowledge/bases/{kb_id}/docs/upload?folder_id={folder_id}",
        files={"file": ("note.md", body, "text/markdown")},
    )
    assert uploaded.status_code == 201, uploaded.text
    payload = uploaded.json()
    doc = payload.get("document") or payload.get("existing") or payload
    doc_id = doc["id"]

    docs = client.get(f"/api/knowledge/bases/{kb_id}/docs")
    assert docs.status_code == 200
    assert docs.json()["total"] >= 1

    preview = client.get(f"/api/knowledge/docs/{doc_id}/preview")
    assert preview.status_code == 200
    assert "Steam boiler" in preview.json()["content"]

    vect = client.post(f"/api/knowledge/docs/{doc_id}/vectorize")
    assert vect.status_code == 200, vect.text
    assert vect.json().get("status") in {"processing", "pending", "completed"}

    jobs = client.get(f"/api/knowledge/bases/{kb_id}/vectorization-jobs")
    assert jobs.status_code == 200
    assert isinstance(jobs.json()["jobs"], list)

    summary = client.post(f"/api/knowledge/docs/{doc_id}/summary")
    assert summary.status_code == 200, summary.text
    assert summary.json().get("status") in {"completed", "completed_no_llm", "skipped"}

    db = kbmod._get_db()
    now = kbmod._now_iso()
    chunk_id = "chunk-smoke"
    db.execute(
        """
        INSERT INTO knowledge_chunks
        (id, doc_id, kb_id, chunk_index, chunk_type, content, char_count, is_enabled, created_at)
        VALUES (?, ?, ?, 0, 'text', ?, ?, 1, ?)
        """,
        (chunk_id, doc_id, kb_id, "Boiler produces steam for heating.", 34, now),
    )
    db.commit()

    chunks = client.get(f"/api/knowledge/docs/{doc_id}/chunks")
    assert chunks.status_code == 200
    assert chunks.json()["chunks"]

    patched = client.patch(f"/api/knowledge/chunks/{chunk_id}", json={"is_enabled": False})
    assert patched.status_code == 200, patched.text

    graph = client.post(f"/api/knowledge/docs/{doc_id}/graph")
    assert graph.status_code == 200, graph.text

    db.execute(
        "UPDATE knowledge_documents SET parse_status = ? WHERE id = ?",
        ("completed", doc_id),
    )
    db.commit()

    wiki = client.post(f"/api/knowledge/docs/{doc_id}/wiki", json={"curate": False})
    assert wiki.status_code == 200, wiki.text
    wiki_id = wiki.json().get("wiki_id") or wiki.json().get("id")
    assert wiki_id

    pages = client.get(f"/api/knowledge/bases/{kb_id}/wiki")
    assert pages.status_code == 200
    assert pages.json()["pages"]

    pending = client.get(f"/api/knowledge/bases/{kb_id}/wiki?review_status=pending")
    assert pending.status_code == 200

    page = client.get(f"/api/knowledge/wiki/{wiki_id}")
    assert page.status_code == 200
    assert page.json()["title"]

    reviewed = client.patch(f"/api/knowledge/wiki/{wiki_id}/review", json={"review_status": "approved"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "approved"

    quality = client.post(f"/api/knowledge/wiki/{wiki_id}/evaluate-quality")
    assert quality.status_code == 200, quality.text
    assert "quality_score" in quality.json()

    entities = client.get(f"/api/knowledge/bases/{kb_id}/entities")
    assert entities.status_code == 200
    rels = client.get(f"/api/knowledge/bases/{kb_id}/relationships")
    assert rels.status_code == 200

    for mode in ("vector", "wiki", "graph", "unified"):
        search = client.post(
            f"/api/knowledge/bases/{kb_id}/search",
            json={"query": "boiler", "limit": 5, "mode": mode},
        )
        assert search.status_code == 200, (mode, search.text)
        assert "results" in search.json()

    folder_wiki = client.post(
        f"/api/knowledge/bases/{kb_id}/folders/{folder_id}/wiki",
        json={"title": "", "curate": False},
    )
    assert folder_wiki.status_code == 200, folder_wiki.text

    bulk = client.post(f"/api/knowledge/bases/{kb_id}/bulk-wiki", json={"doc_ids": [doc_id]})
    assert bulk.status_code == 200, bulk.text
    assert bulk.json().get("job_id")

    hierarchical = client.post(
        f"/api/knowledge/bases/{kb_id}/folders/{folder_id}/hierarchical-wiki",
        json={"curate": False},
    )
    assert hierarchical.status_code in {200, 400}, hierarchical.text

    curate = client.post(
        f"/api/knowledge/bases/{kb_id}/curate",
        json={"review_status": "approved"},
    )
    assert curate.status_code in {200, 400}, curate.text

    curation_jobs = client.get(f"/api/knowledge/bases/{kb_id}/curation-jobs")
    assert curation_jobs.status_code == 200
    assert isinstance(curation_jobs.json()["jobs"], list)

    deleted_chunk = client.delete(f"/api/knowledge/chunks/{chunk_id}")
    assert deleted_chunk.status_code == 200, deleted_chunk.text

    rebuild = client.post(f"/api/knowledge/bases/{kb_id}/rebuild", json={})
    assert rebuild.status_code == 200, rebuild.text

    bulk_delete = client.post(
        f"/api/knowledge/bases/{kb_id}/bulk-delete",
        json={"doc_ids": [doc_id]},
    )
    assert bulk_delete.status_code == 200, bulk_delete.text

    folder_del = client.delete(f"/api/knowledge/bases/{kb_id}/folders/{folder_id}")
    assert folder_del.status_code == 200

    kb_del = client.delete(f"/api/knowledge/bases/{kb_id}")
    assert kb_del.status_code == 200

    if kbmod._db_global_conn is not None:
        kbmod._db_global_conn.close()
        kbmod._db_global_conn = None
