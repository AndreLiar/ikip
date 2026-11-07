# MISSION-017 — Execution log

Evidence labels: `[verified]` run with output · `[untested]`.

## Step 1 — evaluation_case model + migration — [verified]
`EvaluationCase` (tenant-scoped): `case_key`, `gold_set_version`, `question`, `expected_behavior`
(String, not DB enum), `relevant_chunk_ids` (JSONB), unique (tenant, gold_set_version, case_key).
Migration `5dc78f93f29b` hand-written; offline render verified both ways:
```
upgrade:   CREATE TABLE evaluation_case (... UNIQUE (tenant_id, gold_set_version, case_key)); + 3 indexes
downgrade: DROP INDEX ×3; DROP TABLE evaluation_case   (no enum type -> no trap)
```

## Step 2 — Deterministic metrics — [verified]
`eval/metrics.py` (pure, langchain-free → always CI): `recall_at_k` (configurable K; empty-relevant
vacuous), `citation_resolution`, `citation_grounding_coverage` (presence/resolution only),
`percentile` (p50/p95), `estimate_cost_usd` (char/4 + indicative gpt-5.4-mini rates).

## Step 3 — Harness — [verified]
`eval/harness.py`: `evaluate_dataset` runs each `GoldCase` through `grounded_answer`, capturing the
retrieval the graph used (`_CapturingRetrieve`, no double call), separating retrieval vs answer
metrics, aggregating (recall@k, citation res, grounding coverage, behavior conformity, abstention
rate, latency p50/p95, est cost). `compare_to_baseline` flags higher-is-better drops > tolerance.

## Step 4 — Reports (3 artifacts) + CLI — [verified]
`eval/report.py`: `write_run` → runs/<ts>.json + latest.json (never baseline); `promote` → baseline.json;
run metadata = created_at + commit SHA + gold_set_version + config. `eval/__main__.py`: `run` (live,
Azure+DB), `check` (exit 1 on regression), `promote`. CLI `--help` verified.

## Step 5 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_eval_metrics.py test_eval_harness.py -q   # 13 passed
uv run pytest packages/common/tests -q                     # 65 passed, 30 skipped (DB/live gated)
SSL_CERT_FILE=$(certifi) uv run pytest .../test_answer_live.py .../test_embeddings_azure_live.py -q  # 4 passed (no regression)
uv run ruff check / format --check packages/common         # OK
uv run python -c "from ikip_common.eval import recall_at_k"  # metrics import w/o langchain (CI-safe)
```
- Pure (CI): metric edge cases (recall K-cutoff / empty-relevant / invalid K; resolution; coverage flags; percentile; cost scaling).
- Harness (fakes, no network): fixture run deterministic (quality metrics identical across runs; latency excluded); 3-artifact writer + baseline-not-auto-set; regression flagged within/over tolerance.
- DB-gated: evaluation_case persist, unique case_key, tenant isolation (NFR10).

**Pitfalls:**
- Asserting the *whole* aggregate equal across runs failed on wall-clock latency → compare quality metrics only (latency excluded from reproducibility contract).
- `eval.metrics` kept langchain-free so the fast CI gate imports it; `eval.harness` (needs langgraph) is `importorskip`-ed in tests and the CLI lazy-imports.

**Local DB caveat:** DB test runs in CI (ephemeral Neon branch); migration verified offline locally.
