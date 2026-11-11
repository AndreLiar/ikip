"""Core tenant/user ORM models (Story 1.5).

Matches the data model in docs/architecture/lld/data-schema.md. More tables
(document, chunk, embedding, …) land with later epics; the tenant-scoping
pattern established here applies to all of them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
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


class Equipment(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Tenant-owned equipment model or physical asset (Story 4.3)."""

    __tablename__ = "equipment"
    __table_args__ = (
        Index("ix_equipment_tenant_model", "tenant_id", "manufacturer", "model", "revision"),
    )

    manufacturer: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(255))
    revision: Mapped[str | None] = mapped_column(String(64), default=None)
    asset_id: Mapped[str | None] = mapped_column(String(255), default=None)


class Workspace(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    __tablename__ = "workspace"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_workspace_tenant_name"),)

    name: Mapped[str] = mapped_column(String(255))


class WorkspaceMembership(Base):
    __tablename__ = "workspace_membership"
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"))


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
    # MIME type of the raw artifact, captured at fetch time so curation doesn't have to
    # sniff it later (Story 2.2; the sniff remains a fallback).
    content_type: Mapped[str | None] = mapped_column(String(128), default=None)
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
    # JSON sidecar containing normalized text-block regions for PDF highlights.
    layout_object_key: Mapped[str | None] = mapped_column(String(2048), default=None)
    # Key of the ORIGINAL source artifact (raw tier) — the PDF/HTML the user confirms
    # evidence against (Story 4.5). Preferred over curated for the source viewer.
    source_object_key: Mapped[str | None] = mapped_column(String(2048), default=None)


class DocumentEquipment(Base):
    """Tenant-safe N:M association between documents and equipment."""

    __tablename__ = "document_equipment"
    __table_args__ = (PrimaryKeyConstraint("document_id", "equipment_id"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id", ondelete="CASCADE"))
    equipment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )


class DocumentPermission(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """Explicit document ACL. No rows means tenant-wide access (migration-safe)."""

    __tablename__ = "document_permission"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "user_id", "workspace_id", name="uq_document_permission_subject"
        ),
        CheckConstraint(
            "(user_id IS NOT NULL) <> (workspace_id IS NOT NULL)",
            name="ck_document_permission_one_subject",
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), default=None
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), default=None
    )


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


class ExpectedBehavior(enum.StrEnum):
    """Expected system behaviour for an evaluation case (Story 3.6)."""

    answered = "answered"
    abstained = "abstained"


class EvaluationCase(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A gold-set case for RAG quality evaluation (Story 3.6, ADR 0016).

    `case_key` is a stable id within a `gold_set_version`, so a regression can be
    attributed to retrieval/generation vs a corpus change. `relevant_chunk_ids` is the
    expected evidence (for Recall@K). Stored tenant-scoped; `expected_behavior` is a
    plain String (not a DB enum) to keep migrations trap-free."""

    __tablename__ = "evaluation_case"
    __table_args__ = (
        UniqueConstraint("tenant_id", "gold_set_version", "case_key", name="uq_eval_case_key"),
    )

    case_key: Mapped[str] = mapped_column(String(128), index=True)
    gold_set_version: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column()
    expected_behavior: Mapped[str] = mapped_column(String(16))  # ExpectedBehavior value
    relevant_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(String(1024), default=None)


class AuditEvent(UUIDPrimaryKey, TenantScoped, Base):
    """Immutable record of a security- or usage-relevant operation (Story 4.8)."""

    __tablename__ = "audit_event"
    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "created_at"),)

    # Deliberately no FK: external OIDC actors may be audited before local user
    # provisioning, and an immutable audit trail must retain their subject UUID.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), default=None)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class PlatformAuditEvent(UUIDPrimaryKey, Base):
    """Cross-tenant operator audit retained even when a tenant is deleted."""

    __tablename__ = "platform_audit_event"

    actor_user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    operation: Mapped[str] = mapped_column(String(128), index=True)
    target_tenant_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Conversation(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A user's Q&A thread (Story 4.6). Scoped to tenant AND owner so history is
    private per user. Retention is enforced by `created_at` + the tenant's policy
    (Epic 6); no hard delete here."""

    __tablename__ = "conversation"
    __table_args__ = (Index("ix_conversation_tenant_user", "tenant_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(512), default=None)


class ConversationMessage(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """One turn in a conversation (Story 4.6 AC1). `role` ∈ {'user','assistant'};
    assistant turns keep their grounded answer + citations (JSONB) so the thread
    reproduces exactly what the user saw (FR16)."""

    __tablename__ = "conversation_message"
    __table_args__ = (Index("ix_message_conversation_time", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column()
    # Assistant turns: the structured answer payload (status, claims, citations,
    # warnings, abstention_reason) as returned to the UI. Empty for user turns.
    answer_payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class AnswerFeedback(UUIDPrimaryKey, TenantScoped, Timestamped, Base):
    """A user's rating / issue report on an assistant answer (Story 4.6 AC2). Retrievable
    for failure analysis (Epic 5, AC3). `rating` ∈ {-1,0,1} (down/neutral/up); `reason`
    is a free-text or category; `flagged` marks an incorrect answer/source to triage."""

    __tablename__ = "answer_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"),
        Index("ix_feedback_tenant_flagged", "tenant_id", "flagged"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation_message.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    rating: Mapped[int] = mapped_column(default=0)  # -1 | 0 | 1
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(2048), default=None)


class QueryTrace(UUIDPrimaryKey, TenantScoped, Base):
    """Durable end-to-end record of one query→answer (Story 5.4, ADR 0013).

    The queryable audit trail (AC1/AC3): who asked, what retrieval surfaced (chunk IDs),
    which model, latency and estimated cost — correlatable to the Langfuse trace via
    `trace_id`. Deliberately stores a **query hash** + **IDs**, not raw text (AC4/NFR16);
    raw content lives only in Langfuse when content capture is explicitly enabled."""

    __tablename__ = "query_trace"
    __table_args__ = (Index("ix_query_trace_tenant_time", "tenant_id", "created_at"),)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    operation: Mapped[str] = mapped_column(String(64), index=True)  # 'ask' | 'retrieve'
    query_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 of normalized query
    model_version: Mapped[str | None] = mapped_column(String(128), default=None)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(32))  # answered | abstained | error
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    trace_id: Mapped[str | None] = mapped_column(String(128), default=None, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
