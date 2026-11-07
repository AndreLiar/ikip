"""Cache invalidation on version publish (ADR 0009) — pure, no DB, no network."""

import uuid

import pytest
from ikip_common.cache import FakeCache, current_answer_epoch
from ikip_common.db.documents import DuplicateDocumentError, IngestOutcome
from ikip_common.db.models import Document, DocumentVersion
from ikip_ingestion.version_publish import publish_document_version


class _FakeRepo:
    """Minimal DocumentRepository stand-in: records the call + scripts the outcome."""

    def __init__(self, *, raise_dup: bool = False) -> None:
        self.tenant_id = uuid.uuid4()
        self._raise_dup = raise_dup
        self.calls: list[dict] = []

    def ingest_version(self, **kwargs):
        self.calls.append(kwargs)
        if self._raise_dup:
            raise DuplicateDocumentError("exact duplicate")
        doc = Document(title=kwargs.get("title", "Manual"))
        version = DocumentVersion(
            document_id=uuid.uuid4(), revision=kwargs["revision"], checksum="c"
        )
        return IngestOutcome(document=doc, version=version, created_document=True)


def test_publish_invalidates_tenant_answers() -> None:
    repo, cache = _FakeRepo(), FakeCache()
    assert current_answer_epoch(cache, repo.tenant_id) == 0

    out = publish_document_version(
        repo, cache, title="Pump Manual", checksum="abc", fingerprint="f", revision="A"
    )
    assert out.created_document is True
    assert repo.calls[0]["revision"] == "A"
    # a published version bumps the tenant's answer epoch -> stale answers unreachable
    assert current_answer_epoch(cache, repo.tenant_id) == 1


def test_exact_duplicate_does_not_invalidate() -> None:
    repo, cache = _FakeRepo(raise_dup=True), FakeCache()
    with pytest.raises(DuplicateDocumentError):
        publish_document_version(
            repo, cache, title="Pump Manual", checksum="abc", fingerprint="f", revision="A"
        )
    # nothing was published -> cache untouched
    assert current_answer_epoch(cache, repo.tenant_id) == 0
