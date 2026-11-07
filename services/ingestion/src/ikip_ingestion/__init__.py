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
from ikip_ingestion.quality_report import DataQualityReport
from ikip_ingestion.retry import RetryDecision, RetryPolicy

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
    "DataQualityReport",
    "RetryDecision",
    "RetryPolicy",
]
