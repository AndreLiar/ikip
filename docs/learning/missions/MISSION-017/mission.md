# MISSION-017 — Retrieval & answer quality baseline (Epic 3, Story 3.6)

**Mode:** Guidé (eval-scope decision) → Autonome (impl) + knowledge transfer.
**Objective:** make RAG quality a *number* before the UI — a deterministic (LLM-free) evaluation baseline with a gold set, reproducible reports and regression comparison.
**Maps to:** Epic 3 / Story 3.6. Applies [ADR 0016](../../../adr/0016-rag-evaluation-custom-plus-ragas.md); consumes Stories 3.3–3.5.

## Decision (ratified, option 1)
**Deterministic baseline now; Ragas (LLM-judged faithfulness) + custom-vs-Ragas comparison in Epic 5** (per ADR 0016). Mandatory distinction: `citation_grounding_coverage` checks evidence **presence/resolution**, NOT semantic entailment. Don't re-implement the Story 3.5 grounding judge in the harness. See [decisions.md](./decisions.md).

## Acceptance criteria
1. `evaluation_case` records (question, relevant evidence, expected behavior). — **[verified]** (model + migration + DB test; stable `case_key` + `gold_set_version`)
2. Recall@K + citation-resolution over the gold set. — **[verified]** (`recall_at_k`, `citation_resolution`; configurable K; unit + harness tests)
3. A groundedness check flags unsupported claims. — **[verified]** (`citation_grounding_coverage` flags claims without resolvable citation — presence/resolution, not entailment)
4. Reproducible via a documented command + stored for regression comparison. — **[verified]** (harness + `FakeChatClient` + versioned fixture, no network; CLI `run/check/promote`; 3 artifacts runs/latest/baseline; `compare_to_baseline` with tolerance)

## Exit criteria (user)
1. Migration + tenant isolation tested — **[verified]** (`test_eval_case_model.py`, DB-gated).
2. Metrics unit-tested on edge cases — **[verified]** (`test_eval_metrics.py`).
3. Harness reproducible without network — **[verified]** (`test_eval_harness.py`, fakes).
4. Reports usable for regressions — **[verified]** (3 artifacts + `compare_to_baseline`; baseline promoted manually).
5. Command + metric limitations documented — **[verified]** (tutorial + concept; resolution ≠ entailment stated).

## Deliverables
- `db/models.py` `EvaluationCase` + `ExpectedBehavior` (String, no enum trap) + migration `5dc78f93f29b`.
- `eval/metrics.py` (pure): `recall_at_k`, `citation_resolution`, `citation_grounding_coverage`, `percentile`, `estimate_cost_usd`.
- `eval/harness.py`: `GoldCase`, `CaseResult`, `EvalReport`, `evaluate_dataset` (captures retrieval; separates retrieval/answer), `compare_to_baseline`.
- `eval/report.py`: 3-artifact writer (`write_run`, `promote`, `load_json`) + run metadata (commit SHA, dataset version).
- `eval/__main__.py`: CLI `run` (live) / `check` / `promote`.
- Fixture `tests/fixtures/gold/v1.json`.
- Tests: `test_eval_metrics.py` (10), `test_eval_harness.py` (3), `test_eval_case_model.py` (3 DB-gated).

## Concepts
Introduces [rag-evaluation](../../concepts/rag-evaluation.md). Reuses [grounded-answers](../../concepts/grounded-answers.md), [hybrid-retrieval](../../concepts/hybrid-retrieval.md), [multi-tenancy](../../concepts/multi-tenancy.md).
