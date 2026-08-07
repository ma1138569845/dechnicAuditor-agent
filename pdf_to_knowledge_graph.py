"""DEPRECATED: This module has moved to rag.pdf_to_knowledge_graph. Import from there instead."""
import warnings
from rag.pdf_to_knowledge_graph import *  # noqa: F403
warnings.warn(
    "Importing from pdf_to_knowledge_graph is deprecated. "
    "Use rag.pdf_to_knowledge_graph instead.",
    DeprecationWarning, stacklevel=2,
)
