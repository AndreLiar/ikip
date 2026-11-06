# MISSION-003 — Decisions

## D1 — Health endpoint = readiness (200 ok / 503 degraded)
- **Problem:** should `/health` be liveness (is the process up) or readiness (are deps reachable)?
- **Choice:** readiness semantics — probe each configured backend; **200** when all pass, **503** when any fails. Body always lists per-dependency status.
- **Why here:** Story 1.3 AC1 explicitly wants dependency status in `/health`; 503-on-degraded lets an orchestrator (Container Apps) stop routing to an unhealthy instance.
- **Alternative:** split `/livez` (always 200 if up) and `/readyz` (deps). 
- **Trade-off:** a slow/flaky dependency can make `/health` flap; probes must stay cheap and time-bounded.
- **Switch when:** we add autoscaling/orchestration needing distinct liveness vs readiness → split the endpoints.

## D2 — Reuse `ikip_common.doctor.run_checks` for probes
- **Choice:** the endpoint reuses the same check functions as the CLI doctor.
- **Why here:** DRY — one definition of "is Neon/R2/Redis/Langfuse healthy", used by both the CLI and the API.
- **Alternative:** a separate lighter liveness probe in the API.
- **Trade-off:** the doctor's checks do real work (connect, query pgvector, list bucket) — heavier than a bare TCP ping, but more meaningful.
- **Switch when:** probe latency hurts; add a lightweight variant for high-frequency liveness.

## D3 — Structured JSON logging with stdlib (no structlog)
- **Choice:** a small `JsonFormatter` on stdlib `logging` — zero extra deps.
- **Why here:** one JSON line per record is machine-parseable (Azure Monitor / Grafana ingestion later) without pulling in a logging framework for a skeleton.
- **Alternative:** `structlog` (richer context binding).
- **Trade-off:** less ergonomic context binding than structlog; fine for now.
- **Switch when:** we need request-scoped context propagation across services → adopt structlog.

## D4 — Mockable probes for hermetic CI
- **Choice:** tests `monkeypatch` `ikip_api.health.run_checks` to return canned `CheckResult`s; `create_app()` reads monkeypatched env.
- **Why here:** CI must pass without live services or secrets (AC4). Logic (status computation) and the endpoint (via `TestClient`) are both tested offline.
- **Alternative:** hit real services in CI (needs secrets, flaky, slow).
- **Trade-off:** mocks don't prove the real probes work — so we **also ran the app live** once ([execution.md](./execution.md)) as separate evidence.
