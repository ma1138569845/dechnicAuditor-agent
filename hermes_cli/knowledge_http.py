"""HTTP routes for the RAG knowledge base, mounted by ``web_server``.

Kept out of ``web_server.py`` so the knowledge-base surface stays in the RAG
layer.  Each handler lazily imports ``rag.api.knowledge_base`` (matching the
vendored webui's ``routes.py`` convention) so the heavy Qdrant/embedding
dependencies are only loaded on first use, not at web-server startup.

These endpoints are consumed by the hermes-studio-vue BFF via a transparent
proxy; response envelopes (``bases`` / ``folders`` / ``documents`` / ``pages`` /
``entities`` / ``relationships`` / ``results``) match that frontend's contract.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/knowledge")


def _kb():
    from rag.api import knowledge_base as kb

    return kb


def _http_error(exc: Exception) -> HTTPException:
    """Map a rag ValueError to a 404 (unknown id) or 400 (bad input)."""
    message = str(exc)
    status = 404 if "not found" in message.lower() else 400
    return HTTPException(status_code=status, detail=message)


# ── Knowledge Base CRUD ────────────────────────────────────────────────


@router.get("/bases")
def list_bases():
    return {"bases": _kb().list_knowledge_bases()}


@router.post("/bases", status_code=201)
async def create_base(request: Request):
    kb = _kb()
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        created = kb.create_knowledge_base(
            name=name,
            description=(body.get("description") or "").strip(),
            kb_type=body.get("kb_type") or "energy_audit",
            root_path=body.get("root_path"),
            qdrant_collection=body.get("qdrant_collection"),
            embedding_model=body.get("embedding_model") or "dashscope/text-embedding-v3",
            chunking_config=body.get("chunking_config"),
            indexing_strategy=body.get("indexing_strategy"),
        )
        # Return the full row (is_system / updated_at / stats) so the frontend
        # receives the same shape it gets from the list endpoint.
        return kb.get_knowledge_base(created["id"])
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/bases/{kb_id}")
def get_base(kb_id: str):
    try:
        return _kb().get_knowledge_base(kb_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.delete("/bases/{kb_id}")
def delete_base(kb_id: str):
    try:
        return _kb().delete_knowledge_base(kb_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Folders ────────────────────────────────────────────────────────────


def _folder_id(raw: str | None) -> str | None:
    if not raw or raw == "root":
        return None
    return raw


async def _json_body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/bases/{kb_id}/folders")
def list_folders(
    kb_id: str,
    parent_id: str | None = Query(default=None),
    include_all: bool = Query(default=False, alias="all"),
):
    kb = _kb()
    if include_all:
        collected: list = []

        def walk(pid: str | None) -> None:
            kids = kb.list_knowledge_folders(kb_id, pid)
            for folder in kids:
                collected.append(folder)
                walk(folder["id"])

        walk(None)
        return {"folders": collected}
    return {"folders": kb.list_knowledge_folders(kb_id, parent_id)}


@router.post("/bases/{kb_id}/folders", status_code=201)
async def create_folder(kb_id: str, request: Request):
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        return _kb().create_knowledge_folder_v2(kb_id, name, body.get("parent_id"))
    except ValueError as exc:
        raise _http_error(exc)


@router.delete("/bases/{kb_id}/folders/{folder_id}")
def delete_folder(kb_id: str, folder_id: str):
    try:
        return _kb().delete_knowledge_folder_v2(kb_id, folder_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Documents ──────────────────────────────────────────────────────────


@router.get("/bases/{kb_id}/docs")
def list_docs(
    kb_id: str,
    page: int = Query(default=1),
    page_size: int = Query(default=20),
    keyword: str | None = Query(default=None),
    file_type: str | None = Query(default=None),
    parse_status: str | None = Query(default=None),
    folder_id: str | None = Query(default=None),
):
    result = _kb().list_knowledge_documents(
        kb_id,
        {
            "page": page,
            "page_size": page_size,
            "keyword": keyword,
            "file_type": file_type,
            "parse_status": parse_status,
            "folder_id": folder_id,
        },
    )
    return {
        "documents": result.get("data", []),
        "total": result.get("total", 0),
        "page": result.get("page", page),
        "page_size": result.get("page_size", page_size),
    }


@router.get("/docs/{doc_id}")
def get_doc(doc_id: str):
    try:
        return _kb().get_knowledge_document(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/bases/{kb_id}/docs/upload", status_code=201)
async def upload_doc(kb_id: str, request: Request, folder_id: str | None = Query(default=None)):
    content_type = request.headers.get("content-type", "")
    raw_body = await request.body()
    try:
        return _kb().upload_knowledge_file_v2(kb_id, folder_id, raw_body, content_type)
    except ValueError as exc:
        raise _http_error(exc)


@router.delete("/bases/{kb_id}/docs/{doc_id}")
def delete_doc(kb_id: str, doc_id: str):
    try:
        return _kb().delete_knowledge_document(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/docs/{doc_id}/chunks")
def get_doc_chunks(doc_id: str):
    try:
        return _kb().list_document_chunks(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Search ─────────────────────────────────────────────────────────────


@router.post("/bases/{kb_id}/search")
async def search(kb_id: str, request: Request):
    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    return _kb().search_knowledge_v2(
        kb_id,
        query,
        top_k=body.get("limit") or body.get("top_k") or 10,
        mode=body.get("mode") or "vector",
        folder_id=body.get("folder_id"),
        file_type=body.get("file_type"),
        doc_id=body.get("doc_id"),
        score_threshold=body.get("score_threshold"),
    )


# ── Wiki ───────────────────────────────────────────────────────────────


@router.get("/bases/{kb_id}/wiki")
def list_wiki(
    kb_id: str,
    top_k: int = Query(default=100),
    review_status: str | None = Query(default=None),
):
    return {
        "pages": _kb().list_kb_wiki_pages(kb_id, top_k, review_status=review_status).get("pages", []),
    }


@router.get("/wiki/{wiki_id}")
def get_wiki(wiki_id: str):
    try:
        return _kb().get_wiki_page(wiki_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Knowledge Graph ────────────────────────────────────────────────────


@router.get("/bases/{kb_id}/entities")
def list_entities(kb_id: str, top_k: int = Query(default=100)):
    return {"entities": _kb().list_kb_entities(kb_id, top_k).get("entities", [])}


@router.get("/bases/{kb_id}/relationships")
def list_relationships(kb_id: str, top_k: int = Query(default=200)):
    return {"relationships": _kb().list_kb_relationships(kb_id, top_k).get("relationships", [])}


# ── Stats ──────────────────────────────────────────────────────────────


@router.get("/bases/{kb_id}/stats")
def get_stats(kb_id: str):
    try:
        return _kb()._get_kb_stats(kb_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Document pipeline (vectorize / summary / wiki / graph) ───────────


@router.get("/docs/{doc_id}/preview")
def preview_doc(doc_id: str, max_chars: int = Query(default=120_000)):
    try:
        return _kb().get_knowledge_file_preview_v2(doc_id, max_chars=max_chars)
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/docs/{doc_id}/file")
def download_doc(doc_id: str):
    try:
        path, mime, name = _kb().get_document_file(doc_id)
        return FileResponse(path, media_type=mime, filename=name)
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/docs/{doc_id}/file-payload")
def file_payload(doc_id: str, max_bytes: int = Query(default=15_000_000, ge=1, le=50_000_000)):
    try:
        return _kb().get_document_file_payload(doc_id, max_bytes=max_bytes)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/docs/{doc_id}/vectorize")
@router.post("/docs/{doc_id}/reparse")
def vectorize_doc(doc_id: str):
    try:
        return _kb().start_vectorization_v2(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/docs/{doc_id}/summary")
def summarize_doc(doc_id: str):
    try:
        return _kb().start_summary_build(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/docs/{doc_id}/graph")
def graph_doc(doc_id: str):
    try:
        return _kb().start_graph_build(doc_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/docs/{doc_id}/wiki")
async def wiki_doc(doc_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().start_wiki_build(doc_id, curate=bool(body.get("curate")))
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        return _kb().get_vectorization_job(job_id)
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/bases/{kb_id}/vectorization-jobs")
def list_vec_jobs(kb_id: str, status: str | None = Query(default=None)):
    return {"jobs": _kb().list_vectorization_jobs(kb_id, status=status)}


@router.post("/bases/{kb_id}/rebuild")
async def rebuild_base(kb_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().rebuild_knowledge_base(kb_id, body.get("targets"))
    except ValueError as exc:
        raise _http_error(exc)


# ── Wiki / curation jobs ─────────────────────────────────────────────


@router.post("/bases/{kb_id}/folders/{folder_id}/wiki")
async def wiki_folder(kb_id: str, folder_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().start_folder_wiki_build(
            kb_id,
            _folder_id(folder_id),
            title=body.get("title") or "",
            curate=bool(body.get("curate")),
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/bases/{kb_id}/hierarchical-wiki")
@router.post("/bases/{kb_id}/folders/{folder_id}/hierarchical-wiki")
async def hierarchical_wiki(kb_id: str, request: Request, folder_id: str | None = None):
    body = await _json_body(request)
    try:
        return _kb().start_hierarchical_wiki_build(
            kb_id,
            folder_id=_folder_id(folder_id),
            curate=bool(body.get("curate")),
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/bases/{kb_id}/curate")
@router.post("/bases/{kb_id}/folders/{folder_id}/curate")
async def curate_wiki(kb_id: str, request: Request, folder_id: str | None = None):
    body = await _json_body(request)
    try:
        return _kb().start_global_curation(
            kb_id,
            folder_id=_folder_id(folder_id),
            page_ids=body.get("page_ids") or None,
            review_status=body.get("review_status") or None,
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/bases/{kb_id}/bulk-wiki")
@router.post("/bases/{kb_id}/folders/{folder_id}/bulk-wiki")
async def bulk_wiki(kb_id: str, request: Request, folder_id: str | None = None):
    body = await _json_body(request)
    try:
        return _kb().start_bulk_wiki_generation(
            kb_id,
            folder_id=_folder_id(folder_id),
            doc_ids=body.get("doc_ids") or None,
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/bases/{kb_id}/bulk-delete")
async def bulk_delete(kb_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().batch_delete_knowledge_documents(kb_id, body.get("doc_ids") or [])
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/bases/{kb_id}/curation-jobs")
def list_curation(kb_id: str, status: str | None = Query(default=None), limit: int = Query(default=50)):
    try:
        return {"jobs": _kb().list_curation_jobs(kb_id, status=status, limit=limit)}
    except ValueError as exc:
        raise _http_error(exc)


@router.get("/bases/{kb_id}/curation-jobs/{job_id}")
def get_curation(kb_id: str, job_id: str):
    job = _kb().get_curation_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job": job}


@router.patch("/wiki/{wiki_id}/review")
async def review_wiki(wiki_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().update_wiki_review_status(wiki_id, body.get("review_status") or "")
    except ValueError as exc:
        raise _http_error(exc)


@router.post("/wiki/{wiki_id}/evaluate-quality")
@router.patch("/wiki/{wiki_id}/evaluate-quality")
def evaluate_wiki(wiki_id: str):
    try:
        return _kb().start_wiki_quality_eval(wiki_id)
    except ValueError as exc:
        raise _http_error(exc)


# ── Chunks ───────────────────────────────────────────────────────────


@router.put("/chunks/{chunk_id}")
@router.patch("/chunks/{chunk_id}")
async def update_chunk(chunk_id: str, request: Request):
    body = await _json_body(request)
    try:
        return _kb().update_knowledge_chunk(
            chunk_id,
            content=body.get("content"),
            is_enabled=body.get("is_enabled"),
        )
    except ValueError as exc:
        raise _http_error(exc)


@router.delete("/chunks/{chunk_id}")
def delete_chunk(chunk_id: str):
    try:
        return _kb().delete_knowledge_chunk(chunk_id)
    except ValueError as exc:
        raise _http_error(exc)
