"""DEPRECATED: This module has moved to rag.ingestion.ingest_reports. Import from there instead."""
import warnings
from rag.ingestion.ingest_reports import *  # noqa: F403
warnings.warn(
    "Importing from tools.energy_audit.ingest_reports is deprecated. "
    "Use rag.ingestion.ingest_reports instead.",
    DeprecationWarning, stacklevel=2,
)
