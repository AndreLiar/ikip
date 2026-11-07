"""Ingestion-logic tests (Story 2.2 AC4). Hermetic: fake storage + fake job repo
+ in-memory seen-store. No live R2, no DB. Proves change detection + raw storage.
"""

import uuid
from dataclasses import dataclass

from ikip_ingestion.connectors import SourceDocument
from ikip_ingestion.ingest import InMemorySeenStore, ingest_documents


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        self.objects[key] = data
        return key

    def get(self, key):  # pragma: no cover - unused here
        return self.objects[key]

    def exists(self, key):  # pragma: no cover
        return key in self.objects

    def delete(self, key):  # pragma: no cover
        self.objects.pop(key, None)

    def presigned_url(self, key, *, expires_s=3600):  # pragma: no cover
        return f"https://fake/{key}"


@dataclass
class _Job:
    id: uuid.UUID
    source: str
    raw_object_key: str | None
    content_type: str | None = None


class FakeJobs:
    """Minimal stand-in for IngestionJobRepository.create."""

    def __init__(self) -> None:
        self.created: list[_Job] = []

    def create(
        self, source: str, *, raw_object_key: str | None = None, content_type: str | None = None
    ) -> _Job:
        job = _Job(
            id=uuid.uuid4(), source=source, raw_object_key=raw_object_key, content_type=content_type
        )
        self.created.append(job)
        return job


_TENANT = str(uuid.uuid4())


def _docs() -> list[SourceDocument]:
    return [
        SourceDocument("a.pdf", b"content-A", "application/pdf"),
        SourceDocument("b.csv", b"content-B", "text/csv"),
    ]


def test_ingest_stores_raw_and_creates_jobs() -> None:
    storage, jobs, seen = FakeStorage(), FakeJobs(), InMemorySeenStore()
    res = ingest_documents(
        tenant_id=_TENANT,
        config=None,
        connector=None,  # docs injected directly
        storage=storage,
        jobs=jobs,
        seen=seen,
        docs=_docs(),
    )
    assert res.ingested == 2 and res.skipped == 0
    assert len(storage.objects) == 2
    assert len(jobs.created) == 2
    # raw tier + tenant in the key
    assert all(k.startswith(f"raw/{_TENANT}/") for k in storage.objects)
    # content_type captured on the job (persisted so curation needn't sniff later)
    assert {j.content_type for j in jobs.created} == {"application/pdf", "text/csv"}


def test_change_detection_skips_unchanged() -> None:
    storage, jobs, seen = FakeStorage(), FakeJobs(), InMemorySeenStore()
    docs = _docs()
    ingest_documents(
        tenant_id=_TENANT,
        config=None,
        connector=None,
        storage=storage,
        jobs=jobs,
        seen=seen,
        docs=docs,
    )
    # second run, same bytes -> all skipped, no new objects/jobs
    res2 = ingest_documents(
        tenant_id=_TENANT,
        config=None,
        connector=None,
        storage=storage,
        jobs=jobs,
        seen=seen,
        docs=docs,
    )
    assert res2.ingested == 0 and res2.skipped == 2
    assert len(storage.objects) == 2 and len(jobs.created) == 2


def test_changed_content_reingested_as_new_object() -> None:
    storage, jobs, seen = FakeStorage(), FakeJobs(), InMemorySeenStore()
    ingest_documents(
        tenant_id=_TENANT,
        config=None,
        connector=None,
        storage=storage,
        jobs=jobs,
        seen=seen,
        docs=[SourceDocument("a.pdf", b"v1")],
    )
    ingest_documents(
        tenant_id=_TENANT,
        config=None,
        connector=None,
        storage=storage,
        jobs=jobs,
        seen=seen,
        docs=[SourceDocument("a.pdf", b"v2")],
    )
    # a changed document -> a second raw object (raw never overwritten)
    assert len(storage.objects) == 2
    assert len(jobs.created) == 2
