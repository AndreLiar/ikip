# MISSION-004 — Reproduction tutorial

Add a multi-tenant data foundation (models, migrations, tenant-scoped repo) to the monorepo.

## Prerequisites
- MISSION-001/002 done; a Neon project; `.env` pointing `DATABASE_URL` at a Neon `dev` branch.

## Steps

1. **Deps** — add `sqlalchemy>=2.0`, `alembic>=1.13`, `psycopg[binary]>=3.2` to `packages/common/pyproject.toml`; `uv sync`.

2. **ORM base** `db/base.py` — `class Base(DeclarativeBase)`; mixins `UUIDPrimaryKey` (uuid pk), `Timestamped` (created/updated), `TenantScoped` (`tenant_id` FK→tenant, indexed).

3. **Models** `db/models.py` — `Tenant(UUIDPrimaryKey, Timestamped, Base)`; `AppUser(UUIDPrimaryKey, TenantScoped, Timestamped, Base)` with `UniqueConstraint("tenant_id","email")`; roles as `enum.StrEnum`.

4. **Session** `db/session.py` — `create_engine(_psycopg_url(settings.database_url))` where `_psycopg_url` swaps `postgresql://` → `postgresql+psycopg://`.

5. **Tenant-scoped repo** `db/repository.py`:
   ```python
   class TenantScopedRepository[ModelT: Base]:
       model: type[ModelT]
       def __init__(self, session, tenant_id): ...
       def _scoped(self): return select(self.model).where(self.model.tenant_id == self.tenant_id)
       def list(self): return self.session.execute(self._scoped()).scalars().all()
       def add(self, obj): obj.tenant_id = self.tenant_id; self.session.add(obj); return obj
   ```

6. **Alembic** — `alembic.ini` (`script_location = migrations`); `migrations/env.py` loads the root `.env` with `load_dotenv(find_dotenv(usecwd=True))`, sets `sqlalchemy.url` from Settings, `target_metadata = Base.metadata`, imports models. Add `script.py.mako`.
   ```bash
   cd packages/common
   uv run --project ../.. alembic revision --autogenerate -m "initial tenant and app_user"
   ```
   **Review the migration** — add enum TYPE drops to `downgrade()` (autogen omits them).
   ```bash
   uv run --project ../.. alembic upgrade head
   uv run --project ../.. alembic downgrade base   # prove reversibility
   ```

7. **Isolation tests** `tests/test_tenant_isolation.py` — `pytest.mark.skipif(not TEST_DATABASE_URL)`; module fixture `create_all`/`drop_all`; per-test session with `rollback`. Seed A+B, assert a tenant-A repo sees only A.
   ```bash
   uv run pytest apps packages -q                          # DB tests skip -> green
   TEST_DATABASE_URL=<throwaway> uv run pytest packages/common/tests/test_tenant_isolation.py -q
   ```

## Common mistakes
- **`Settings` fail-fast when running alembic** → it can't find `.env` from `packages/common`; load it with `find_dotenv(usecwd=True)` in `env.py`.
- **Re-`upgrade` fails "type already exists"** → `downgrade` must drop enum TYPEs, not just tables.
- **`postgresql://` uses psycopg2** → force `postgresql+psycopg://` for psycopg v3.
- **Tests pollute the dev DB** → use an ephemeral Neon branch + flush/rollback; never the shared dev DB.
- **Cross-tenant leak** → never query tenant tables outside the repository.

## Recovery
Additive; revert branch/commit. Tests roll back; `alembic downgrade base` cleans the schema.
