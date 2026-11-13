# MISSION-036 — Tenant Isolation & Authorization Security Tests (Epic 6, Story 6.2)

**Mode:** Autonome (first Epic-6 story; proves existing controls) + knowledge transfer.
**Objective:** make **zero cross-tenant disclosure** a provable, required CI gate — adversarial tests that cross-tenant reads (documents, retrieval, source access) and object-level ACL violations are all denied.
**Maps to:** Epic 6 / Story 6.2. Hardens NFR10/FR21; the mechanisms shipped in Epics 1–4, this adds the adversarial proof + gate.

## What already existed (the controls)
- Retrieval SQL scopes `WHERE tenant_id = :tenant` on `chunk`/`embedding`, with citation joins kept within the tenant.
- Object-level ACL (`DocumentPermission`) applied **on chunks** in both arms: no ACL rows = tenant-public; else direct-user or workspace-membership grant.
- The source-url service authorizes `version ∈ tenant` before presigning (short-lived URL).
- Endpoints bind `tenant_id` from the authenticated `Principal` (JWT), never from the request.

Story 6.2 = **prove it adversarially + gate it**, at two layers.

## What was built
### Hermetic API suite — the required gate (runs in `validate`)
`apps/api/tests/test_security_isolation.py` (no DB, no network):
- **authz-before-access (AC2):** `/retrieve`, `/ask`, `/documents/{id}/source-url` → **401** without a token.
- **tenant bound from the JWT, not the request (AC1):** a smuggled `tenant_id` in the body is ignored — the service always receives the principal's tenant; two different JWTs produce two distinct bound tenants. A caller cannot structurally target another tenant.

### DB adversarial suite — the SQL-layer proof (runs in `db-tests`, ephemeral Neon)
`packages/common/tests/test_security_isolation_db.py`:
- **cross-tenant retrieval (AC1):** identical content seeded in tenants A and B; A's lexical **and** vector search return A's chunk and **never** B's.
- **object-level ACL on chunks (AC4):** a restricted doc's chunks are excluded for a non-permitted user, included for a direct-ACL user and via **workspace membership**; a doc with no ACL rows is tenant-public.
- **cross-tenant source access (AC1):** tenant B's `DocumentVersion` is not resolvable under tenant A (the presign authorization query).

### Docs
`docs/architecture/security.md` — a threat → control → test table (also advances Story 6.1).

## Acceptance (Story 6.2)
1. Adversarial cross-tenant reads across documents/retrieval/source — all denied. — **[verified]** (hermetic + DB suites).
2. Authz verified before retrieval and before source access. — **[verified]** (401 tests; tenant-from-principal).
3. Zero cross-tenant disclosure is a required CI gate. — **[verified]** the hermetic suite runs in **`validate`** (a required check); the SQL proof runs in `db-tests`.
4. Object-level permissions enforced on chunks/sources, not just documents. — **[verified]** (ACL-on-chunks tests incl. workspace grant).

## Verification
- ruff + format ✓; `pytest apps packages services` → **252 passed / 48 skipped** (hermetic security tests run; DB security tests skip locally, run on CI's Neon branch).
- The 4 DB tests are gated on `TEST_DATABASE_URL` and were **not** run locally (they `create_all/drop_all`); CI `db-tests` runs them on a throwaway branch.

## Deliverables
- `apps/api/tests/test_security_isolation.py` (hermetic, required gate).
- `packages/common/tests/test_security_isolation_db.py` (DB-gated SQL proof).
- `docs/architecture/security.md` threat→control→test table.

## Follow-ups (noted)
- Story 6.1: expand the threat model doc (this table is the isolation slice).
- Story 6.3: prompt-injection / malicious-document defenses as a required gate (builds on the 5.3 safety gate + the live poisoned-doc finding).
- Defense-in-depth: Postgres RLS (deferred hardening) on top of the application-layer scoping.

## Concepts
Reuses [multi-tenancy](../../concepts/multi-tenancy.md) + [auth-rbac](../../concepts/auth-rbac.md).
