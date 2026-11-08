"""curate_and_version (Epic 2 completion) — pure, fakes, no DB, no network.

Asserts the full curation→versioning seam: curated artifact stored, version published
(with a revision), cache invalidated; exact duplicates skipped.
"""

import uuid

from ikip_common.cache import FakeCache, current_answer_epoch
from ikip_common.db.documents import DuplicateDocumentError, IngestOutcome
from ikip_common.db.models import Document, DocumentVersion
from ikip_ingestion.curate import curate_and_version


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        self.objects[key] = data
        return key

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_url(self, key: str, *, expires_s: int = 3600) -> str:
        return f"memory://{key}"


class _FakeRepo:
    def __init__(self, *, raise_dup: bool = False) -> None:
        self.tenant_id = uuid.uuid4()
        self._raise_dup = raise_dup
        self.calls: list[dict] = []

    def ingest_version(self, **kwargs) -> IngestOutcome:
        self.calls.append(kwargs)
        if self._raise_dup:
            raise DuplicateDocumentError("exact duplicate")
        doc = Document(title=kwargs["title"])
        version = DocumentVersion(
            document_id=uuid.uuid4(), revision=kwargs["revision"], checksum=kwargs["checksum"]
        )
        return IngestOutcome(document=doc, version=version, created_document=True)


def test_curate_and_version_stores_curated_and_publishes() -> None:
    repo, cache, storage = _FakeRepo(), FakeCache(), _FakeStorage()
    raw = b"Pump Manual\n\nFault E42: pump motor overheat.\n\nRev. C"

    res = curate_and_version(
        tenant_id=repo.tenant_id,
        raw_bytes=raw,
        source="https://x/pump-manual.txt",
        repo=repo,
        cache=cache,
        storage=storage,
        source_object_key="raw/t/doc/abc.bin",
    )

    assert res.skipped_duplicate is False and res.outcome is not None
    # curated artifact stored under the curated tier, keyed by checksum
    assert (
        res.curated_object_key.startswith("curated/") and res.curated_object_key in storage.objects
    )
    # version published with the manufacturer revision parsed from the text
    assert repo.calls[0]["revision"] == "C"
    assert repo.calls[0]["curated_object_key"] == res.curated_object_key
    # the original source artifact key is threaded onto the version (Story 4.5)
    assert repo.calls[0]["source_object_key"] == "raw/t/doc/abc.bin"
    # publishing invalidated the tenant answer cache (ADR 0009)
    assert current_answer_epoch(cache, repo.tenant_id) == 1


def test_revision_fallback_when_absent() -> None:
    repo, cache, storage = _FakeRepo(), FakeCache(), _FakeStorage()
    curate_and_version(
        tenant_id=repo.tenant_id,
        raw_bytes=b"manual with no revision marker",
        source="m.txt",
        repo=repo,
        cache=cache,
        storage=storage,
    )
    assert repo.calls[0]["revision"].startswith("r-")  # deterministic checksum-derived fallback


def test_exact_duplicate_skipped_no_invalidation() -> None:
    repo, cache, storage = _FakeRepo(raise_dup=True), FakeCache(), _FakeStorage()
    res = curate_and_version(
        tenant_id=repo.tenant_id,
        raw_bytes=b"dup",
        source="d.txt",
        repo=repo,
        cache=cache,
        storage=storage,
    )
    assert res.skipped_duplicate is True and res.outcome is None
    # curated artifact is still written (idempotent, checksum-keyed), but no version/cache change
    assert res.curated_object_key in storage.objects
    assert current_answer_epoch(cache, repo.tenant_id) == 0


def test_pdf_layout_sidecar_is_stored_and_published() -> None:
    from ikip_docproc.models import DocumentExtraction, ExtractionMethod, PageExtraction, TextRegion

    class _Extractor:
        def extract(self, data: bytes) -> DocumentExtraction:
            return DocumentExtraction(
                pages=[
                    PageExtraction(
                        page=3,
                        text="Fault E42 reset procedure",
                        method=ExtractionMethod.native,
                        regions=[
                            TextRegion(
                                page=3,
                                text="Fault E42 reset procedure",
                                bbox=(0.1, 0.2, 0.8, 0.3),
                            )
                        ],
                    )
                ]
            )

    repo, cache, storage = _FakeRepo(), FakeCache(), _FakeStorage()
    result = curate_and_version(
        tenant_id=repo.tenant_id,
        raw_bytes=b"%PDF-fake",
        source="manual.pdf",
        repo=repo,
        cache=cache,
        storage=storage,
        extractor=_Extractor(),
    )
    assert result.layout_object_key is not None
    assert result.layout_object_key.endswith(".layout.json")
    assert b'"bbox":[0.1,0.2,0.8,0.3]' in storage.objects[result.layout_object_key]
    assert repo.calls[0]["layout_object_key"] == result.layout_object_key
