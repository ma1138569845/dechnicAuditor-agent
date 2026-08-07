"""DEPRECATED: This module has moved to rag.knowledge_graph.energy_kg. Import from there instead."""
import warnings
from rag.knowledge_graph.energy_kg import *  # noqa: F403
warnings.warn(
    "Importing from tools.energy_audit.energy_kg is deprecated. "
    "Use rag.knowledge_graph.energy_kg instead.",
    DeprecationWarning, stacklevel=2,
)
