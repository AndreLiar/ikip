"""Cache invalidation on document-version publish (Epic 2 ingestion ↔ Story 3.7, ADR 0009).

When ingestion publishes a new `document_version` (a brand-new document OR a revision
that supersedes a prior one), any cached answer for that tenant may now be stale — it
could cite an obsolete version. So the publish point must invalidate the tenant's answer
cache. This is the seam the Dagster versioning asset calls.

Dagster-free and port-injected (`DocumentRepository` + `Cache`) → unit-testable with a
`FakeCache`. An exact-duplicate (no new version published) raises and does NOT invalidate.
"""

from __future__ import annotations

from ikip_common.cache.base import Cache
from ikip_common.cache.keys import invalidate_tenant_answers
from ikip_common.db.documents import DocumentRepository, IngestOutcome


def publish_document_version(
    repo: DocumentRepository,
    cache: Cache,
    **ingest_kwargs: object,
) -> IngestOutcome:
    """Publish a version via `repo.ingest_version(**ingest_kwargs)`, then invalidate the
    tenant's answer cache (epoch bump). Propagates `DuplicateDocumentError` for exact
    duplicates — in which case nothing was published and the cache is left untouched."""
    outcome = repo.ingest_version(**ingest_kwargs)  # type: ignore[arg-type]
    # A new version (new doc or supersession) is now current -> stale answers must go.
    invalidate_tenant_answers(cache, repo.tenant_id)
    return outcome
