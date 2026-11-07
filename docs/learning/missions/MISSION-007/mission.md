# MISSION-007 — Source connectors & Dagster orchestration (Epic 2, Story 2.2)

**Mode:** Autonome + knowledge transfer.
**Objective:** fetch documents from authorized/licensed sources, store them raw with change detection, create ingestion jobs, and orchestrate it with Dagster — keeping the core Dagster-free and CI-fast.
**Maps to:** Epic 2 / Story 2.2.

## Acceptance criteria
1. Connectors ingest file + API sources (any type is bytes here; parsing is Story 2.3). — **[verified]** (`HttpSourceConnector`, tested with a fake fetcher)
2. Dagster schedules/sensors trigger synchronization. — **[verified]** (`ingested_sources` asset + `daily_ingest` cron; materialized in-process)
3. Authorized crawling respects access/licensing. — **[verified]** (`SourceConfig.ensure_allowed` → `UnauthorizedSourceError` if not authorized or no license)
4. New/changed documents detected + queued. — **[verified]** (checksum-based change detection; raw stored, `ingestion_job` created pending)

## Deliverables
- `services/ingestion/` (uv workspace member): `connectors.py` (SourceConnector, HttpSourceConnector, SourceConfig/SourceDocument), `ingest.py` (`ingest_documents`, SeenStore), `definitions.py` (Dagster asset + schedule — the only Dagster import), `Dockerfile.dagster`.
- Dagster is an **optional dep** (`dagster` dependency-group / package extra) so the fast CI job stays Dagster-free.
- Tests: `test_connectors.py`, `test_ingest.py` (hermetic, run in CI); `test_definitions.py` (Dagster smoke, `--group dagster`).
- CI/pytest now include `services`.
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [dagster-orchestration](../../concepts/dagster-orchestration.md) (assets, schedules, thin-wrapper pattern, gotchas). Reuses [object-storage](../../concepts/object-storage.md), [multi-tenancy](../../concepts/multi-tenancy.md).

## Decisions
Dagster dev = Docker image; prod deferred ([ADR 0002](../../../adr/0002-dual-orchestration-dagster-langgraph.md)). Thin-wrapper to keep CI fast — [decisions.md](./decisions.md).
