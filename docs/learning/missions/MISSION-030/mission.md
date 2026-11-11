# MISSION-030 — Eval loop closure: trace↔score↔config, model-config wiring, cost, hardening

**Mode:** Autonome (improvements the user approved from the Epic-5 review) + knowledge transfer.
**Objective:** close the observability/governance loop around the eval stack and harden it — so a quality shift is traceable to the exact prompt/model that caused it, config rollback actually changes generation, Ragas reports a real cost, and the safety gate can't be bypassed.
**Maps to:** Epic 5 follow-ups on Stories 5.2/5.4/5.5/5.3.

## What was built
1. **ModelConfig → `build_chat_client` (5.5 follow-up).** The active prompt config's `ModelConfig` now supplies the *behavior* knobs (`reasoning_effort`, `temperature`) via `settings.model_copy(update=…)`, so promote/rollback actually changes generation. The deployment **name** stays env-owned (infra, not a versioned knob). v1 == current defaults → zero behavior change. Test: config overrides env for the knobs, not the deployment.
2. **Prompt config version → `query_trace.model_version` (5.5 ↔ 5.4).** `/ask` stamps the trace with `"{deployment}+prompt:{version}"` from `active_prompt_config()`, so a metric regression is attributable to the exact prompt/model. Endpoint test asserts the stamp.
3. **Ragas scores → `trace_id` (5.2 ↔ 5.4).** The harness traces each case behind the `Telemetry` port (default `NullTelemetry` in deterministic CI) and records `CaseResult.trace_id`; the `ScorePublisher` attaches per-case Ragas scores to that Langfuse trace (plus run-level means) — navigate trace→score→prompt. Tests: publisher attaches per-case + means.
4. **Real-ish Ragas cost + `answer_correctness` (5.2 AC4).** `RagasScores.cost_usd` is now a coarse judge-cost estimate (`estimate_ragas_cost_usd`) instead of a `0.0` placeholder (real usage counters = follow-up). `answer_correctness` added (uses the gold `ground_truth`).
5. **Hardening.** `enforce_admins=true` on `main` — the required `validate` + `safety-gate` checks can no longer be admin-bypassed (closes the 5.3 "100% blocking" gap). Added a **contract test** for `RagasAdapter` (fake `ragas`/`datasets` modules) that asserts the result-DataFrame→per-case mapping + cost, catching Ragas API drift before the nightly live run.

## Verification
- ruff + format ✓; `pytest apps packages services` → 221 passed / 43 skipped. OpenAPI unchanged.
- New deterministic tests: chat-config wiring (config wins over env), `/ask` model_version stamp, Ragas adapter contract (mapping + cost), score publisher trace attachment.
- Live Azure-judged path still `[untested live]` (nightly `ragas-eval.yml`).

## Deliverables
- `llm/__init__.py` (`build_chat_client` applies active ModelConfig); `apps/api/retrieval.py` (`model_version` stamp).
- `eval/harness.py` (per-case telemetry span + `CaseResult.trace_id`); `eval/ragas_eval.py` (`answer_correctness`, `estimate_ragas_cost_usd`, `ScorePublisher.trace_ids`); `eval/__main__.py` (threads telemetry + trace_ids).
- Tests: `test_chat_config_wiring.py`, `test_ragas_eval.py` (contract + publisher), endpoint assertion.
- Branch protection `enforce_admins=true`.

## Follow-ups (noted)
- Real usage-based Ragas cost (judge token counters) instead of the estimate.
- The 🔴 item — a **seed_eval_corpus** script + one real live run producing `comparison.json` + Langfuse screenshots — is the next mission.

## Concepts
Ties [[MISSION-026]] (tracing), [[MISSION-028]] (config), [[MISSION-029]] (Ragas) together. Realises ADRs 0013/0016.
