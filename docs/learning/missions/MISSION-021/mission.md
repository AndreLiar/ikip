# MISSION-021 — Complete Epic 2: curation → version persistence (feed the pipeline)

**Mode:** Guidé (extraction scope + revision decisions) → Autonome (assembly) + knowledge transfer.
**Objective:** turn the placeholder `document_versions` stage into real work — raw artifact → curated text → persisted, deduplicated `DocumentVersion` with a curated artifact — so `embedded_chunks` finally has upstream data and the whole build-time pipeline runs end to end.
**Maps to:** Epic 2 completion (Stories 2.3/2.4/2.5). Feeds MISSION-020 (embedding pipeline).

## Decisions (Guidé)
- **Extraction = text-first, PDF engines behind Protocols** (chosen): raw bytes are decoded as text (HTML tags stripped); `curate_document` takes an optional `TextExtractor` (PyMuPDF) so real PDF/OCR is a later adapter behind the same seam — no heavy dep in the hot path, CI stays fast.
- **Revision = `extract_revision` + deterministic fallback** (chosen): reuse Story 2.4's parser ("Rev. B"); if absent, fall back to `r-<checksum[:8]>`. Version-aware, matches real manuals.

## What was built
- **`ikip_docproc/curation.py` `curate_document(raw_bytes, *, source, content_type, extractor=None)`** — decode/strip-HTML (or use an injected PDF extractor) → `clean_text` → `build_metadata` (title/type/revision). Pure, engine-free by default.
- **`ikip_ingestion/curate.py` `curate_and_version(...)`** — curate → checksum + SimHash fingerprint → store curated text in the `curated` R2 tier → `publish_document_version` (dedup + supersession + **cache invalidation**). Exact duplicate → skipped. Port-injected (repo + cache + storage + extractor).
- **Dagster `document_versions` asset** now processes PENDING ingestion jobs: load raw from R2 → `curate_and_version` → transition the job (succeeded / failed-dead-letter), emitting a real quality report.
- Pipeline now runs end to end: `ingested_sources → curated_documents → document_versions → embedded_chunks`.

## Acceptance (self-set)
1. `curate_document`: text-first clean + metadata + revision; HTML stripped; injected extractor path. — **[verified]** (`test_curation.py`, pure)
2. `curate_and_version`: stores curated artifact, publishes a version with a revision, invalidates cache; exact-dup skipped (no invalidation). — **[verified]** (`test_curate.py`, fakes)
3. Dagster `document_versions` wired over pending jobs; `defs` load. — **[verified]** (import under `--group dagster`)
4. No regression. — **[verified]** (150 passed, 34 skipped; ruff/format OK)

## Honest remaining gaps (scoped out)
- **Real PDF extraction (PyMuPDF/Tesseract)** is behind the `TextExtractor` Protocol but not wired into the asset yet — text-first is the MVP path; PDF is an adapter swap + fixtures (follow-up).
- `curated_documents` stays a thin lineage node; the actual curation runs inside `document_versions` (sharing data across Dagster assets would mean re-querying). Splitting is a cosmetic lineage refinement.
- A full raw→version→index→retrieve DB test across all three services is possible but heavy; the seam is covered by the per-stage tests + the existing DB-gated indexing closed-loop (MISSION-020).

## Deliverables
- `services/document-processing/src/ikip_docproc/curation.py` (+ export) · `tests/test_curation.py`.
- `services/ingestion/src/ikip_ingestion/curate.py` · `tests/test_curate.py`.
- `services/ingestion/.../definitions.py` `document_versions` asset (real).

## Concepts
Reuses [pdf-extraction](../../concepts/pdf-extraction.md), [data-validation](../../concepts/data-validation.md), [dedup-versioning](../../concepts/dedup-versioning.md), [caching](../../concepts/caching.md), [dagster-orchestration](../../concepts/dagster-orchestration.md).
