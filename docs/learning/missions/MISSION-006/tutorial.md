# MISSION-006 — Reproduction tutorial

Add an object-storage port (R2 adapter) + an `ingestion_job` model.

## Prerequisites
- MISSIONs 001–005; `.env` with R2 creds + `DATABASE_URL` (Neon dev branch); `uv`.

## Steps

1. **Port** `ikip_common/storage/base.py` — `class ObjectStorage(Protocol)` with `put/get/exists/delete/presigned_url`; `ArtifactTier(StrEnum)` raw/cleaned/curated; `tier_key(tier, *parts)` → `"raw/.../..."`.

2. **R2 adapter** `storage/r2.py` — `R2ObjectStorage` using `boto3.client("s3", endpoint_url=..., aws_access_key_id=..., config=Config(signature_version="s3v4"))`, creds from `Settings`. Accept an injectable `client` (for tests). Implement the 5 methods.

3. **Model** `db/models.py` — `IngestionState(StrEnum)`; `IngestionJob(UUIDPrimaryKey, TenantScoped, Timestamped, Base)` with source/state(indexed)/raw_object_key/attempts/error_info(JSONB)/started_at/finished_at. Export from `db/__init__.py`.

4. **Repo** `db/ingestion.py` — `IngestionJobRepository(TenantScopedRepository[IngestionJob])` with `create(...)` and `transition(job, to, error_info=None)` guarded by an `_ALLOWED` map; raise `IllegalStateTransitionError` on bad moves.

5. **Migration**
   ```bash
   cd packages/common
   uv run --project ../.. alembic upgrade head          # DB must be at head to autogen
   uv run --project ../.. alembic revision --autogenerate -m "add ingestion_job"
   # review: add `sa.Enum(name='ingestion_state').drop(op.get_bind(), checkfirst=True)` to downgrade()
   uv run --project ../.. alembic upgrade head
   ```

6. **Tests**
   - `test_storage.py` — a `FakeS3` (in-memory dict) injected into `R2ObjectStorage(client=FakeS3())`; test put/get, exists/delete, presigned, tier_key. No live R2.
   - `test_ingestion_job.py` — gated on `TEST_DATABASE_URL`; test defaults, happy path, retry→dead_letter, illegal transition, tenant scoping.
   ```bash
   uv run pytest apps packages -q                       # storage runs, DB tests skip -> green
   TEST_DATABASE_URL=<branch> uv run pytest packages/common/tests/test_ingestion_job.py -q
   ```

## Common mistakes
- **`alembic autogenerate` → "Target database is not up to date"** → run `alembic upgrade head` first.
- **Re-upgrade fails "type already exists"** → downgrade must drop the enum TYPE.
- **N818 ruff** → exception classes need an `Error` suffix.
- **Calling boto3 in the pipeline** → go through the `ObjectStorage` port so tests can mock it.
- **Overwriting `raw`** → reprocess into `curated`; never mutate the raw tier.

## Recovery
Additive; revert branch/commit. `alembic downgrade -1` removes `ingestion_job`.
