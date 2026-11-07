# MISSION-010 — Deduplication & document versioning (Epic 2, Story 2.5)

**Mode:** Autonome + knowledge transfer.
**Objective:** detect exact + near-duplicate documents, and version documents so a new revision supersedes the old without deleting it (NFR15) — enabling version-aware retrieval (FR14).
**Maps to:** Epic 2 / Story 2.5.

## Acceptance criteria
1. Exact duplicates via checksum; near-duplicates via similarity. — **[verified]** (checksum lookup; SimHash + Hamming)
2. `document` + `document_version` capture revision, dates, checksum. — **[verified]** (models + reversible migration)
3. New version supersedes prior without deleting original evidence. — **[verified]** (is_current flip; both rows kept)
4. Tests cover dup detection + version supersession. — **[verified]** (5 DB tests; 4 pure SimHash tests)

## Deliverables
- `ikip_common/db/models.py` — `Document`, `DocumentVersion`.
- `ikip_common/db/similarity.py` — SimHash fingerprint + Hamming/near-dup (pure).
- `ikip_common/db/documents.py` — `DocumentRepository.ingest_version` (exact/near dedup + supersession), `DuplicateDocumentError`.
- Alembic migration (reversible; document + document_version only).
- Tests: `test_similarity.py` (pure, CI), `test_documents.py` (DB-gated).
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [dedup-versioning](../../concepts/dedup-versioning.md) (exact vs near, SimHash, supersede-not-delete, migration enum lesson). Reuses [multi-tenancy](../../concepts/multi-tenancy.md), [data-validation](../../concepts/data-validation.md).

## Notable
- Hit (and documented) the enum-type-orphan migration trap while resetting the dev DB.
- Dedup is tenant-scoped (same checksum in another tenant is not a duplicate).
