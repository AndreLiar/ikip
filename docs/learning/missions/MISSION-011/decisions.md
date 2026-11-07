# MISSION-011 — Decisions

## D1 — Model stages as chained Dagster assets (lineage for free)
- **Choice:** `ingested_sources → curated_documents → document_versions` via `@asset(deps=[...])`.
- **Why here:** Dagster tracks the dependency graph → lineage, subset re-runs, backfills. The whole point of an orchestrator over a script.
- **Alternative:** one monolithic asset.
- **Trade-off:** more asset nodes; but each is independently (re)materializable.

## D2 — Retry policy is pure; the step applies the effect
- **Choice:** `RetryPolicy.should_retry(attempts)` + `backoff_delay_s(attempts)` return decisions; the Dagster step mutates the `ingestion_job` and re-enqueues via `JobQueue`.
- **Why here:** policy is unit-testable without a DB/queue; separates "what should happen" from side effects.
- **Trade-off:** indirection; worth it for testability.

## D3 — Bounded retries → dead-letter (never infinite)
- **Choice:** retry up to `max_attempts` with capped exponential backoff, then `dead_letter`.
- **Why here:** a poison document must stop retrying and be parked for inspection (Story 2.6 AC3), not loop forever.

## D4 — Quality report is pure, emitted as asset metadata
- **Choice:** `DataQualityReport` computes rates from counts; attached to the asset's `MaterializeResult.metadata` (Dagster UI) and storable.
- **Why here:** measurable runs (AC2) without the report querying anything itself.

## D5 — Reprocess = re-materialize downstream only
- **Choice:** `dg.materialize([curated_documents], selection=[curated_documents])` re-runs just that stage.
- **Why here:** parser/chunker changes shouldn't re-download raw; raw/curated evidence is preserved (NFR15) so it's safe + idempotent.
