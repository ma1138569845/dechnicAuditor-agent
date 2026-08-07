"""DEPRECATED: This module has moved to rag.rag_energy_qa. Import from there instead."""
import warnings
from rag.rag_energy_qa import *  # noqa: F403
warnings.warn(
    "Importing from rag_energy_qa is deprecated. "
    "Use rag.rag_energy_qa instead.",
    DeprecationWarning, stacklevel=2,
)
