"""Build-time curation → versioning (Epic 2 completion).

Composes the pure pieces into the stage that was missing between raw ingestion and
embedding: a raw artifact becomes a persisted, deduplicated **document version** with a
curated artifact in object storage. Port-injected (DocumentRepository + Cache +
ObjectStorage + optional PDF extractor) → testable with fakes.

Steps per raw artifact:
  1. curate  (decode/extract → clean → metadata),
  2. checksum (exact-dup key) + SimHash fingerprint (near-dup key),
  3. store the curated text in the `curated` tier,
  4. publish the version (dedup + supersession + cache invalidation, Story 2.5/3.7).

Revision: the manufacturer revision parsed from the text (`extract_revision`) when
present, else a deterministic fallback derived from the checksum.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from ikip_common.cache.base import Cache
from ikip_common.db.documents import DocumentRepository, DuplicateDocumentError, IngestOutcome
from ikip_common.db.similarity import simhash
from ikip_common.storage import ArtifactTier, ObjectStorage, tier_key
from ikip_docproc.curation import TextExtractor, curate_document

from ikip_ingestion.version_publish import publish_document_version


@dataclass
class CurationOutcome:
    curated_object_key: str
    skipped_duplicate: bool
    outcome: IngestOutcome | None  # None iff skipped_duplicate


def _safe(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def curate_and_version(
    *,
    tenant_id: uuid.UUID,
    raw_bytes: bytes,
    source: str,
    repo: DocumentRepository,
    cache: Cache,
    storage: ObjectStorage,
    content_type: str | None = None,
    extractor: TextExtractor | None = None,
) -> CurationOutcome:
    """Curate a raw artifact and publish it as a document version. Exact duplicates
    (same curated checksum) are skipped; near-duplicates become a new version of the
    existing document (handled inside `publish_document_version`)."""
    curated = curate_document(
        raw_bytes, source=source, content_type=content_type, extractor=extractor
    )
    checksum = hashlib.sha256(curated.text.encode("utf-8")).hexdigest()
    fingerprint = simhash(curated.text)

    key = tier_key(ArtifactTier.curated, str(tenant_id), _safe(source), f"{checksum}.txt")
    storage.put(key, curated.text.encode("utf-8"), content_type="text/plain")

    revision = curated.metadata.revision or f"r-{checksum[:8]}"
    try:
        outcome = publish_document_version(
            repo,
            cache,
            title=curated.metadata.title or source,
            checksum=checksum,
            fingerprint=fingerprint,
            revision=revision,
            curated_object_key=key,
            source=source,
        )
    except DuplicateDocumentError:
        return CurationOutcome(curated_object_key=key, skipped_duplicate=True, outcome=None)
    return CurationOutcome(curated_object_key=key, skipped_duplicate=False, outcome=outcome)
