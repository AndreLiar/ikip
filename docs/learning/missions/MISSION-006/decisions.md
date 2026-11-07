# MISSION-006 — Decisions

## D1 — `ObjectStorage` as a Protocol port; R2 adapter via boto3
- **Choice:** define `ObjectStorage` as a `typing.Protocol`; `R2ObjectStorage` implements it with boto3 (S3).
- **Why here:** core/pipeline code depends on the port, not R2; tests mock it; R2↔MinIO↔Blob is an adapter swap ([ADR 0003](../../../adr/0003-local-first-ports-and-adapters.md)).
- **Alternative:** call boto3 directly in the pipeline.
- **Trade-off:** a small interface layer; worth it for testability + no vendor lock.

## D2 — Artifact tiers as key prefixes (not separate buckets)
- **Choice:** `ArtifactTier` enum + `tier_key(tier, *parts)` → `raw/… cleaned/… curated/…` in one bucket.
- **Why here:** logical separation (NFR15) with zero extra buckets/config; easy to list a tier by prefix.
- **Alternative:** one bucket per tier.
- **Trade-off:** no per-tier bucket policies; can split later if lifecycle rules diverge.

## D3 — `ingestion_job` with a guarded state machine
- **Choice:** `IngestionState` enum + an `_ALLOWED` transition map; `transition()` rejects illegal moves, stamps `started_at/finished_at`, increments `attempts`.
- **Why here:** makes the lifecycle explicit and safe (pending→running→succeeded/failed; failed→running(retry)/dead_letter) — the base for Story 2.6 (DLQ/retry).
- **Alternative:** a free-form status string set anywhere.
- **Trade-off:** must update the map when adding states; prevents inconsistent status.

## D4 — Tests mock storage; DB tests gated on an ephemeral branch
- **Choice:** storage tests use an in-memory `FakeS3`; job tests run only when `TEST_DATABASE_URL` is set (ephemeral Neon branch in CI).
- **Why here:** hermetic CI, no R2 secret, no shared-DB pollution — consistent with MISSION-002/004.

## D5 — Reversible migration drops the enum type
- Same lesson as MISSION-004: autogen `downgrade` omits the `ingestion_state` enum TYPE; added the drop so re-upgrade works.
