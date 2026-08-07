"""DEPRECATED: This module has moved to rag.memory_storage. Import from there instead."""
import warnings
from rag.memory_storage import *  # noqa: F403
warnings.warn(
    "Importing from memory_storage is deprecated. "
    "Use rag.memory_storage instead.",
    DeprecationWarning, stacklevel=2,
)
