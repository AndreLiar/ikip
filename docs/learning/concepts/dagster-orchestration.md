# Concept — Dagster orchestration (assets, schedules, thin wrapper)

_Write-once concept note. First used by [MISSION-007](../missions/MISSION-007/mission.md). Reused by every pipeline step (Epic 2)._

## What Dagster is (plain)
Dagster is a **data orchestrator**: it runs your data-processing steps in the right order, on a schedule, tracks success/failure, and lets you **re-run** just what broke. In IKIP it builds and maintains the **knowledge base** (ingest → parse → clean → chunk → embed → index). The *other* orchestrator, LangGraph, answers one technician's question at request time — different job, different clock ([ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md), see [dagster-vs-langgraph](../../architecture/dagster-vs-langgraph.md)).

## Core pieces (as used here)
- **Asset** (`@dg.asset`) — a declared piece of data ("ingested sources") and the function that produces it. Dagster knows assets' dependencies, so it can materialize/re-materialize them.
- **Schedule** (`dg.ScheduleDefinition`) — "materialize this asset on a cron" (`0 2 * * *` = 02:00 daily).
- **Definitions** (`dg.Definitions`) — the registry Dagster loads (`assets=[...]`, `schedules=[...]`). Pointed at with `-m ikip_ingestion.definitions`.
- **webserver + daemon** — the UI (http://localhost:3000) and the process that fires schedules/sensors. Run together in dev via `dagster dev`.

## The key pattern: thin Dagster wrapper over pure logic
**Don't put real work inside the `@asset`.** IKIP keeps the ingestion logic (connectors, `ingest_documents`) **Dagster-free and pure** (injected storage/db/seen-store), and the `@asset` just *calls* it. Why:
- the logic is **unit-testable without Dagster** → runs in the fast CI job (no heavy install, no daemon);
- Dagster is an **optional dependency** (installed only in the Dagster image / `--group dagster`);
- you can swap orchestrators later without rewriting the pipeline.

```
connectors.py / ingest.py   # pure, tested in CI, no dagster import
definitions.py              # @asset + schedule — the ONLY file importing dagster
```

## Running it (dev)
- Docker image (IKIP default, [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md)): `docker build -f services/ingestion/Dockerfile.dagster -t ikip-dagster . && docker run -p 3000:3000 --env-file .env ikip-dagster`.
- Or no Docker: `uv run --group dagster dagster dev -m ikip_ingestion.definitions`.
- **Prod hosting is deferred** — the daemon is ~always-on, the main prod cost to weigh.

## Gotchas (hit in IKIP)
- **`from __future__ import annotations` breaks Dagster's `context` type check.** Leave the `context` parameter **unannotated** in `@asset` functions (Dagster introspects the real type and rejects a stringized annotation).
- **Materialize in-process for tests** with `dg.materialize([asset])` — no daemon needed; great for a wiring smoke test.
- Keep secrets out of the image — pass `.env` at `docker run`, never bake them in.

## Rules to remember
1. Pipeline *logic* is pure + injected; the `@asset` is a thin wrapper.
2. Dagster stays an optional dep so CI (and the core package) stay light.
3. Schedules live in `Definitions`; the daemon fires them.
4. Change detection / idempotency belong in the pure logic (so re-runs are safe), not in Dagster plumbing.

## Related
- [dagster-vs-langgraph](../../architecture/dagster-vs-langgraph.md) · [object-storage](./object-storage.md) · [config-12-factor](./config-12-factor.md).
- [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md) (dual orchestration; dev=Docker, prod deferred).
