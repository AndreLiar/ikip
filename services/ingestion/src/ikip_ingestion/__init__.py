"""IKIP ingestion service — source connectors + ingestion logic (Dagster-free core)."""

from ikip_ingestion.connectors import (
    HttpSourceConnector,
    SourceConfig,
    SourceConnector,
    SourceDocument,
    UnauthorizedSourceError,
)
from ikip_ingestion.ingest import (
    IngestResult,
    InMemorySeenStore,
    SeenStore,
    ingest_documents,
)

__all__ = [
    "HttpSourceConnector",
    "SourceConfig",
    "SourceConnector",
    "SourceDocument",
    "UnauthorizedSourceError",
    "InMemorySeenStore",
    "IngestResult",
    "SeenStore",
    "ingest_documents",
]
