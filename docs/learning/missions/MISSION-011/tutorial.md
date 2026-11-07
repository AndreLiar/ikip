# MISSION-011 — Reproduction tutorial

Turn the pipeline into a Dagster lineage graph with quality reporting + retry.

## Prerequisites
- MISSIONs 001–010; `uv`; Dagster via `--group dagster` (or the Docker image).

## Steps

1. **Retry policy** `ikip_ingestion/retry.py` — `RetryPolicy(max_attempts, base_delay_s, max_delay_s)` with `should_retry(attempts) -> retry|dead_letter` and `backoff_delay_s(attempts)` (exponential, capped). Pure.

2. **Quality report** `ikip_ingestion/quality_report.py` — `DataQualityReport` dataclass with counts + `success_rate`/`failure_rate` properties + `as_dict()`. Pure.

3. **Lineage graph** `ikip_ingestion/definitions.py` — add downstream assets:
   ```python
   @dg.asset(deps=[ingested_sources])
   def curated_documents(context): ...      # extract/clean/validate node
   @dg.asset(deps=[curated_documents])
   def document_versions(context):          # dedup/version node
       return dg.MaterializeResult(metadata={"stage": "versions", **DataQualityReport().as_dict()})
   defs = dg.Definitions(assets=[ingested_sources, curated_documents, document_versions], schedules=[...])
   ```
   (Leave `context` unannotated — Dagster gotcha.)

4. **Tests**
   ```bash
   uv run pytest apps packages services -q      # retry + quality report run; dagster skips
   uv run --group dagster pytest services/ingestion/tests/test_definitions.py -q
   ```
   Assert: graph keys contain the 3 assets; `dg.materialize([curated_documents], selection=[curated_documents])` succeeds (asset-aware re-run).

5. **See lineage in the UI** (optional)
   ```bash
   uv run --group dagster dagster dev -m ikip_ingestion.definitions   # graph at :3000
   ```

## Common mistakes
- **One mega-asset** → no lineage/subset re-runs. Chain with `deps=`.
- **Side effects in the retry policy** → keep it pure; apply effects in the step.
- **Infinite retries** → bound them, then dead-letter.
- **Re-downloading raw to reprocess** → re-materialize the downstream asset only.

## Recovery
Additive; revert branch/commit. No data touched.
