# MISSION-002 — Configuration & connectivity (Epic 1, Story 1.2)

**Mode:** Guidé (scope decision: drop Docker Compose) → Autonome (implementation) + knowledge transfer.
**Objective:** a typed 12-factor config layer loaded from `.env`, plus a connectivity "doctor" that verifies the managed backends — the foundation every service imports.
**Maps to:** Epic 1 / Story 1.2 (reshaped: managed-services-first, no Docker Compose).

## Decision that reshaped the story
The user asked: "do I still need Docker Compose given Neon/R2/Redis Cloud/Langfuse are managed?" Answer: **no for day-to-day dev** (the app points `.env` at managed services); Docker's real value was hermetic test DBs, which we defer to a **CI Postgres service container** (Story 1.3/1.5). Story 1.2 therefore became **config + connectivity**, not "Docker Compose up". NFR17 softened: offline is possible via the ports but not shipped. See [decisions.md](./decisions.md) D1.

## Acceptance criteria (reshaped Story 1.2)
1. Typed settings (Pydantic `BaseSettings`) in `packages/common`, loaded from `.env`, fail-fast on missing required, secrets as `SecretStr`. — **[verified]**
2. Connectivity `doctor` reports pass/fail per backend without printing secrets. — **[verified]** (ran green against Neon+pgvector, R2, Redis, Langfuse)
3. Hermetic unit tests (env monkey-patched, no live services) run in CI. — **[verified]** (4 passed; CI runs `uv run pytest`)
4. No local Docker Compose; offline via ports only; DB tests use a CI Postgres service container later. — **[verified]** (documented)

## Deliverables
- `packages/common/` — first real Python package (uv workspace member): `src/ikip_common/{config.py,doctor.py,__init__.py}`, `pyproject.toml`, `tests/test_config.py`.
- Root `pyproject.toml` — uv workspace + `dev`/`doctor` dependency groups; `uv.lock` committed.
- `.github/workflows/ci.yml` — now `uv sync` + ruff + `pytest` + hardened secret guard.
- README dev setup (uv sync, doctor); Node pinned to 22 LTS (`.nvmrc`).
- Learning: [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Reuses [concepts/dev-tooling.md](../../concepts/dev-tooling.md); introduces [concepts/config-12-factor.md](../../concepts/config-12-factor.md) (env-based config, Pydantic Settings, SecretStr, fail-fast).

## Related decisions
Ports & adapters [ADR 0003](../../../adr/0003-local-first-ports-and-adapters.md) · managed-first [ADR 0012](../../../adr/0012-local-first-dev-cloud-models-only.md) · Neon [ADR 0015](../../../adr/0015-neon-serverless-postgres.md) · R2 [ADR 0014](../../../adr/0014-cloudflare-r2-object-storage.md).
