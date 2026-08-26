"""
Shared embedding module for the energy audit knowledge base system.

Provides a single, cached DashScope text-embedding-v3 client used by all
downstream modules (knowledge_base, rag_search, energy_audit_search,
energy_audit_importer).  Replaces four independent implementations that each
created a new OpenAI client on every call.

Usage:
    from rag.embedding import embed_texts, embed_query
    vectors = embed_texts(["文本1", "文本2"])          # batch
    vector  = embed_query("单个查询")                   # single
"""

from __future__ import annotations

import logging
import os
import time
from typing import List

logger = logging.getLogger(__name__)

# ── config ──────────────────────────────────────────────────────

_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_EMBED_MODEL = "text-embedding-v3"
_EMBED_DIM = 1024  # text-embedding-v3 default
_BATCH_SIZE = 10   # DashScope batch limit

# ── lazy client singleton ───────────────────────────────────────

_client = None


def _load_api_key() -> str:
    """Resolve DASHSCOPE_API_KEY from the unified RAG config (.env under HERMES_HOME)."""
    from rag.config import dashscope_api_key

    return dashscope_api_key()


def get_embedding_client():
    """Return a module-level cached OpenAI client for DashScope embeddings.

    The client and its underlying httpx connection pool are reused across
    all calls, avoiding the overhead of creating a new connection per request.
    """
    global _client
    if _client is not None:
        return _client
    api_key = _load_api_key()
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not set. "
            "Export it or add it to ~/.hermes/.env."
        )
    from openai import OpenAI
    _client = OpenAI(api_key=api_key, base_url=_DASHSCOPE_BASE_URL)
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts in batches.

    Returns a list of vectors (each 1024-dim) in the same order as the input.
    """
    if not texts:
        return []
    client = get_embedding_client()
    vectors: List[List[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i:i + _BATCH_SIZE]
        resp = client.embeddings.create(model=_EMBED_MODEL, input=batch)
        # response.data may not be ordered by input index; sort by index
        vectors.extend(
            d.embedding for d in sorted(resp.data, key=lambda x: x.index)
        )
    return vectors


def embed_query(text: str) -> List[float]:
    """Embed a single query string. Convenience wrapper around embed_texts."""
    return embed_texts([text])[0]
