"""DEPRECATED: This module has moved to rag.general_kg. Import from there instead."""
import warnings
from rag.general_kg import *  # noqa: F403
warnings.warn(
    "Importing from knowledge_graph is deprecated. "
    "Use rag.general_kg instead.",
    DeprecationWarning, stacklevel=2,
)
