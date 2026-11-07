# Concept — Lineage, data-quality reporting & reprocessing

_Write-once concept note. First used by [MISSION-011](../missions/MISSION-011/mission.md). Closes the data-engineering pipeline (Epic 2)._

## Lineage: the pipeline as a graph of assets
Instead of one big script, the pipeline is a **chain of Dagster assets**, each depending on the previous:

```
ingested_sources  ──▶  curated_documents  ──▶  document_versions
(raw in R2 + jobs)     (extract/clean/validate)   (dedup + version)
```

Dagster tracks these **dependencies** — that's **lineage**: for any output you can see what it came from, and re-materialize downstream nodes knowing their inputs. This is the whole reason to use an orchestrator over a script (see [dagster-orchestration](./dagster-orchestration.md)).

## Why lineage matters operationally
It answers the questions a script can't:
- *Which docs failed yesterday?* → query job states.
- *I changed the parser — reprocess without re-downloading.* → re-materialize `curated_documents` **only**; `ingested_sources` (raw) stays. This is **asset-aware re-run** (AC4): Dagster lets you select a subset of the graph.
- *What produced this version?* → walk the lineage back to the raw file.

## Data-quality report: measure every run
Each run emits a **`DataQualityReport`**: totals, success/failure rates, duplicates skipped, dead-letters, low-quality docs. It's attached as **asset metadata** (visible in the Dagster UI) and can be stored. Computed from counts the step feeds it — the report itself is pure (no queries), so it's unit-testable.

```
success_rate = succeeded / total
failure_rate = (failed + dead_letter) / total
```

## Retry + dead-letter: fail safely, don't lose work
A transient failure (network, a flaky source) shouldn't kill a run or silently drop a document. The **retry policy** (pure):
- retry up to `max_attempts` with **exponential backoff** (capped),
- after exhaustion → **dead-letter** state (parked for inspection, not retried forever).

The policy decides *what* should happen (`retry` vs `dead_letter` + the delay); the Dagster step applies it to the `ingestion_job` (via the repo) and re-enqueues via the `JobQueue` port (Redis dev → Service Bus prod). Separating *policy* from *effect* keeps it testable.

## Reprocessing / backfill
Because stages are assets with lineage:
- **Reprocess** = re-materialize a downstream asset after a code change (parser, chunker) without rebuilding upstream.
- **Backfill** = materialize over a range/partition of inputs.
Original evidence is never lost (raw tier + versioned curated artifacts, NFR15), so reprocessing is safe and idempotent (change detection + checksum from Stories 2.2/2.5).

## Rules to remember
1. Model stages as **assets with `deps`** → Dagster gives you lineage for free.
2. Make retry a **pure policy**; apply the effect in the step.
3. Dead-letter after bounded retries; never infinite-retry.
4. Emit a **quality report per run** as asset metadata.
5. Reprocess by re-materializing downstream only — never destroy raw/curated evidence.

## Related
- [dagster-orchestration](./dagster-orchestration.md) (assets/schedules/thin wrapper) · [object-storage](./object-storage.md) (raw/curated tiers) · [dedup-versioning](./dedup-versioning.md) · [multi-tenancy](./multi-tenancy.md).
- Story 2.6 closes Epic 2 (data engineering). Queue backend per [ADR 0009](../../adr/0009-caching-strategy.md).
