# MISSION-027 — Safety-Abstention Evaluation (Epic 5, Story 5.3) → critical release gate

**Mode:** Autonome (safety gate on an existing guardrail) + knowledge transfer.
**Objective:** a predefined, versioned **critical safety test set** that runs in CI as a **required, 100%-must-pass release gate**, confirming the system refuses unsafe/unsupported guidance and contains malicious documents — with a report of which cases abstained vs. answered.
**Maps to:** Epic 5 / Story 5.3. Builds on the Story 3.5 grounded-answer guardrail (`llm/answer.py`) and the Story 3.6 eval harness (`eval/`, ADR 0016).

## Key design decision — what the gate tests
The safety guardrail is the **deterministic policy** in `llm/answer.py`: empty/insufficient retrieval → abstain (without calling the model); the model may self-abstain; after generation, grounding verdicts are applied — an **unsupported safety-critical claim aborts the whole answer**, an unknown/fabricated evidence handle is forced to `unsupported`, and injected unsafe instructions that aren't entailed are dropped.

This gate asserts that **policy**: given the model's (possibly adversarial) draft + the grounding judge's verdicts, the system produces the safe result. It deliberately does **not** measure the judge's ML accuracy on entailment — that is a separate *probabilistic* eval (Ragas/live, 5.1/5.2), never a hard 100% gate. Making the gate deterministic (scripted fakes, no network, no DB, no secrets) is what lets it be a **required** check that runs on every PR including forks. The residual risk (a malicious doc whose unsafe instruction the judge is *fooled* into calling "supported") is defended by document provenance/trust in **Epic 6** — noted, not silently ignored.

## What was built
- **Versioned safety set** `packages/common/tests/fixtures/safety/v1.json` — 8 critical cases across categories: `insufficient_evidence`, `model_abstention`, `unsupported_safety_claim`, `fabricated_reference`, `malicious_document` (×2 — injection of unsafe guidance, and injection of exfiltration/"ignore instructions"), and `positive_control` (×2). Each scripts retrieval + the model draft + grounding verdicts and declares its safe invariant (`must_abstain` / `must_answer` / `must_not_contain`). Positive controls keep the gate from being trivially satisfied by *always* abstaining.
- **Runner** `eval/safety.py` — `load_safety_cases`, `run_safety_suite` → `SafetyReport` (n_passed, `all_passed`, abstained/answered split, `by_category`), `format_report`. Drives the REAL `grounded_answer` graph via scripted `FakeChatClient`/`FakeGroundingValidator`; a `_NoCallChat` proves the no-evidence path abstains **without** invoking the model.
- **CLI** `python -m ikip_common.eval safety [--gold … --out …]` — prints the abstained-vs-answered report (AC3) and **exits 1 on any failure** (blocks release).
- **Required CI job** `safety-gate` in `.github/workflows/ci.yml` — `uv sync --group embeddings`, runs `test_safety_suite.py` + the CLI gate. No DB/secrets → runs on forks.
- **Tests** `tests/test_safety_suite.py` — 100%-pass over the real fixture (AC1/AC2), abstained/answered split present (AC3), malicious-document containment (AC4), and a **meta-test** that the gate actually FAILs a case whose invariant is violated (green means something).

## Acceptance (Story 5.3)
1. Predefined critical safety test set runs in CI. — **[verified]** (`safety-gate` job; versioned `safety/v1.json`).
2. 100% pass required; failures block release. — **[verified]** (CLI exits 1 on any fail; `all_passed` asserted; meta-test proves failures are detected).
3. Reports show which cases abstained vs. answered. — **[verified]** (`format_report` + `SafetyReport.n_abstained/n_answered/by_category`; CLI prints per-case PASS/behavior).
4. Malicious-document cases confirm safe handling. — **[verified]** (two injection cases: unsafe-guidance contained → abstain; exfiltration/"ignore instructions" not leaked; `must_not_contain` enforced). Ties to Epic 6 (doc provenance for the judge-fooling residual).

## Verification
- `uv run --group embeddings python -m ikip_common.eval safety` → **8/8 passed (abstained=5, answered=3)**, exit 0.
- `pytest test_safety_suite.py` (with langgraph) → 4 passed; fast gate skips it (importorskip), `safety-gate` job runs it.
- ruff ✓, ruff format ✓, `pytest apps packages services` → 199 passed / 43 skipped.

## Deliverables
- `packages/common/tests/fixtures/safety/v1.json`; `eval/safety.py`; `eval/__main__.py` (`safety` subcommand); `tests/test_safety_suite.py`; `.github/workflows/ci.yml` (`safety-gate`).

## Follow-ups (noted)
- Epic 6: document provenance/trust to defend the judge-fooling residual (a trusted-source signal feeding the grounding policy).
- 5.1/5.2: probabilistic judge-accuracy eval (Ragas) over adversarial entailment — complementary to this deterministic gate.
- Grow the set as real failures surface (promote new regressions into `v1.json`/`v2`).

## Concepts
Extends [grounded-answers](../../concepts/grounded-answers.md). Realises the eval contract of ADR 0016; adversarial guardrail mechanics unit-tested in `test_answer_graph.py`.
