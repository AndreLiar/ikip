"""Lexical + vector search over curated chunks (Story 3.3, ADR 0004/0021).

Two retrieval arms, both tenant-scoped (NFR10) and both returning the full citation
chain chunk → section → document_version → document (FR16):
  - `lexical_search`  — BM25/full-text via Postgres `tsvector`/GIN (`simple` config).
  - `vector_search`   — semantic via pgvector HNSW (cosine distance).
Both accept `RetrievalFilters` (version-awareness via `is_current`, document type,
metadata containment — Story 3.4 AC3) and an optional `min_score` floor (feeds the
abstention path, AC4). Fusion/reranking live in `ikip_common.llm.hybrid`; the
grounded-answer graph in Story 3.5. Each call measures and logs its latency (AC4).
SQL stays ours (not a LangChain retriever) so tenant scoping + citations are
structural, not delegated (ADR 0021).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ikip_common.db.models import (
    FTS_CONFIG,
    Chunk,
    Document,
    DocumentEquipment,
    DocumentVersion,
    Embedding,
    Section,
)
from ikip_common.llm.base import Vector

logger = logging.getLogger("ikip.retrieval")

DEFAULT_LIMIT = 10


@dataclass
class SearchHit:
    """One retrieval result + its resolvable citation (FR16). `score` is higher-is-better."""

    chunk_id: uuid.UUID
    content: str
    score: float
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    revision: str
    is_current: bool
    section_id: uuid.UUID
    heading: str | None
    hierarchy_path: str | None
    page_start: int | None
    page_end: int | None


@dataclass
class RetrievalFilters:
    """Metadata filters for retrieval (Story 3.4 AC3). Applied in SQL on both arms.

    `current_only` enforces version-awareness (only applicable, non-superseded versions
    — NFR15/FR14); `document_type` narrows by document kind; `metadata` is a JSONB
    containment match on `chunk.chunk_metadata` (e.g. equipment model/revision, kept
    lightweight at MVP — no dedicated equipment table yet)."""

    current_only: bool = True
    document_type: str | None = None
    equipment_id: uuid.UUID | None = None
    metadata: dict | None = None


def _apply_filters(stmt, filters: RetrievalFilters | None):
    if filters is None:
        return stmt
    if filters.current_only:
        stmt = stmt.where(DocumentVersion.is_current.is_(True))
    if filters.document_type is not None:
        stmt = stmt.where(Document.type == filters.document_type)
    if filters.equipment_id is not None:
        stmt = stmt.where(
            select(DocumentEquipment.document_id)
            .where(
                DocumentEquipment.document_id == Document.id,
                DocumentEquipment.equipment_id == filters.equipment_id,
            )
            .exists()
        )
    if filters.metadata:
        stmt = stmt.where(Chunk.chunk_metadata.contains(filters.metadata))
    return stmt


@contextmanager
def _timed(arm: str, *, tenant_id: uuid.UUID) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("retrieval arm=%s tenant=%s latency_ms=%.1f", arm, tenant_id, elapsed_ms)


def _citation_joins(stmt):
    """Attach the chunk → section → document_version → document joins (FR16)."""
    return (
        stmt.join(Section, Chunk.section_id == Section.id)
        .join(DocumentVersion, Section.document_version_id == DocumentVersion.id)
        .join(Document, DocumentVersion.document_id == Document.id)
    )


def _hit(row) -> SearchHit:
    return SearchHit(
        chunk_id=row.chunk_id,
        content=row.content,
        score=float(row.score),
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        revision=row.revision,
        is_current=row.is_current,
        section_id=row.section_id,
        heading=row.heading,
        hierarchy_path=row.hierarchy_path,
        page_start=row.page_start,
        page_end=row.page_end,
    )


_CITATION_COLUMNS = (
    Chunk.id.label("chunk_id"),
    Chunk.content.label("content"),
    Document.id.label("document_id"),
    DocumentVersion.id.label("document_version_id"),
    DocumentVersion.revision.label("revision"),
    DocumentVersion.is_current.label("is_current"),
    Section.id.label("section_id"),
    Section.heading.label("heading"),
    Section.hierarchy_path.label("hierarchy_path"),
    Chunk.page_start.label("page_start"),
    Chunk.page_end.label("page_end"),
)


def _lexical_stmt(tenant_id: uuid.UUID, query: str, limit: int, filters: RetrievalFilters | None):
    tsquery = func.websearch_to_tsquery(FTS_CONFIG, query)
    score = func.ts_rank(Chunk.content_tsv, tsquery).label("score")
    stmt = _citation_joins(select(*_CITATION_COLUMNS, score)).where(
        Chunk.tenant_id == tenant_id,
        Chunk.content_tsv.op("@@")(tsquery),
    )
    return _apply_filters(stmt, filters).order_by(score.desc()).limit(limit)


def _vector_stmt(
    tenant_id: uuid.UUID,
    query_vector: Vector,
    model_version: str,
    limit: int,
    filters: RetrievalFilters | None,
):
    distance = Embedding.vector.cosine_distance(query_vector)
    # cosine similarity = 1 - cosine distance -> higher-is-better score
    score = (1 - distance).label("score")
    stmt = _citation_joins(
        select(*_CITATION_COLUMNS, score).join(Chunk, Embedding.chunk_id == Chunk.id)
    ).where(
        Embedding.tenant_id == tenant_id,
        Embedding.model_version == model_version,
    )
    # ascending distance = closest first
    return _apply_filters(stmt, filters).order_by(distance).limit(limit)


def _floor(hits: list[SearchHit], min_score: float | None) -> list[SearchHit]:
    return hits if min_score is None else [h for h in hits if h.score >= min_score]


def lexical_search(
    session: Session,
    tenant_id: uuid.UUID,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    filters: RetrievalFilters | None = None,
    min_score: float | None = None,
) -> list[SearchHit]:
    """Full-text (BM25-style) search via `tsvector`/GIN, ranked by `ts_rank` (AC1)."""
    with _timed("lexical", tenant_id=tenant_id):
        rows = session.execute(_lexical_stmt(tenant_id, query, limit, filters)).all()
    return _floor([_hit(r) for r in rows], min_score)


def vector_search(
    session: Session,
    tenant_id: uuid.UUID,
    query_vector: Vector,
    *,
    model_version: str,
    limit: int = DEFAULT_LIMIT,
    filters: RetrievalFilters | None = None,
    min_score: float | None = None,
) -> list[SearchHit]:
    """Semantic search via pgvector HNSW cosine distance (AC2). Only vectors of the
    given `model_version` are comparable, so we filter on it."""
    with _timed("vector", tenant_id=tenant_id):
        rows = session.execute(
            _vector_stmt(tenant_id, query_vector, model_version, limit, filters)
        ).all()
    return _floor([_hit(r) for r in rows], min_score)
