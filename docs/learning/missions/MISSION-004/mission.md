# MISSION-004 — Multi-tenant data foundation (Epic 1, Story 1.5)

**Mode:** Autonome + knowledge transfer (Guidé on the test-DB decision → Neon branching).
**Objective:** the core tenant/user schema, Alembic migrations, and a tenant-scoped repository that structurally prevents cross-tenant access — the security base every later table inherits.
**Maps to:** Epic 1 / Story 1.5.

## Acceptance criteria
1. Migrations create `tenant` + `app_user` with the data-model fields. — **[verified]** (alembic upgrade on the Neon `dev` branch created both tables)
2. Every tenant-owned table carries `tenant_id`; queries are tenant-scoped by default. — **[verified]** (`TenantScoped` mixin + `TenantScopedRepository`)
3. A migration tool (safe, reversible) is configured. — **[verified]** (Alembic; upgrade→downgrade→upgrade proven reversible, incl. dropping enum TYPEs)
4. Tests prove tenant A cannot read tenant B rows. — **[verified locally]** (3 isolation tests pass against the `dev` branch; CI runs them once an ephemeral-branch secret is set)

## Deliverables
- `packages/common/src/ikip_common/db/` — `base.py` (Base + `UUIDPrimaryKey`/`Timestamped`/`TenantScoped`), `models.py` (`Tenant`, `AppUser`, enums), `session.py` (engine from Settings, psycopg driver), `repository.py` (`TenantScopedRepository`).
- Alembic: `alembic.ini`, `migrations/env.py` (URL from `.env` → follows the active Neon branch), `migrations/versions/…_initial…py` (reversible).
- `packages/common/tests/test_tenant_isolation.py` — gated on `TEST_DATABASE_URL`, flush+rollback, create/drop schema.
- Learning: [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Decisions
- **Neon branching** for destructive DB tests (ephemeral branch, not the shared dev DB) — [decisions.md](./decisions.md) D1.
- **Neon environment branches**: `production` (default = prod) + `dev` (daily) + `test/*` (ephemeral) — amends [ADR 0015](../../../adr/0015-neon-serverless-postgres.md).
- **SQLAlchemy + Alembic** — [ADR 0017](../../../adr/0017-sqlalchemy-alembic.md).

## Concepts
Introduces [multi-tenancy](../../concepts/multi-tenancy.md) (isolation models, repository enforcement, RLS backstop). Reuses [config-12-factor](../../concepts/config-12-factor.md).
