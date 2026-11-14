# Runbook — Reading the Dagster UI (IKIP ingestion)

How to make sense of the Dagster web UI for IKIP's knowledge-base pipeline. Dagster is
**asset-centric** (it models *data that exists*, not tasks), which is the thing that confuses
newcomers. See also the concept note [dagster-orchestration](../learning/concepts/dagster-orchestration.md)
and [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md).

## 0. Open it
```bash
DAGSTER_HOME=$HOME/.ikip-dagster \
  uv run --group dagster --group extraction --group docling-serve --group indra \
          --group doctor --group embeddings \
  dagster dev -m ikip_ingestion.definitions
# → Serving dagster-webserver on http://127.0.0.1:3000
```
`DAGSTER_HOME` makes runs/history persist (and makes CLI `dagster asset materialize` runs show
up in the UI). Launch with the heavy groups so UI-triggered runs can import the engines.

## The mental model (keep this in your head)
```
Code location  →  defines  Assets  +  Schedules/Sensors  →  which trigger  Runs  →  (re)produce Assets
(Deployment tab)           (Assets tab)   (Automation tab)        (Runs tab)
```
- **Asset** = a piece of data that *exists* (e.g. "the embeddings"), not an action.
- **Run** = one execution that (re)materializes assets.
- **Schedule/Sensor** = what *triggers* a run.
- **Code location** = the Python module Dagster loads (`ikip_ingestion.definitions`).

## The tabs

### Assets — the heart
The data **catalog** + the **lineage graph** ("View lineage"). IKIP's chain:
`ingested_sources → curated_documents → document_versions → embedded_chunks`
(plus the asset checks `embedding_dimension_matches_schema`, `chunks_non_empty`). Each asset shows
its **last materialization**, status, and your **metadata** (curated/versions/chunks counts). Click an
asset → its materialization **history** + lineage. **Use it to answer "what data exists, and where did
it come from"** (provenance). _"Never materialized" = that asset was never produced (e.g. `ingested_sources`,
because we load corpora via scripts — see the lineage gap note in the concept doc)._

### Runs — the executions
History of every materialization: **ID, target, launched by, status, created-at, duration**. Click a run →
**step-by-step logs**, per-asset events, failures. `Success` = everything materialized; `Failure`/`Canceled`
= stopped. A run that keeps "Running" for hours with a growing duration after you force-killed its process is
a **zombie** (see Gotchas).

### Automation (Schedules & Sensors) — the triggers
- **Schedule** `daily_ingest` — cron `0 2 * * *` (02:00), materializes the whole pipeline nightly.
- **Sensor** `pending_jobs_sensor` — **STOPPED by default**; when enabled, requests a run as soon as new
  PENDING, not-yet-curated jobs appear ([ADR 0025](../adr/0025-ingestion-trigger-schedule-sensor-queue.md)).
Toggle on/off here; inspect the "tick" history.

### Jobs
Runnable **bundles of assets**. IKIP has `ingest_processing` (curate → version → embed) — the job the sensor
triggers.

### Deployment — the code/infra
The **code locations** Dagster loads (`ikip_ingestion.definitions`): **status** (loaded / error), a **Reload**
button, and daemon/webserver health. A **"View error"** here is a *code-load* problem, not a data problem.

### Overview
Dashboard: recent runs, asset health, schedule/sensor status, timeline.

## Common tasks (your reflexes)
| Question | Where |
|---|---|
| Are my 500 docs indexed? | **Assets** → `embedded_chunks` (last materialization + metadata) |
| Why did it fail? | **Runs** → click the red run → logs |
| When does it run? | **Automation** |
| Is the code loaded? | **Deployment** |
| What produced this chunk/embedding? | **Assets** → lineage (provenance, FR16) |

## Gotchas (seen on IKIP)
- **Zombie runs.** `pkill -9` on a `dagster asset materialize` process leaves its run stuck as "Running"
  with a fake multi-hour duration (Dagster never recorded the end). The data already committed is safe
  (per-doc commits). Clean up: mark them canceled — `DagsterInstance.get().report_run_canceled(run)` for the
  non-terminal run ids (never the live one). Prefer a graceful stop over `-9`.
- **Code location "View error" after editing/branch-switching.** `dagster dev` reloads on file changes; if it
  reloads mid-edit or mid-`git checkout` it can cache a stale error even though the code is valid. Confirm with
  `dagster definitions validate -m ikip_ingestion.definitions`; if it passes, **Reload** the code location, or
  restart `dagster dev`.
- **Two runs on the same `DAGSTER_HOME`.** The default instance uses SQLite; concurrent CLI materializations +
  the UI coexist, but avoid piling many at once.
- **`from __future__ import annotations` + `@asset` context.** Leave the `context` param **unannotated**
  (Dagster rejects a stringized annotation) — a code-location load error if you don't.
