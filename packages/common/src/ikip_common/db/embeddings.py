"""Embedding generation + versioned, tenant-scoped storage (Story 3.2, ADR 0020/0021).

Turns chunks into vectors via the `EmbeddingClient` port and stores them in the
tenant-scoped `embedding` table, tagged with the client's `model_version`. Writes
are **additive and idempotent**: a (chunk_id, model_version) already present is
skipped; a *new* model_version writes new rows without touching prior vectors (FR14).
The domain depends only on our port — not on LangChain (ADR 0021).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ikip_common.db.models import Chunk, Embedding
from ikip_common.db.repository import TenantScopedRepository
from ikip_common.llm.base import EmbeddingClient


class EmbeddingRepository(TenantScopedRepository[Embedding]):
    """Tenant-scoped access to embedding vectors."""

    model = Embedding

    def existing_versions(
        self, chunk_ids: Sequence[uuid.UUID], model_version: str
    ) -> set[uuid.UUID]:
        """chunk_ids (within this tenant) that already have a vector for model_version."""
        if not chunk_ids:
            return set()
        stmt = self._scoped().where(
            Embedding.chunk_id.in_(chunk_ids),
            Embedding.model_version == model_version,
        )
        return {e.chunk_id for e in self.session.execute(stmt).scalars()}


@dataclass
class EmbedReport:
    """Outcome of an embed_and_store run."""

    model_version: str
    embedded: int
    skipped: int


def embed_and_store(
    session: Session,
    tenant_id: uuid.UUID,
    client: EmbeddingClient,
    chunks: Sequence[Chunk],
    *,
    skip_existing: bool = True,
) -> EmbedReport:
    """Embed `chunks` and persist one `embedding` row per chunk for the client's
    model_version. Idempotent (skips chunks already embedded for that version) and
    additive (never deletes vectors from other versions)."""
    repo = EmbeddingRepository(session, tenant_id)
    model_version = client.model_version

    todo = list(chunks)
    skipped = 0
    if skip_existing:
        have = repo.existing_versions([c.id for c in chunks], model_version)
        todo = [c for c in chunks if c.id not in have]
        skipped = len(chunks) - len(todo)

    if todo:
        vectors = client.embed([c.content for c in todo])
        for chunk, vector in zip(todo, vectors, strict=True):
            repo.add(Embedding(chunk_id=chunk.id, model_version=model_version, vector=vector))

    return EmbedReport(model_version=model_version, embedded=len(todo), skipped=skipped)


def vectors_for_chunk(
    session: Session, tenant_id: uuid.UUID, chunk_id: uuid.UUID
) -> list[Embedding]:
    """All stored vectors for a chunk (one per model_version) — shows version coexistence."""
    repo = EmbeddingRepository(session, tenant_id)
    stmt = repo._scoped().where(Embedding.chunk_id == chunk_id)  # noqa: SLF001
    return list(session.execute(stmt).scalars())
