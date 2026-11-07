# MISSION-004 — Execution log

Labels: `[verified]` = run with observed output · `[proposed]` = not run here.

## Steps
1. **Neon `dev` branch** `[verified]` — created in console (auto-delete OFF), connection verified: Postgres 18.6, pgvector 0.8.6. `.env` repointed to `dev`.
2. **DB layer** `[verified]` — `db/base.py` (Base + mixins), `db/models.py` (Tenant, AppUser, StrEnum roles), `db/session.py` (psycopg driver), `db/repository.py` (`TenantScopedRepository`). Deps added to `ikip-common` (sqlalchemy, alembic, psycopg).
3. **Smoke isolation (pre-Alembic)** `[verified]` — create_all on `dev`, seed A/B, `UserRepo(s, a.id).list()` → only A's rows; drop_all. "ISOLATION OK".
4. **Alembic** `[verified]` — `alembic.ini`, `migrations/env.py` (loads root `.env` via `find_dotenv(usecwd=True)` so it works from `packages/common`; URL from Settings). `--autogenerate` produced the initial migration.
5. **Made migration reversible** `[verified]` — autogen `downgrade` only dropped tables; added enum TYPE drops. Proven: `upgrade head` → tables present → `downgrade base` → `upgrade head` (would fail without the enum drop) → `downgrade base`. "migration is reversible". `dev` left clean.
6. **pytest isolation tests** `[verified]` — gated on `TEST_DATABASE_URL`; without it → **skipped** (CI stays green: 8 passed, 3 skipped). With `TEST_DATABASE_URL=dev` → **3 passed** (lists only own tenant; can't `get` other tenant's row; `add` stamps tenant_id).
7. **Modernization (ruff)** `[verified]` — `StrEnum` (UP042), PEP 695 generics `class TenantScopedRepository[ModelT: Base]` (UP046), import sort (I001). ruff lint+format green.

## Validation summary
- Migration creates tenant + app_user `[verified]`
- Migration reversible (incl. enum types) `[verified]`
- Tenant isolation: 3 tests pass vs real `dev` branch `[verified]`
- CI (no TEST_DATABASE_URL): 8 passed, 3 skipped `[verified]`
- CI ephemeral-branch run → `[proposed]` (needs NEON_API_KEY secret)

## Rollback
Additive (new db module + migration + tests). Revert branch/commit. The `dev` branch was left clean (downgraded to base; tests roll back).

## Follow-up
Wire a `db-tests` CI job that creates an ephemeral Neon branch (NEON_API_KEY + project id in GitHub secrets), sets `TEST_DATABASE_URL`, runs the DB tests, deletes the branch. Activates AC4 in CI.
