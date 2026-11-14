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

## Why Dagster here (vs Airflow / Prefect / cron) — the defensible choice
Pitch in one line: **IKIP's ingestion produces a *governed knowledge base*, not a sequence of tasks** — so an **asset-centric** orchestrator fits.
- **Asset vs task model.** Airflow/Prefect orchestrate *tasks* (operations); Dagster models *assets* ("this data exists") with **lineage** between them. For a KB where I must trace *which embedding came from which chunk / version / PDF* (provenance, FR16), that is a 1:1 mapping, not an add-on.
- **Asset-aware re-runs.** Change the chunker or embedding model → re-materialize **just** `embedded_chunks` **without** re-OCR'ing the raw. Lived in IKIP (PyMuPDF → hybrid → Indra). Task tools make this a manual bolt-on.
- **Local-first + built-in observability (NFR12).** `dagster dev` = full UI (runs, logs, asset graph, materialization status) with **no infra**; Airflow needs scheduler+webserver+metadata-DB just to run.
- **Software-defined + testable.** Assets are plain functions, tested with fakes (`test_definitions` passes in CI with **no real DB**).
- **Honesty (say it to a jury):** for a **one-shot** load a plain script suffices — IKIP's `fetch_*`/`seed_*` **are** plain scripts. Dagster **earns its place** for an *ongoing, scheduled, audited, evolving* KB. Alternatives weighed: **Airflow** (ubiquitous but task-centric, heavy locally), **Prefect** (light, weaker asset/lineage), **Temporal** (durable workflows, microservice-oriented, not data-assets).

## Where incrementality actually lives (NOT Dagster magic)
"Only reprocess what changed" is real, but it comes from **our DB + domain code**, which Dagster merely orchestrates:
- **"Did it change?" = dedup/versioning** — checksum (exact) + SimHash (near-dup) in `publish_document_version`; identical content → same checksum → skipped; changed → new version that *supersedes* (`is_current`), nothing destroyed (NFR15).
- **"Skip the done" = idempotent per-stage SQL filters** — e.g. `curated_documents` only takes `state=pending AND curated_object_key IS NULL`; `index_version` is rerun-safe; re-embedding is **additive by `model_version`** (FR14).
- **Proof it's not Dagster's doing:** those filters are `WHERE` clauses and the fetch/seed are plain scripts — a bare `cron` + the same SQL would be just as incremental. Dagster adds **lineage + selective re-runs + schedule + retries** on top.
- **The native-Dagster upgrade** (follow-up): **partition per document** → Dagster tracks each doc's state and backfills only the changed partition, with per-doc retry/status in the UI. It *reinforces* the SQL-level incrementality we already have.

## Ingestion execution model — async, scheduled-pull, event-driven-*ready*
- **Asynchronous via a DB-backed job queue.** Acquisition (write raw to the **blob** + create an `IngestionJob` `PENDING`) is **decoupled** from processing; a worker **pulls** `pending` jobs in the background. States: `pending → running → succeeded/failed`. Durable, resumable, idempotent. We never block a request on OCR/embed (minutes).
- **Trigger today = scheduled + manual (pull), i.e. batch.** `daily_ingest_schedule` runs the pipeline daily and pulls whatever's `pending`; plus manual `dagster asset materialize`.
- **Honesty:** the arch lists a `JobQueue` port (Redis→Service Bus) but it is **not implemented** — the real queue is the **`IngestionJob` table**. There is **no `@dg.sensor`** → **not event-driven yet**.
- **Event-driven path (follow-up):** a Dagster **sensor** watching new blob objects / new `pending` jobs, or a message-queue on `enqueue` — same ports, no model change.
- **Blob's role:** the raw blob (R2) is the source-of-truth input; a job carries `raw_object_key`; the worker reads it async → enables **reprocess-from-raw** without re-fetch (NFR15). Raw is **tenant-scoped** (`raw/<tenant>/<source>/<checksum>`), consistent with the `curated/` tier.

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
