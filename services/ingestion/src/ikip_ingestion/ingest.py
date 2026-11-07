"""Ingestion logic (Story 2.2) — Dagster-free, pure, testable.

For each document a connector yields:
  1. compute a content checksum,
  2. change detection (AC4): skip if an identical checksum was already ingested
     for this source_uri (via a `SeenStore`),
  3. store the raw bytes in object storage (raw tier),
  4. create an `ingestion_job` (pending) referencing the raw key.

Side-effecting collaborators (storage, job repo, seen-store) are injected so the
whole thing is unit-testable with fakes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from ikip_common.db.ingestion import IngestionJobRepository
from ikip_common.storage import ArtifactTier, ObjectStorage, tier_key

from ikip_ingestion.connectors import SourceConfig, SourceConnector, SourceDocument


class SeenStore(Protocol):
    """Tracks already-ingested (source_uri -> checksum) for change detection."""

    def seen_checksum(self, source_uri: str) -> str | None: ...
    def mark(self, source_uri: str, checksum: str) -> None: ...


class InMemorySeenStore:
    def __init__(self) -> None:
        self._m: dict[str, str] = {}

    def seen_checksum(self, source_uri: str) -> str | None:
        return self._m.get(source_uri)

    def mark(self, source_uri: str, checksum: str) -> None:
        self._m[source_uri] = checksum


@dataclass
class IngestResult:
    ingested: int = 0
    skipped: int = 0
    job_ids: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.job_ids is None:
            self.job_ids = []


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _raw_key(tenant_id: str, source_uri: str, checksum: str) -> str:
    # Deterministic, collision-resistant key; checksum in the path makes a changed
    # document a new object (raw tier is never overwritten, NFR15).
    safe = hashlib.sha256(source_uri.encode()).hexdigest()[:16]
    return tier_key(ArtifactTier.raw, tenant_id, safe, f"{checksum}.bin")


def ingest_documents(
    *,
    tenant_id: str,
    config: SourceConfig,
    connector: SourceConnector,
    storage: ObjectStorage,
    jobs: IngestionJobRepository,
    seen: SeenStore,
    docs: Iterable[SourceDocument] | None = None,
) -> IngestResult:
    """Run a source through to raw storage + pending ingestion jobs."""
    result = IngestResult()
    stream = docs if docs is not None else connector.iter_documents(config)
    for doc in stream:
        checksum = _checksum(doc.content)
        if seen.seen_checksum(doc.source_uri) == checksum:
            result.skipped += 1
            continue
        key = _raw_key(tenant_id, doc.source_uri, checksum)
        storage.put(key, doc.content, content_type=doc.content_type)
        job = jobs.create(source=doc.source_uri, raw_object_key=key)
        seen.mark(doc.source_uri, checksum)
        result.ingested += 1
        result.job_ids.append(str(job.id))
    return result
