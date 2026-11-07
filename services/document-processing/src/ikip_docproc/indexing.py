"""Build-time indexing: curated text → sections + chunks + embeddings (Epic 2↔3).

The missing downstream stage of the Dagster pipeline: it turns a document version's
curated text into the rows retrieval queries — `Section` + `Chunk` (+ their vectors in
`Embedding`). Pure and port-injected (a SQLAlchemy `Session` + an `EmbeddingClient`), so
it is unit-testable with a `FakeEmbeddingClient` and a real pgvector DB; the Dagster
asset is a thin wrapper that fetches curated text (R2) and injects the Azure client.

Idempotent + asset-rerun-safe: if a version was already chunked, we DON'T duplicate
sections/chunks — we just (re-)embed the existing chunks (`embed_and_store` is itself
idempotent per `(chunk_id, model_version)`, so re-indexing is cheap and additive, FR14).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from ikip_common.db.embeddings import EmbedReport, embed_and_store
from ikip_common.db.models import Chunk, Section
from ikip_common.llm.base import EmbeddingClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from ikip_docproc.chunking import ChunkSpec, chunk_document


@dataclass
class _PlannedSection:
    path: str
    heading: str | None
    ordinal: int
    specs: list[ChunkSpec]


def plan_sections(specs: list[ChunkSpec]) -> list[_PlannedSection]:
    """Group chunk specs into ordered sections by `section_path` (pure, DB-free)."""
    sections: dict[str, _PlannedSection] = {}
    for spec in specs:
        sec = sections.get(spec.section_path)
        if sec is None:
            sec = _PlannedSection(
                path=spec.section_path,
                heading=spec.section_heading,
                ordinal=len(sections),
                specs=[],
            )
            sections[spec.section_path] = sec
        sec.specs.append(spec)
    return list(sections.values())


@dataclass
class IndexReport:
    sections_created: int
    chunks_created: int
    embed: EmbedReport


def _existing_chunks(session: Session, document_version_id: uuid.UUID) -> list[Chunk]:
    stmt = (
        select(Chunk)
        .join(Section, Chunk.section_id == Section.id)
        .where(Section.document_version_id == document_version_id)
    )
    return list(session.execute(stmt).scalars())


def index_version(
    session: Session,
    tenant_id: uuid.UUID,
    document_version_id: uuid.UUID,
    curated_text: str,
    embedding_client: EmbeddingClient,
    *,
    max_tokens: int = 400,
    overlap_tokens: int = 40,
) -> IndexReport:
    """Chunk `curated_text`, persist Section/Chunk (if not already present for this
    version), then embed the chunks. Returns counts + the embedding report."""
    existing = _existing_chunks(session, document_version_id)
    if existing:
        # Already chunked -> don't duplicate; just (re-)embed existing chunks (idempotent).
        report = embed_and_store(session, tenant_id, embedding_client, existing)
        return IndexReport(sections_created=0, chunks_created=0, embed=report)

    specs = chunk_document(curated_text, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    chunks: list[Chunk] = []
    sections_created = 0
    for planned in plan_sections(specs):
        section = Section(
            document_version_id=document_version_id,
            heading=planned.heading,
            hierarchy_path=planned.path,
            ordinal=planned.ordinal,
            page_start=planned.specs[0].page_start,
            page_end=planned.specs[-1].page_end,
        )
        session.add(section)
        session.flush()  # get section.id
        sections_created += 1
        for spec in planned.specs:
            chunk = Chunk(
                tenant_id=tenant_id,
                section_id=section.id,
                content=spec.content,
                page_start=spec.page_start,
                page_end=spec.page_end,
                token_count=spec.token_count,
                chunk_metadata={"section_path": spec.section_path, "ordinal": spec.ordinal},
            )
            session.add(chunk)
            chunks.append(chunk)
    session.flush()  # get chunk ids for embedding

    report = embed_and_store(session, tenant_id, embedding_client, chunks)
    return IndexReport(sections_created=sections_created, chunks_created=len(chunks), embed=report)
