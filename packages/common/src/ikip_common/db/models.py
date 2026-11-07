"""Core tenant/user ORM models (Story 1.5).

Matches the data model in docs/architecture/lld/data-schema.md. More tables
(document, chunk, embedding, …) land with later epics; the tenant-scoping
pattern established here applies to all of them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from ikip_common.db.base import Base, TenantScoped, Timestamped, UUIDPrimaryKey

# Embedding vector dimension (ADR 0020). text-embedding-3-small reduced to 512 via
# Matryoshka to fit Neon storage (ADR 0015). Baked into the pgvector column type;
# changing it is a migration + versioned re-embedding, not a hot toggle.
EMBEDDING_DIM = 512

# Postgres text-search config for the lexical arm (Story 3.3). 'simple' = no stemming,
# language-neutral — best for exact codes/refs and mixed FR/EN; the vector arm covers
# meaning/synonyms. Per-language stemming is a post-MVP enhancement.
FTS_CONFIG = "simple"


class UserRole(enum.StrEnum):
    admin = "admin"
    manager = "manager"
    technician = "technician"


class AccountStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"


class IngestionState(enum.StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"


class Tenant(UUIDPrimaryKey, Timestamped, Base):
    __tablename__ = "tenant"

    name: Mapped[str] = mapped_column(String(255))
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    policies: Mapped[dict] = mapped_column(JSONB, default=dict)


class AppUser(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_app_user_tenant_email"),)

    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), default=UserRole.technician
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status"), default=AccountStatus.active
    )


class IngestionJob(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Tracks one source file through ingestion (Story 2.1, FR8)."""

    __tablename__ = "ingestion_job"

    source: Mapped[str] = mapped_column(String(1024))
    state: Mapped[IngestionState] = mapped_column(
        Enum(IngestionState, name="ingestion_state"),
        default=IngestionState.pending,
        index=True,
    )
    # Key of the stored raw artifact in object storage (tier-prefixed), if captured.
    raw_object_key: Mapped[str | None] = mapped_column(String(2048), default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    error_info: Mapped[dict | None] = mapped_column(JSONB, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Document(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A logical document (Story 2.5). Has many versions; raw evidence preserved."""

    __tablename__ = "document"

    title: Mapped[str] = mapped_column(String(512))
    source: Mapped[str | None] = mapped_column(String(1024), default=None)
    type: Mapped[str | None] = mapped_column(String(64), default=None)
    rights: Mapped[str | None] = mapped_column(String(256), default=None)  # license/provenance
    # content_fingerprint = SimHash (or similar) for near-duplicate detection (Story 2.5).
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None, index=True)


class DocumentVersion(UUIDPrimaryKey, Timestamped, Base):
    """A revision of a Document. New versions supersede prior ones without deleting
    them (`is_current`), preserving original evidence (NFR15)."""

    __tablename__ = "document_version"
    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_docver_document_revision"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[str] = mapped_column(String(64))
    checksum: Mapped[str] = mapped_column(String(128), index=True)  # exact-dup detection
    publication_date: Mapped[date | None] = mapped_column(Date, default=None)
    effective_date: Mapped[date | None] = mapped_column(Date, default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Key of the curated artifact for this version in object storage.
    curated_object_key: Mapped[str | None] = mapped_column(String(2048), default=None)


class Section(UUIDPrimaryKey, Timestamped, Base):
    """A structural section of a document version (Story 3.1). Hierarchy + page range
    so chunks (and citations) can resolve back to a section/page (FR16)."""

    __tablename__ = "section"

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_version.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("section.id", ondelete="CASCADE"), default=None
    )
    heading: Mapped[str | None] = mapped_column(String(512), default=None)
    hierarchy_path: Mapped[str | None] = mapped_column(String(128), default=None)  # e.g. '3.2.1'
    page_start: Mapped[int | None] = mapped_column(default=None)
    page_end: Mapped[int | None] = mapped_column(default=None)
    ordinal: Mapped[int] = mapped_column(default=0)


class Chunk(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A retrieval unit (Story 3.1). Tenant-scoped (denormalized) so retrieval
    filters by tenant without a multi-join (NFR10). Keeps a resolvable back-reference
    to document/version/page/section for citations (FR16)."""

    __tablename__ = "chunk"
    # GIN index over the generated tsvector for BM25/full-text search (Story 3.3 AC1).
    __table_args__ = (Index("ix_chunk_content_tsv", "content_tsv", postgresql_using="gin"),)

    section_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("section.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column()
    # Stored, DB-generated full-text vector (language-neutral 'simple' config, FTS_CONFIG).
    # Kept in sync by Postgres from `content`; never set from Python.
    content_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(f"to_tsvector('{FTS_CONFIG}', content)", persisted=True)
    )
    page_start: Mapped[int | None] = mapped_column(default=None)
    page_end: Mapped[int | None] = mapped_column(default=None)
    token_count: Mapped[int] = mapped_column(default=0)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)


class Embedding(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A chunk's vector for semantic retrieval (Story 3.2, ADR 0020/0021).

    Vectors live in OUR relational schema (not a framework's store) so they keep the
    chunk → section → document_version citation chain (FR16) and tenant scoping (NFR10).
    `model_version` tags which model+dimension produced the vector; a unique
    (chunk_id, model_version) lets re-embedding be idempotent and *additive* — a new
    model version writes new rows without destroying prior vectors (FR14).
    """

    __tablename__ = "embedding"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model_version", name="uq_embedding_chunk_model"),
        # HNSW approximate-nearest-neighbour index for cosine similarity (Story 3.3 AC2).
        Index(
            "ix_embedding_vector_hnsw",
            "vector",
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
        ),
    )

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunk.id", ondelete="CASCADE"), index=True
    )
    model_version: Mapped[str] = mapped_column(String(128), index=True)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
