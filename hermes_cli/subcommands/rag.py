"""``hermes rag`` subcommand parser.

Interactive RAG knowledge-base configuration wizard.
Guides the user through Qdrant, embedding, LLM, and storage setup.
"""

from __future__ import annotations

from typing import Callable


def build_rag_parser(subparsers, *, cmd_rag: Callable) -> None:
    """Attach the ``rag`` subcommand to ``subparsers``."""
    rag_parser = subparsers.add_parser(
        "rag",
        help="Configure RAG knowledge base (Qdrant, embedding, LLM, storage)",
        description="Interactively configure the RAG knowledge-base system: "
        "remote Qdrant, embedding/LLM models, local directories, and Qdrant collections.",
    )
    rag_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Apply defaults without prompting (useful for scripting).",
    )
    rag_parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant connectivity check and collection creation.",
    )
    rag_parser.add_argument(
        "--qdrant-host",
        default=None,
        help="Qdrant server host (default: $QDRANT_HOST or 127.0.0.1).",
    )
    rag_parser.add_argument(
        "--qdrant-port",
        type=int,
        default=None,
        help="Qdrant gRPC port (default: 6334).",
    )
    rag_parser.add_argument(
        "--qdrant-api-key",
        default=None,
        help="Qdrant API key (leave empty for no auth).",
    )
    rag_parser.add_argument(
        "--embedding-model",
        default=None,
        help="Embedding model name (default: dashscope/text-embedding-v3).",
    )
    rag_parser.add_argument(
        "--dashscope-api-key",
        default=None,
        help="DashScope API key for embedding.",
    )
    rag_parser.add_argument(
        "--llm-model",
        default=None,
        help="LLM model for summaries/wiki (default: deepseek-v4-flash).",
    )
    rag_parser.add_argument(
        "--deepseek-api-key",
        default=None,
        help="DeepSeek API key for LLM tasks.",
    )
    rag_parser.add_argument(
        "--deepseek-api-base",
        default=None,
        help="DeepSeek API base URL (default: https://api.deepseek.com/v1).",
    )
    rag_parser.set_defaults(func=cmd_rag)
