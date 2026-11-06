# MISSION-003 — FastAPI skeleton & health endpoint (Epic 1, Story 1.3)

**Mode:** Autonome + knowledge transfer.
**Objective:** a deployable FastAPI baseline exposing `GET /api/v1/health` that reports service + dependency status, with structured logging and hermetic tests.
**Maps to:** Epic 1 / Story 1.3.

## Acceptance criteria
1. `GET /api/v1/health` returns service status + each configured dependency's status. — **[verified]** (ran live: 200, neon/r2/redis/langfuse all ok)
2. Pydantic settings load from env; fail-fast on missing required. — **[verified]** (`create_app()` calls `get_settings()` at startup)
3. Structured logging configured; no secrets logged. — **[verified]** (JSON logs; settings never passed to logger)
4. Unit + integration tests pass in CI; dependency checks mockable (no live services). — **[verified]** (8 tests pass; `run_checks` monkeypatched)

## Deliverables
- `apps/api/` — FastAPI app (uv workspace member): `src/ikip_api/{main,health,logging_config,__init__}.py`, `pyproject.toml`, `tests/test_health.py`.
- Root `pyproject.toml` — `apps/api` added to workspace + dev group; `pytest` testpaths include `apps`.
- `ci.yml` — `uv run pytest apps packages`.
- Learning: [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Reuses [config-12-factor](../../concepts/config-12-factor.md) and [dev-tooling](../../concepts/dev-tooling.md); introduces [health-checks](../../concepts/health-checks.md) (liveness vs readiness, dependency probes, mockability).

## Related decisions
Ports/adapters [ADR 0003](../../../adr/0003-local-first-ports-and-adapters.md) · API versioning [ADR 0008 context]; reuses `ikip_common.doctor` checks.
