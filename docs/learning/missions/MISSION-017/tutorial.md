# MISSION-017 — Reproduction tutorial

Run the deterministic RAG evaluation baseline. Concept: [rag-evaluation](../../concepts/rag-evaluation.md);
decision [ADR 0016](../../../adr/0016-rag-evaluation-custom-plus-ragas.md).

## Prerequisites
- Stories 3.2–3.5 done. `uv sync --group embeddings` (harness needs langgraph).
- Migrate the gold table: `cd packages/common && uv run alembic upgrade head`.

## Per-push gate (no network — the reproducible command)
```bash
uv run pytest packages/common/tests/test_eval_metrics.py \
              packages/common/tests/test_eval_harness.py -q
```
This runs the harness over the versioned fixture `tests/fixtures/gold/v1.json` with a
`FakeChatClient` — deterministic, offline. The metric unit tests cover edge cases.

## Live run against a gold set (real Azure + DB)
```bash
# gold cases live in evaluation_case (tenant-scoped) or a JSON file like the fixture
SSL_CERT_FILE=$(uv run python -c "import certifi;print(certifi.where())") \
uv run --group embeddings python -m ikip_common.eval run \
    --gold packages/common/tests/fixtures/gold/v1.json \
    --tenant <tenant-uuid> --k 5 --out eval-results
# -> eval-results/runs/<timestamp>.json + eval-results/latest.json
```

## Regression check + baseline promotion (the 3 artifacts)
```bash
# compare the latest run to the APPROVED baseline (exit 1 if a metric regressed > tolerance)
uv run python -m ikip_common.eval check --out eval-results --tolerance 0.02

# approve the current latest as the new reference (manual — never automatic)
uv run python -m ikip_common.eval promote --out eval-results   # latest.json -> baseline.json
```
- `runs/<ts>.json` = history · `latest.json` = last run · `baseline.json` = approved reference.
- A degraded run updates `latest`, never `baseline` — so it can't silently become the bar.

## Metrics + their limits (read before trusting a number)
- **Recall@K** — relevant gold chunks found in top-K (configurable K).
- **citation_resolution** — cited chunks resolve to retrieved ones (provenance).
- **citation_grounding_coverage** — claims with ≥1 resolvable citation. **Presence/resolution only — NOT semantic entailment.** A citation can resolve yet not support the claim; faithfulness (LLM-judged) is Epic 5.
- **behavior_conformity / abstention_rate** — answered-vs-abstained correctness.
- **latency p50/p95**, **estimated_cost_usd** — operational; cost is a char/4 estimate, real FinOps in Epic 5.

## Common mistakes
- **Comparing the whole aggregate for determinism** → latency is wall-clock; exclude `latency_*`.
- **Calling `citation_grounding_coverage` faithfulness** → it isn't; it ignores entailment.
- **Letting CI write baseline.json** → never; promote is manual/approved.
- **Running `check` with no baseline** → it's a no-op until you `promote` once.
