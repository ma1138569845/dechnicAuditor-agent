"""DEPRECATED: This module has moved to rag.knowledge_graph.knowledge_schema. Import from there instead."""
import warnings
from rag.knowledge_graph.knowledge_schema import *  # noqa: F403
warnings.warn(
    "Importing from tools.energy_audit.knowledge_schema is deprecated. "
    "Use rag.knowledge_graph.knowledge_schema instead.",
    DeprecationWarning, stacklevel=2,
)
