# MISSION-002 — Reproduction tutorial

Build the config layer + connectivity doctor, from the monorepo scaffold.

## Prerequisites
- The monorepo scaffold (MISSION-001); `uv` installed; a `.env` with managed-service creds.

## Steps

1. **Make the root a uv workspace** — in root `pyproject.toml`:
   ```toml
   [tool.uv.workspace]
   members = ["packages/common"]
   [dependency-groups]
   dev = ["pytest>=8.3", "ruff>=0.7", "ikip-common"]
   doctor = ["boto3>=1.35", "psycopg[binary]>=3.2", "redis>=5.0", "httpx>=0.27"]
   [tool.uv.sources]
   ikip-common = { workspace = true }
   [tool.uv]
   package = false
   ```
   > Gotcha: a `packages/*` glob fails if any matched dir lacks a `pyproject.toml`. List members explicitly until each has one.

2. **Create the package** `packages/common/`:
   - `pyproject.toml` (hatchling build, `packages = ["src/ikip_common"]`, deps `pydantic`, `pydantic-settings`).
   - `src/ikip_common/config.py` — a `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)`, fields using `Field(alias="ENV_NAME")`, secrets as `SecretStr`, and a cached `get_settings()`.
   - `src/ikip_common/__init__.py` exporting `Settings, get_settings`.

3. **Verify config loads** (expected: real host printed, secret masked)
   ```bash
   uv sync
   uv run python -c "from ikip_common import get_settings; s=get_settings(); print(s.r2_bucket, repr(s.r2_secret_access_key))"
   # -> ikip-dev SecretStr('**********')
   ```

4. **Write the doctor** `src/ikip_common/doctor.py` — lazy-import boto3/psycopg/redis/httpx; one check per backend returning pass/fail/skip; `main()` prints a table. Run:
   ```bash
   uv run --group doctor python -m ikip_common.doctor
   ```

5. **Hermetic unit tests** `packages/common/tests/test_config.py` — use `monkeypatch.setenv(...)` and `Settings(_env_file=None)` so no real `.env`/services are touched. Cover: loads-required, missing-required-raises, secrets-masked.
   ```bash
   uv run pytest packages -q   # -> 4 passed
   ```

6. **Wire CI** — in `ci.yml`: `astral-sh/setup-uv`, `uv sync`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest packages`. Make the secret guard match `KEY=value` (not identifiers).

## Common mistakes
- **`ModuleNotFoundError: ikip_common`** → the workspace member isn't installed; add `ikip-common` to the `dev` group (with `[tool.uv.sources] ikip-common = { workspace = true }`).
- **Secret guard false positive** → an `alias="SOME_API_KEY"` string matches a naive grep; match `KEY=value` assignments instead.
- **Doctor crashes with ImportError** → you didn't pass `--group doctor`; or keep the lazy-import/SKIPPED pattern.
- **Secret printed in logs** → type it as `SecretStr`; call `.get_secret_value()` only where needed.

## Recovery
Additive change; revert the branch/commit. No data touched (the doctor only reads/pings).
