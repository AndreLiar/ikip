# 0025. Ingestion triggering: scheduled-pull now → Dagster sensor → message-queue (a deliberate progression)

- **Status:** Accepted
- **Date:** 2026-11-14
- **Deciders:** Architect, PM
- **Related:** [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md) (dual orchestration) · [ADR 0003](./0003-local-first-ports-and-adapters.md) · Story 2.2 (ingestion) · concept [dagster-orchestration](../learning/concepts/dagster-orchestration.md)

## Context
Ingestion is **asynchronous**: acquisition writes the raw bytes to the blob (R2) and creates an `IngestionJob` (`pending`); processing happens later in the Dagster pipeline (`curated_documents → document_versions → embedded_chunks`). The open question is **how the processing is triggered**.

Today the **only** trigger is a daily **schedule** (`daily_ingest_schedule`, cron `0 2 * * *`), plus manual `dagster asset materialize`. There is **no** `@dg.sensor` and **no** message queue (the `JobQueue` port is named in the architecture doc but not implemented — the real async queue is the `ingestion_job` table). So a newly-added document waits up to ~24 h to become searchable.

Forces:
- The corpus is **low-velocity** (industrial manuals revise quarterly; batch source-sync) → a schedule is appropriate and cheapest.
- But **interactive / self-service upload** ("I added this manual, it should be searchable now") needs **near-real-time** ingestion, which a daily schedule cannot give.
- We must not over-build: a message queue (Service Bus + a consumer service + backpressure) is real operational weight, justified only at scale.

## Decision
Adopt a **three-step progression**, driven by need, not hype — all behind the same ports, no model change:

1. **Scheduled-pull (now, default).** The daily `ScheduleDefinition` pulls whatever is `pending`. Correct for batch source-sync; zero extra infra.
2. **Dagster sensor (implemented here, opt-in).** `pending_jobs_sensor` watches the `ingestion_job` table and requests a pipeline run when **new** `pending`, not-yet-curated jobs appear — near-real-time ingestion **without** a message queue, staying entirely inside Dagster. Ships **stopped by default** (`DefaultSensorStatus.STOPPED`); enable it in the UI when interactive upload is live. The sensor uses the latest job `created_at` as a **watermark cursor** so it fires once per new batch, not repeatedly while a run drains the backlog.
3. **Message-queue (future, scale).** A real queue (Redis/Azure Service Bus) + a consumer, triggered on `enqueue`, is the path for **high-velocity, multi-tenant** ingestion that needs to decouple and scale the workers independently of the Dagster run. Deferred until volume/SLA demands it.

## Consequences
**Positive**
- Each deployment runs the **right level of complexity**: batch → schedule; interactive → sensor; scale → queue.
- The sensor gives event-like latency (~seconds) with **no new infrastructure** — it reuses the `IngestionJob` table as the signal and the existing assets as the work.
- The progression is a single, defensible story (not a rebuild at each step): the trigger changes, the async job-table + idempotent assets do not.

**Negative / watch**
- The sensor is a **poll** (the daemon evaluates it on an interval), not a push — fine for our latencies, but it is not a true event bus.
- The watermark cursor (latest `created_at`) is a pragmatic heuristic; a production version would also check for in-flight runs / use a durable watermark.
- Running the sensor means running the Dagster **daemon** (already required for schedules) — a ~always-on process, the main prod cost (noted in ADR 0002).

## Alternatives considered
- **Tighter cron** (e.g. every 15 min) — one-line, cuts latency without a sensor; good enough if sub-minute isn't needed. The sensor wins when you want ~seconds and event-shaped behaviour.
- **Message queue now** — rejected as premature (YAGNI): operational weight unjustified for a low-velocity batch KB; it is the documented scaling step, not the starting point.
- **Blob-event trigger (R2/S3 notifications)** — viable later, but couples the trigger to the storage vendor; the job-table sensor stays portable (ADR 0003).
