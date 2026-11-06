# Concept — Health checks (liveness vs readiness)

_Write-once concept note. First used by [MISSION-003](../missions/MISSION-003/mission.md). Reused whenever a service exposes health/probes._

## Why a health endpoint exists
An orchestrator (Azure Container Apps, Kubernetes) needs to ask a service two different questions:
- **Liveness** — "is the process alive?" If not, **restart** it.
- **Readiness** — "can it serve traffic *right now*?" (deps reachable, warmed up). If not, **stop routing** to it but don't restart.

Conflating them is a classic mistake: if a readiness check restarts the pod whenever the DB blips, you get restart storms. Keep the *intent* clear even if you expose one endpoint.

## IKIP's `/api/v1/health` (readiness-style)
Returns the service status **plus each configured dependency's** status, and uses the HTTP code as the signal:
- **200** when all dependency probes pass → safe to route.
- **503** when any probe fails (`status: "degraded"`) → orchestrator should pull it from rotation.

```json
{ "status": "ok", "service": "ikip-api", "version": "0.1.0",
  "dependencies": [ {"service": "neon", "ok": true, "detail": "connected; pgvector=yes"}, … ] }
```
`ok: null` = **skipped** (an optional backend not configured) — not a failure.

## Design rules that matter
1. **Probes must be cheap and time-bounded.** A health check that does heavy work or has no timeout becomes a self-inflicted outage. (IKIP reuses `ikip_common.doctor` checks, each with a connect timeout.)
2. **Reuse one definition of "healthy".** The CLI `doctor` and the API `/health` call the **same** check functions — no drift.
3. **Make probes mockable.** Tests must pass in CI without live services: inject/patch the probe function (`monkeypatch.setattr(health_mod, "run_checks", …)`). Then prove the *real* probes once by running the app live (separate evidence).
4. **Never leak secrets** in the health body or logs — report `service` + `ok` + a short non-sensitive `detail`.

## When to split liveness vs readiness
Introduce distinct `/livez` (always 200 if the event loop runs) and `/readyz` (dependency probes) once you have autoscaling/rolling deploys where restart-vs-derotate must differ. Until then, one readiness endpoint is enough.

## Related
- Config feeding the probes: [config-12-factor](./config-12-factor.md).
- The shared probe functions live in `ikip_common.doctor` (also the CLI doctor).
- Ports/adapters behind each dependency: [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md).
