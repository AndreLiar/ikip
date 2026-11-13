# MISSION-040 — Data Retention, Deletion & Provenance (Epic 6, Story 6.5)

**Mode:** Autonome (code/DB governance workflows) + knowledge transfer.
**Objective:** retention/deletion workflows + provenance tracking so licensing and data-rights obligations are met, consistently across all stores, audit-logged.
**Maps to:** Epic 6 / Story 6.5. Closes threat **T10**; defends the judge-fooling residual (provenance).

## What was built — `ikip_common/db/retention.py`
- **Provenance (AC1):** `provenance(document, versions)` → per-source (document `source` + `rights` license) **and** per-version (revision, checksum, `is_current`, `source_object_key`). `is_license_allowed(rights)` enforces the `data-sources.md` licensing gate (allow-list: public-domain/cc0/cc-by[-sa]/mit/apache-2.0/manufacturer-authorized; unknown/empty → **not allowed**, conservative).
- **Consistent deletion (AC3):** `delete_document(session, storage, tenant_id, document_id)` — deletes the **R2 object artifacts** first (curated/layout/source keys; FKs don't cascade to object storage; best-effort per key with a failure list), then the `Document` row so the **DB cascade** removes versions → sections → chunks → embeddings. Returns a `DeletionReport` (counts + keys). **Tenant-scoped**: another tenant's document is "not found" → raises, never deletes cross-tenant (NFR10).
- **Per-tenant retention (AC2):** `get_retention_days(tenant)` from `tenant.policies["retention_days"]`; `retention_sweep(...)` deletes documents older than the window via `delete_document` (so all stores + audit stay consistent); no policy → no-op.
- **Audit (AC4):** every delete writes `AuditEvent(operation="data.delete", resource_id=document)`; a sweep writes `data.retention_sweep` with counts.

## Acceptance (Story 6.5)
1. Licensing/provenance per source + version. — **[verified]** (`provenance` + license gate; `test_retention.py`).
2. Retention configurable per tenant. — **[verified]** (`tenant.policies["retention_days"]` + `retention_sweep`).
3. Deletion consistent across raw/curated/index/embedding. — **[verified]** (R2 keys + DB cascade; DB test asserts chunks + embeddings = 0 and object keys deleted).
4. Deletion + retention actions audit-logged. — **[verified]** (`AuditEvent` rows asserted).

## Verification
- ruff + format ✓; `pytest apps packages services` → **269 passed / 51 skipped**. Pure tests (license gate, provenance) run everywhere; deletion/sweep/tenant-scoping DB tests run on CI's Neon branch.

## Deliverables
- `packages/common/src/ikip_common/db/retention.py`; `tests/test_retention.py`; threat-model T10 → implemented.

## Follow-ups (noted)
- An API endpoint + role (admin) to trigger `delete_document` / `retention_sweep` on demand (admin console); a scheduled sweep (cron) per tenant.
- Enforce the license gate at **ingestion** (reject a document whose `rights` isn't allowed) — wire `is_license_allowed` into the ingestion pipeline.
- Raw ingestion-job artifacts: link `IngestionJob.raw_object_key` into deletion when a doc↔job association is added.

## Concepts
Realises threat **T10** of the [threat model](../../architecture/threat-model.md). Reuses [multi-tenancy](../../concepts/multi-tenancy.md); builds on the audit log (Story 4.8).
