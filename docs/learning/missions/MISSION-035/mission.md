# MISSION-035 — Operations & Evaluation dashboards + alerts (Epic 5, Story 5.6)

**Mode:** Guidé (observability-backend choice put to the user) then Autonome.
**Objective:** operator dashboards + alerts for latency, cost, pipeline health and quality, so the platform can be run — and the LLMOps loop (trace → metric → dashboard → alert) is closed.
**Maps to:** Epic 5 / Story 5.6. Realises the Grafana-Cloud half of [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md). Completes Epic 5.

## Decision — observability backend (asked the user)
Chose **Grafana Cloud (free tier)** per AC4. The artifacts (dashboards/alerts/k6) are backend-independent; only the OTLP endpoint differs. Everything is portable by design (see "trial survival" below).

## What was built
- **`Metrics` port + OTel adapter** (`telemetry/metrics.py`): `record_request` (latency histogram + request counter, `status` label), `record_cost` (USD counter), `set_eval_gauge` (quality gauges), `flush`. `OTelMetrics` exports via OTLP (lazy SDK, `otel` group); `build_metrics` is **no-op without `OTEL_EXPORTER_OTLP_ENDPOINT`** → the API runs unchanged locally. `FakeMetrics`/`NullMetrics` for tests. Config: `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`.
- **`/ask` instrumentation**: records latency + cost per request (labelled by status) → the ops dashboard. **`eval run`** pushes the quality aggregate as `ikip_eval_quality{metric=...}` gauges + `flush()` → the eval dashboard.
- **Dashboards** (`grafana/dashboards/`): `ops.json` (p95 latency, error rate, throughput, token cost) + `eval.json` (Recall@K, groundedness, citation resolution, behavior conformity, regression trend; 14-day window to match free-tier retention).
- **Alerts** (`grafana/alerts/rules.yaml`, Prometheus/Mimir format): p95 > 3s, error rate > 5%, token cost > $5/h; recall < 0.6, groundedness < 0.9, behavior_conformity < 1.
- **k6** (`load/k6/ask_load.js`): ramps VUs on `/ask`, SLO thresholds (p95 < 3s, errors < 1%). A committed **artifact run on demand**, NOT a CI gate — see below.
- **Runbook** `docs/runbooks/grafana-cloud-observability.md`: OTLP wiring, dashboard/alert import, k6, trial-survival, prod (Azure Monitor) note.

## k6 is deferred to a deployment (deliberate)
A realistic load test needs a deployed, resource-sized target serving real traffic — IKIP has **no cloud deployment yet** (Epic 6). So k6 is a versioned artifact + documented command (`k6 run` local / `k6 cloud` later), not a CI job. A faked-dependency CI smoke run was **considered and dropped** on the user's call: with Azure/DB faked away it only measures FastAPI overhead — low value. The script is ready for Epic 6.

## Trial survival (free tier) — the feature is NOT locked to the account
- Instrumentation + dashboards + alerts + k6 all live in **git** → re-importable into any Grafana org forever; the app degrades to no-op without an endpoint.
- **Durable data is in Postgres (`query_trace`) + committed eval artifacts**, not in Grafana — losing Grafana loses no history.
- Free-tier metric retention ≈ 14 days (why `eval.json` is a 14-day window); our metrics are low-cardinality (labels: operation/status/metric) → far under the series cap.
- Leaving Grafana = swap `OTEL_EXPORTER_OTLP_ENDPOINT` (Azure Monitor / self-hosted) — **no code change** (the port).

## Acceptance (Story 5.6)
1. Dashboards: p95 latency, error rate, pipeline health, token cost — **[verified]** (`ops.json` + instrumentation; tests assert the panels query our metric names).
2. Eval dashboard: Recall@K, citation correctness, groundedness, regressions — **[verified]** (`eval.json` + `eval run` gauge push).
3. Alerts on thresholds (latency, errors, cost, quality) — **[verified]** (`rules.yaml`; test asserts all rules present).
4. Backends via the port: Langfuse (traces) + Grafana Cloud (metrics/dashboards/alerts/k6), OTel/OTLP — **[verified]** code; live render **[untested live]** (needs a Grafana Cloud account).

## Verification
- ruff + format ✓; `pytest apps packages services` → **243 passed / 44 skipped**. `node --check ask_load.js` ✓. OpenAPI unchanged.
- Metrics tests: Null-without-endpoint, FakeMetrics records, dashboards/alerts/k6 artifacts valid + wired to the emitted metric names; `/ask` records request+cost. OTel adapter construct+record+flush smoke-tested against a dummy endpoint (`--group otel`).

## Deliverables
- `telemetry/metrics.py`; `config.py` OTLP fields; `apps/api/observability.py` (`get_metrics`); `/ask` + `eval run` instrumentation; `otel` dep group; `.env.example`.
- `grafana/dashboards/{ops,eval}.json`; `grafana/alerts/rules.yaml`; `load/k6/ask_load.js`; runbook.
- `tests/test_metrics.py` + `/ask` metric assertion.

## Concepts
Realises [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md). Builds on [[MISSION-026]] (Telemetry port/tracing). Eval numbers explained in [[rag-evaluation-metrics]].
