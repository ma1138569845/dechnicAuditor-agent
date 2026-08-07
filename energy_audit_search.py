"""DEPRECATED: This module has moved to rag.energy_audit_search. Import from there instead."""
import warnings
from rag.energy_audit_search import *  # noqa: F403
warnings.warn(
    "Importing from energy_audit_search is deprecated. "
    "Use rag.energy_audit_search instead.",
    DeprecationWarning, stacklevel=2,
)
