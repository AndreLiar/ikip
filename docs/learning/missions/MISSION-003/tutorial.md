# MISSION-003 — Reproduction tutorial

Add a FastAPI app with a dependency-aware health endpoint to the monorepo.

## Prerequisites
- MISSION-001/002 done (monorepo, `ikip_common.config` + `doctor`); `uv`.

## Steps

1. **Create `apps/api/pyproject.toml`** — `name = "ikip-api"`, deps `fastapi`, `uvicorn[standard]`, `ikip-common`, and the probe clients (`boto3`, `psycopg[binary]`, `redis`, `httpx`); hatchling build; `[tool.uv.sources] ikip-common = { workspace = true }`.

2. **Register the member** — in root `pyproject.toml`: add `apps/api` to `[tool.uv.workspace].members`, add `ikip-api` to the `dev` group and `[tool.uv.sources]`. Set `testpaths = ["packages","apps","tests"]`.

3. **Structured logging** `src/ikip_api/logging_config.py` — a `JsonFormatter(logging.Formatter)` emitting one JSON line; `configure_logging()` installs it on the root logger.

4. **Health module** `src/ikip_api/health.py`:
   - reuse `from ikip_common.doctor import run_checks, CheckResult`;
   - `_to_status(results)` → `status="degraded"` if any `ok is False` else `"ok"`;
   - `@router.get("/health")` sets `response.status_code` to 503 when degraded, else 200.

5. **App factory** `src/ikip_api/main.py` — `create_app()` calls `configure_logging()`, `get_settings()` (fail-fast), and `app.include_router(health.router, prefix="/api/v1")`.

6. **Tests** `apps/api/tests/test_health.py` — monkeypatch env + `get_settings.cache_clear()`; unit-test `_to_status`; integration via `TestClient(create_app())` with `monkeypatch.setattr(health_mod, "run_checks", lambda *a, **k: results)`.
   ```bash
   uv sync
   uv run pytest apps packages -q    # -> 8 passed
   ```

7. **Run it for real** (optional, needs `.env`)
   ```bash
   uv run uvicorn ikip_api.main:app --port 8000
   curl -s localhost:8000/api/v1/health | python -m json.tool
   # -> 200, dependencies all "ok"
   ```

## Common mistakes
- **ruff format fails** → 2 blank lines before top-level functions; run `uv run ruff format .`.
- **`ModuleNotFoundError: ikip_api`** → add `ikip-api` to the `dev` group + `[tool.uv.sources]`, then `uv sync`.
- **CI hits live services** → mock `run_checks` in tests; never require secrets in CI.
- **Secret in logs** → never pass `Settings` to the logger; log plain messages only.

## Recovery
Additive; revert the branch/commit. No data touched.
