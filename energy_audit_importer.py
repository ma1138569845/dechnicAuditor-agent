"""DEPRECATED: This module has moved to rag.energy_audit_importer. Import from there instead."""
import warnings
from rag.energy_audit_importer import *  # noqa: F403
warnings.warn(
    "Importing from energy_audit_importer is deprecated. "
    "Use rag.energy_audit_importer instead.",
    DeprecationWarning, stacklevel=2,
)
