# MISSION-007 — Execution log

Labels: `[verified]` = run with observed output · `[proposed]` = not run here.

## Steps
1. **Package `services/ingestion`** `[verified]` — core deps ikip-common+httpx; Dagster as an optional extra. Registered in uv workspace + dev group; `services` added to pytest paths + CI.
2. **Connectors** `[verified]` — `SourceConfig` (authorized+license gate), `SourceDocument`, `SourceConnector` Protocol, `HttpSourceConnector` (injectable `Fetcher`).
3. **Ingest logic** `[verified]` — `ingest_documents`: checksum, change detection via `SeenStore`, store raw (ObjectStorage), create `ingestion_job`. Pure + injected.
4. **Dagster wiring** `[verified]` — `definitions.py`: `@asset ingested_sources`, `daily_ingest` schedule, `Definitions`. Only file importing Dagster.
5. **Dagster gotcha fixed** `[verified]` — in-process `materialize` failed: `from __future__ import annotations` + `context: AssetExecutionContext` rejected by Dagster. Left `context` unannotated → works.
6. **Dagster smoke (in-process)** `[verified]` — `dg.materialize([ingested_sources])` → success; metadata `{ingested:0, skipped:0}` (no tenant); schedule `daily_ingest` present.
7. **CI isolation of Dagster** `[verified]` — confirmed `dagster installed: False` in the dev env; `test_definitions.py` skips in `validate`, passes via `uv run --group dagster` (1 passed).
8. **Dockerfile.dagster** `[verified-authored]` — python:3.12-slim + uv, installs the dagster extra, `CMD dagster dev -m ikip_ingestion.definitions`. (Image build itself: `[proposed]`.)
9. **ruff** `[verified]` — import-sort fixes; lint+format green.

## Validation summary
- Connector + ingest hermetic tests pass `[verified]`
- Change detection (skip unchanged, re-ingest changed) `[verified]`
- Authorization/licensing gate raises `[verified]`
- Dagster asset+schedule load and materialize in-process `[verified]`
- Fast suite: 28 passed, 8 skipped (dagster skips) `[verified]`
- With dagster group: definitions test 1 passed `[verified]`
- CI (validate + db-tests) → `[proposed]` (observed on PR)

## Rollback
Additive (new service package + CI/pytest path). Revert branch/commit. No data touched (ingest tests use fakes; the asset no-ops without a tenant).

## Follow-up
- Source configs from a DB table (not env JSON).
- DB-backed `SeenStore` via document versions (Story 2.5).
- A Dagster sensor for event-driven sync (currently a daily schedule).
