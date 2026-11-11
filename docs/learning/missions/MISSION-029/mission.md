# MISSION-029 — Gold datasets + Ragas eval & custom-vs-Ragas comparison (Epic 5, Stories 5.1 + 5.2)

**Mode:** Autonome (realises the ratified [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md)) + knowledge transfer.
**Objective:** representative gold datasets for key failure modes (5.1) and automated quality metrics from **both** the custom deterministic harness **and Ragas**, compared, so improvements are measured with trustworthy + standard metrics (5.2).
**Maps to:** Epic 5 / Stories 5.1, 5.2. Builds on the eval harness (3.6), prompt config (5.5), tracing (5.4).

## What was built
### Gold datasets (5.1)
- `tests/fixtures/gold/failure_modes.json` (version `failure-modes-v1`) — 8 cases covering the **seven required failure modes**: equipment_identifier (×2), outdated_manual, conflicting_sources, unanswerable, table, scanned_pdf, malicious_document. Each case: `category`, `question`, `relevant_chunk_ids` (evidence), `expected_behavior` (answered/abstained incl. abstention), optional `ground_truth` (Ragas reference). Versioned + reviewable (JSON, git).
- `GoldCase` gained optional `category` + `ground_truth` (backward compatible). The documented command runs against **any** dataset: `python -m ikip_common.eval run|ragas|compare --gold <file> ...`.

### Ragas behind a port (5.2)
- `eval/ragas_eval.py`: `RagasEvaluator` port + `RagasAdapter` (lazy `ragas` + Azure judge via langchain wrappers; `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`) + `FakeRagasEvaluator` (deterministic, CI). `ScorePublisher` port + `LangfuseScorePublisher` (pushes mean scores as Langfuse scores, AC3) + Null fallback. `ragas` dep group.
- Harness `CaseResult` now also carries `answer` + `contexts` so ONE harness run feeds both metric systems.

### Custom-vs-Ragas comparison (5.2 AC4)
- `eval/compare.py` (pure, no numpy): aligns custom **citation-grounding coverage** with Ragas **faithfulness** per case; reports **Pearson correlation**, **mean abs difference**, **agreement rate** (bucketed at a threshold), **divergent cases**, **cost**, and **run-to-run variance** (population variance of means across repeated Ragas runs), plus an honest **recommendation** on which set should gate releases.

### CLI + CI split (5.2 AC5)
- CLI: `eval ragas` (live Azure judge → `ragas.json` + Langfuse) and `eval compare --sample N --runs M` (both systems → `comparison.json`).
- **Deterministic metrics + the comparison math gate every push** (`test_ragas_eval.py` in `validate`). **Ragas (live, costly, non-deterministic) runs nightly/on-demand** — `.github/workflows/ragas-eval.yml` (cron + workflow_dispatch), guarded on Azure/DB secrets (no-op on forks, like db-tests).

## Acceptance
**5.1** 1 ✅ (7 modes) · 2 ✅ (question/evidence/behavior incl. abstention) · 3 ✅ (versioned JSON) · 4 ✅ (`eval run/ragas/compare --gold`).
**5.2** 1 ✅ (Recall@K deterministic, existing) · 2 ✅ (citation resolution deterministic, existing) · 3 ✅ (Ragas 4 metrics, Azure judge, Langfuse push — [untested live]) · 4 ✅ (comparison: agreement/divergence/cost/variance) · 5 ✅ (deterministic gate every push; Ragas sampled nightly/on-demand).

## Verification
- ruff + format ✓; `pytest apps packages services` → 218 passed / 43 skipped. Targeted embeddings suite (ragas fake, comparison, gold datasets, offline end-to-end comparison) → all pass.
- **Offline end-to-end** (`test_eval_compare_integration.py`): the real harness (FakeChatClient) → `EvalSample`s → `FakeRagasEvaluator` → comparison flags an injected faithfulness/coverage **divergence** — proving the full pipeline + the `CaseResult.answer/contexts` wiring without Azure.
- Live Azure-judged Ragas (`RagasAdapter`, CLI `ragas`/`compare`) is **[untested live]** — needs the `ragas` group + Azure creds + a seeded tenant (nightly workflow).

## Deliverables
- `tests/fixtures/gold/failure_modes.json`; `eval/ragas_eval.py`; `eval/compare.py`; harness `GoldCase`/`CaseResult` extensions; `eval/__init__.py` exports.
- CLI `ragas`/`compare` subcommands; `.github/workflows/ragas-eval.yml`; `pyproject.toml` `ragas` group.
- `tests/test_ragas_eval.py`, `tests/test_gold_datasets.py`, `tests/test_eval_compare_integration.py`; ADR 0016 implementation note.

## Follow-ups (noted)
- Live nightly run once the `ragas` group + Azure creds + a seeded eval tenant exist; publish `comparison.json` as the thesis artifact (which metric gates).
- Attach Ragas scores to the specific Langfuse trace (Story 5.4 `trace_id`) rather than standalone scores.
- Grow `failure_modes.json` with real ingested table/scanned-PDF/poisoned docs for a true live retrieval signal.

## Concepts
Realises [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md). Related: [[MISSION-027]] (safety gate), [[MISSION-028]] (config gates), [[MISSION-026]] (tracing/Langfuse).
