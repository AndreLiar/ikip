# Runbook — Operations & Evaluation dashboards on Grafana Cloud (Story 5.6)

Wire the API's OpenTelemetry metrics to **Grafana Cloud** (free tier), import the dashboards + alert rules, and run the k6 load test. Backends via the `Telemetry`/`Metrics` ports (ADR 0013): Langfuse = LLM/RAG traces + eval scores; Grafana Cloud = infra metrics/dashboards/alerts/k6.

## 1. Point the API at Grafana Cloud (OTLP)
Create a Grafana Cloud stack → **Connections → OTLP**. Copy the endpoint + generate an API token, then set the standard OTel env vars (the exporter reads them directly):

```bash
# .env (gitignored) — values from Grafana Cloud "OTLP" connection page
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<zone>.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64(instanceID:token)>
OTEL_SERVICE_NAME=ikip-api
```

Install the exporter and run the API with it:
```bash
uv sync --group otel
uv run uvicorn ikip_api.main:create_app --factory
```
Without `OTEL_EXPORTER_OTLP_ENDPOINT`, metrics are a **no-op** — the API runs unchanged. The `/ask` endpoint then emits:
`ikip_request_duration_ms` (histogram), `ikip_requests_total` (counter, `status` label), `ikip_request_cost_usd` (counter).

## 2. Push evaluation quality (for the eval dashboard)
`eval run` pushes the quality aggregate as `ikip_eval_quality{metric=...}` gauges (same OTLP env):
```bash
uv run --group embeddings --group otel python -m ikip_common.eval run \
    --gold eval-results/failure_modes.resolved.json --tenant <uuid> --out eval-results
```
Schedule it (cron / nightly `ragas-eval.yml`) so the eval dashboard trends over time.

## 3. Import the dashboards
Grafana Cloud → **Dashboards → New → Import** → upload:
- `grafana/dashboards/ops.json` — p95 latency, error rate, throughput, token cost.
- `grafana/dashboards/eval.json` — Recall@K, groundedness, citation resolution, behavior conformity, regression trend.

Pick your **Prometheus** datasource for the `DS_PROMETHEUS` variable when prompted.

## 4. Import the alert rules
Grafana Cloud → **Alerts & IRM → Alert rules** (or the Mimir ruler) → import `grafana/alerts/rules.yaml`:
- ops: p95 > 3s (10m), error rate > 5% (5m), token cost > $5/h.
- quality: recall < 0.6, groundedness < 0.9, behavior_conformity < 1.

Attach a **contact point** (Slack/email) + a notification policy so the alerts route somewhere. Thresholds are starting points — tune per environment.

## 5. Load test (k6) — on demand, deferred to a deployment
`load/k6/ask_load.js` is a committed artifact, **not a CI gate**. A realistic load test needs a deployed, resource-sized target — IKIP has no cloud deployment yet (**Epic 6**). Until then, run it against a locally-running API, or `k6 cloud` once a staging/prod URL exists:
```bash
# local target (needs AUTH_DEV_LOGIN=true on the API)
BASE_URL=http://localhost:8000 TENANT_ID=<uuid> k6 run load/k6/ask_load.js
# Grafana Cloud k6 against a deployed URL (Epic 6):
k6 cloud load/k6/ask_load.js
```
SLO thresholds in the script: **p95 < 3s**, **error rate < 1%**. The same run drives the OTel metrics the ops dashboard shows — run k6 while watching the dashboard to validate the end-to-end path. (A faked-dependency CI smoke run was considered and dropped: with Azure/DB faked away it only measures framework overhead.)

## Surviving the free trial → Free (Forever) tier
**Nothing here is locked to the trial.** Grafana Cloud is only a *visualization* layer wired via standard OTLP; the feature is owned by this repo + our own datastore:

- **Portable by design.** Instrumentation, `ops.json`/`eval.json`, `rules.yaml`, `ask_load.js` all live in git → re-importable into any Grafana org (free tier, a new account, or a self-hosted Grafana) forever. The app degrades to **no-op** without an endpoint, so it never breaks.
- **Durable data is NOT in Grafana.** The long-term record is **`query_trace` in Postgres** (latency/cost/IDs, NFR16) + the committed `eval-results/*.json` / `comparison.*.json` artifacts. Grafana only *renders* recent metrics — losing it loses no history.
- **When the 14-day Pro trial ends**, the account drops to **Free Forever** (not deleted). You keep: unlimited dashboards, the Prometheus/Logs/Traces OTLP endpoints, and Performance Testing (k6). Re-import the two dashboards + the rules if a feature was trial-only; the OTLP env vars are unchanged.
- **Free-tier limits that matter here:** metrics retention ≈ **14 days** (why `eval.json` defaults to a 14-day window; the durable trend is Postgres + git), and a series-count cap we stay far under — our metrics are **low-cardinality** (labels: `operation`, `status`, `metric` only).
- **If you leave Grafana entirely:** swap `OTEL_EXPORTER_OTLP_ENDPOINT` to Azure Monitor / a self-hosted OTel Collector + Prometheus/Grafana. **No code change** (the `Metrics` port, ADR 0013).

## Notes
- **Data governance (NFR16):** metrics carry only counts/latency/cost + labels (operation, status, metric) — never query text or document content. Raw content stays out of Grafana entirely.
- **Prod (Azure):** point the same OTLP env at Azure Monitor's OTLP ingestion instead; the app code + dashboards are unchanged (only the endpoint differs).
- **[untested live]** here: rendered dashboards/alerts require a Grafana Cloud account; the artifacts + instrumentation are validated in CI (schema + FakeMetrics + k6 script).
