"""Database layer: models, session, tenant-scoped repository (Story 1.5)."""

from ikip_common.db.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey
from ikip_common.db.documents import (
    DocumentRepository,
    DuplicateDocumentError,
    IngestOutcome,
)
from ikip_common.db.embeddings import (
    EmbeddingRepository,
    EmbedReport,
    embed_and_store,
    vectors_for_chunk,
)
from ikip_common.db.ingestion import IllegalStateTransitionError, IngestionJobRepository
from ikip_common.db.models import (
    EMBEDDING_DIM,
    AccountStatus,
    AppUser,
    Chunk,
    Document,
    DocumentVersion,
    Embedding,
    IngestionJob,
    IngestionState,
    Section,
    Tenant,
    UserRole,
)
from ikip_common.db.repository import TenantScopedRepository
from ikip_common.db.retrieval import (
    RetrievalFilters,
    SearchHit,
    lexical_search,
    vector_search,
)
from ikip_common.db.session import make_engine, make_session_factory
from ikip_common.db.similarity import (
    hamming_distance,
    is_near_duplicate,
    simhash,
)

__all__ = [
    "Base",
    "TenantScoped",
    "Timestamped",
    "UUIDPrimaryKey",
    "Tenant",
    "AppUser",
    "UserRole",
    "AccountStatus",
    "IngestionJob",
    "IngestionState",
    "IngestionJobRepository",
    "IllegalStateTransitionError",
    "Document",
    "DocumentVersion",
    "Section",
    "Chunk",
    "Embedding",
    "EMBEDDING_DIM",
    "EmbeddingRepository",
    "EmbedReport",
    "embed_and_store",
    "vectors_for_chunk",
    "DocumentRepository",
    "DuplicateDocumentError",
    "IngestOutcome",
    "simhash",
    "hamming_distance",
    "is_near_duplicate",
    "TenantScopedRepository",
    "SearchHit",
    "RetrievalFilters",
    "lexical_search",
    "vector_search",
    "make_engine",
    "make_session_factory",
]
