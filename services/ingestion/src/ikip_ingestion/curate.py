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
import json
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
    layout_object_key: str | None
    skipped_duplicate: bool
    outcome: IngestOutcome | None  # None iff skipped_duplicate


def _safe(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def curate_to_storage(
    *,
    tenant_id: uuid.UUID,
    raw_bytes: bytes,
    source: str,
    storage: ObjectStorage,
    content_type: str | None = None,
    extractor: TextExtractor | None = None,
) -> tuple[str, str | None]:
    """Stage 1 (asset `curated_documents`): extract + clean + validate a raw artifact and
    write the curated text (+ optional layout sidecar) to the `curated` tier. Returns
    (curated_object_key, layout_object_key). The heavy PDF/OCR work happens HERE; it writes
    NO DB rows, so versioning can be re-run later WITHOUT re-extracting (Story 2.6 lineage)."""
    curated = curate_document(
        raw_bytes, source=source, content_type=content_type, extractor=extractor
    )
    checksum = hashlib.sha256(curated.text.encode("utf-8")).hexdigest()
    key = tier_key(ArtifactTier.curated, str(tenant_id), _safe(source), f"{checksum}.txt")
    storage.put(key, curated.text.encode("utf-8"), content_type="text/plain")
    layout_key = None
    if curated.regions:
        layout_key = tier_key(
            ArtifactTier.curated, str(tenant_id), _safe(source), f"{checksum}.layout.json"
        )
        layout = [
            {"page": region.page, "text": region.text, "bbox": list(region.bbox)}
            for region in curated.regions
        ]
        storage.put(
            layout_key,
            json.dumps(layout, separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
        )
    return key, layout_key


def version_from_curated(
    *,
    tenant_id: uuid.UUID,
    repo: DocumentRepository,
    cache: Cache,
    storage: ObjectStorage,
    curated_object_key: str,
    layout_object_key: str | None,
    source: str,
    source_object_key: str | None = None,
) -> CurationOutcome:
    """Stage 2 (asset `document_versions`): publish a deduplicated version FROM an already
    curated artifact — no extraction / no OCR. Title/revision are re-derived from the clean
    curated text (cheap, deterministic). Exact duplicates are skipped."""
    curated_text = storage.get(curated_object_key).decode("utf-8")
    meta = curate_document(curated_text.encode("utf-8"), source=source, content_type="text/plain")
    checksum = hashlib.sha256(curated_text.encode("utf-8")).hexdigest()
    fingerprint = simhash(curated_text)
    revision = meta.metadata.revision or f"r-{checksum[:8]}"
    try:
        outcome = publish_document_version(
            repo,
            cache,
            title=meta.metadata.title or source,
            checksum=checksum,
            fingerprint=fingerprint,
            revision=revision,
            curated_object_key=curated_object_key,
            layout_object_key=layout_object_key,
            source_object_key=source_object_key,
            source=source,
        )
    except DuplicateDocumentError:
        return CurationOutcome(
            curated_object_key=curated_object_key,
            layout_object_key=layout_object_key,
            skipped_duplicate=True,
            outcome=None,
        )
    return CurationOutcome(
        curated_object_key=curated_object_key,
        layout_object_key=layout_object_key,
        skipped_duplicate=False,
        outcome=outcome,
    )


def curate_and_version(
    *,
    tenant_id: uuid.UUID,
    raw_bytes: bytes,
    source: str,
    repo: DocumentRepository,
    cache: Cache,
    storage: ObjectStorage,
    content_type: str | None = None,
    source_object_key: str | None = None,
    extractor: TextExtractor | None = None,
) -> CurationOutcome:
    """Compose stage 1 + stage 2 (curate → version) in one call. Kept for callers/tests that
    want the whole seam; the Dagster assets use the two stages separately (extract in
    `curated_documents`, version in `document_versions`) for a faithful lineage."""
    key, layout_key = curate_to_storage(
        tenant_id=tenant_id,
        raw_bytes=raw_bytes,
        source=source,
        storage=storage,
        content_type=content_type,
        extractor=extractor,
    )
    return version_from_curated(
        tenant_id=tenant_id,
        repo=repo,
        cache=cache,
        storage=storage,
        curated_object_key=key,
        layout_object_key=layout_key,
        source=source,
        source_object_key=source_object_key,
    )
