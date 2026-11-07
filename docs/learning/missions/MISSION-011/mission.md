# MISSION-011 — Lineage, quality reporting & reprocessing (Epic 2, Story 2.6)

**Mode:** Autonome + knowledge transfer.
**Objective:** wire the pipeline into a lineage graph of Dagster assets, emit a data-quality report, add retry + dead-letter, and enable asset-aware reprocessing — closing Epic 2.
**Maps to:** Epic 2 / Story 2.6.

## Acceptance criteria
1. Lineage links raw → curated → version as Dagster assets. — **[verified]** (3 chained assets; graph asserted)
2. Data-quality report (success rate, failures, duplicates) per run. — **[verified]** (`DataQualityReport`, pure, as asset metadata)
3. Failed jobs → dead-letter with retry (via `JobQueue` port). — **[verified]** (`RetryPolicy`: bounded retries + backoff → dead_letter)
4. Reprocess/backfill via asset-aware re-run, no full rebuild. — **[verified]** (materialize `curated_documents` only)

## Deliverables
- `ikip_ingestion/retry.py` (RetryPolicy — pure), `quality_report.py` (DataQualityReport — pure).
- `ikip_ingestion/definitions.py` — lineage graph `ingested_sources → curated_documents → document_versions`; schedule materializes the whole graph.
- Tests: `test_retry.py`, `test_quality_report.py` (pure, CI); `test_definitions.py` extended (lineage graph + asset-aware re-run, `--group dagster`).
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [lineage-reprocessing](../../concepts/lineage-reprocessing.md). Reuses [dagster-orchestration](../../concepts/dagster-orchestration.md), [dedup-versioning](../../concepts/dedup-versioning.md), [object-storage](../../concepts/object-storage.md).

## Closes Epic 2
Data engineering pipeline complete: ingest → extract/OCR → clean/validate → dedup/version → lineage/quality/reprocess.
