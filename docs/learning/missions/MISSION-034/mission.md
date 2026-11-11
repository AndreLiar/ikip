# MISSION-034 — Covering Ragas' known limitations (Epic 5, Story 5.2 hardening)

**Mode:** Autonome (close the 5 limitations the user raised) + knowledge transfer.
**Objective:** turn the acknowledged Ragas limitations from "documented gaps" into "handled, measured" — language bias, cost, judge quality, reference provenance, multi-turn.
**Maps to:** Epic 5 / Story 5.2. Concept: [[rag-evaluation-metrics]]. Shipped as PRs #51–#54.

## Limitation → how it's handled now

### 1. Dependent on LLM-judge quality → **calibration vs humans** (PR #53)
`fixtures/eval/judge_calibration.json` = 6 human-labeled (claim, evidence) grounding judgments. `eval/calibration.py` runs our REAL `LLMGroundingValidator` (Azure judge) over them → **accuracy, binary (supported vs not), Cohen's kappa, 3-class confusion**. CLI `eval calibrate [--min-accuracy]`. **Live: accuracy = 1.00, kappa = 1.00 (n=6)** — the judge agreed with every human label, incl. the `partial` and contradiction cases (`evidence/judge-calibration.live.json`). We now have a ground truth on the judge itself.

### 2. High cost & latency → **real token counting + hard budget cap** (PR #52)
`RagasAdapter` wraps the judge in langchain `get_openai_callback` → **measured** prompt/completion tokens → real `cost_usd` (`cost_source="measured"`), falling back to the estimate only when unavailable. `eval ragas/compare --budget-usd <cap>` estimates cost (× runs) and **refuses (exit 2) before spending** if over cap. **Live: `--budget-usd 0.0000001` → "estimated $0.0018 exceeds cap — refused"** (no spend). Ragas already runs bounded-sample / nightly, never per-push.

### 3. English bias → **FR gold + language tag + per-language reporting** (PR #51)
`GoldCase.language` + `CaseResult.language` + aggregate **`by_language`** behaviour conformity. `failure_modes_fr.json` (FR mirror) + FR seed docs (`c-*-fr`). **Key framing:** our *gating* deterministic metrics (recall@k, citation resolution) are **language-agnostic** (they compare IDs) — only the advisory Ragas layer is English-biased, and the judge is swappable behind the port.

### 4. Requires quality references → **SME-review provenance** (PR #51)
`GoldCase.reviewed`/`reviewer` per case + CLI `eval gold-status [--require-reviewed]` (exits 1 on unreviewed when required). Every current case is honestly `reviewed:false` (hand-written, not SME-validated). Also: our headline comparison uses **`faithfulness`**, which **needs no reference** — so reference quality doesn't gate the main result.

### 5. Single-turn only → **multi-turn eval** (PR #54)
`eval/multiturn.py`: runs short conversations sequentially, folding prior (Q,A) into each turn's query (`contextualize`), scoring the FINAL turn. `multi_turn.json` (en+fr). CLI `eval multiturn`. **Live: 3 cases** — FR follow-up **answered** ✅, out-of-evidence follow-up **abstained** ✅, and one EN case hit **Azure's jailbreak content filter** (the retrieval surfaced the poisoned seed doc; the filter blocked it) → recorded as **`error`**, never a silent answer. Robust per-case error handling means one filtered turn doesn't crash the run. `evidence/multiturn.live.json`.

## New CLI surface
`python -m ikip_common.eval` now has: run · check · promote · safety · config · seed · ragas · compare · **gold-status** · **calibrate** · **multiturn**.

## Verification
- ruff + format ✓; `pytest apps packages services` → **237 passed / 44 skipped**.
- Deterministic tests added: calibration math (kappa/confusion), within_budget + measured-cost callback, FR gold/by_language, contextualize + multi-turn fakes run.
- Live (real Azure): calibration 1.00/1.00; budget refusal; multi-turn 2/3 + 1 content-filtered.

## Honest residuals (follow-ups)
- Calibration set is tiny (n=6) + `reviewed:false` — grow it + get SME sign-off before it gates.
- Token-measured cost uses indicative Azure rates (not a billing export).
- Multi-turn is **query-contextualized**, not a native conversational retriever (prior answers aren't re-retrieved) — a larger feature.
- The poisoned seed doc trips the content filter in multi-turn retrieval — a signal for Epic-6 document provenance (don't retrieve untrusted content into the judge/model).

## Concepts
Extends [[rag-evaluation-metrics]]; builds on [[MISSION-029]]/[[MISSION-032]] (Ragas) + [[MISSION-031]] (seed corpus).
