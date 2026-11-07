# MISSION-006 — Object storage port & ingestion-job model (Epic 2, Story 2.1)

**Mode:** Autonome + knowledge transfer.
**Objective:** store raw files in object storage behind a swappable port, and track every source file through an `ingestion_job` with a safe lifecycle — the base the Dagster pipeline (Story 2.2+) builds on.
**Maps to:** Epic 2 / Story 2.1.

## Acceptance criteria
1. `ObjectStorage` port with a Cloudflare R2 (S3) adapter stores raw files; MinIO/mocks back the same port. — **[verified]** (live R2 put/get/exists/presigned/delete via the port)
2. `ingestion_job` table records source, state, timestamps, error info. — **[verified]** (model + reversible migration on the Neon `dev` branch)
3. Raw/cleaned/curated artifacts logically separated. — **[verified]** (`ArtifactTier` + `tier_key` prefixes, NFR15)
4. Tests cover upload/retrieve and job state transitions; storage mockable in CI. — **[verified]** (storage tests use a fake S3; job lifecycle tests on an ephemeral branch)

## Deliverables
- `ikip_common/storage/` — `base.py` (`ObjectStorage` Protocol, `ArtifactTier`, `tier_key`), `r2.py` (`R2ObjectStorage` boto3/S3 adapter).
- `ikip_common/db/models.py` — `IngestionJob` (+ `IngestionState`); `db/ingestion.py` — `IngestionJobRepository` with guarded state transitions.
- Alembic migration `…_add_ingestion_job` (reversible, drops the enum type).
- Tests: `test_storage.py` (hermetic, fake S3), `test_ingestion_job.py` (DB-gated).
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Reuses [multi-tenancy](../../concepts/multi-tenancy.md) (job repo is tenant-scoped), [config-12-factor](../../concepts/config-12-factor.md). Introduces [object-storage](../../concepts/object-storage.md) (ports, S3 abstraction, artifact tiers, presigned URLs).

## Decisions
- Dagster hosting: dev = Docker image; prod = deferred — [ADR 0002 update](../../../adr/0002-dual-orchestration-dagster-langgraph.md).
- R2 behind the `ObjectStorage` port — [ADR 0014](../../../adr/0014-cloudflare-r2-object-storage.md), [ADR 0003](../../../adr/0003-local-first-ports-and-adapters.md).
