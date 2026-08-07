"""DEPRECATED: This module has moved to rag.knowledge_graph.kg_visualizer. Import from there instead."""
import warnings
from rag.knowledge_graph.kg_visualizer import *  # noqa: F403
warnings.warn(
    "Importing from tools.energy_audit.kg_visualizer is deprecated. "
    "Use rag.knowledge_graph.kg_visualizer instead.",
    DeprecationWarning, stacklevel=2,
)
