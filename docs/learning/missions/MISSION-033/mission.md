# MISSION-033 — Fix the conflicting-sources defect via a gated prompt-config v2 (Epic 5)

**Mode:** Autonome (fix a defect the eval loop surfaced) + knowledge transfer.
**Objective:** stop the assistant from silently picking one value when two CURRENT sources conflict — it must abstain and name the conflict — and ship the fix through the Story 5.5 governance gate.
**Maps to:** Epic 5 follow-up (found by MISSION-032's custom-vs-Ragas comparison). Concept: [[rag-evaluation-metrics]].

## The defect (how the eval found it)
For *"max operating pressure of vessel V-3?"* two current sources say **8 bar** and **10 bar** (gold expects **abstain**). The system answered **"10 bar [E1]"**:
- `citation_grounding_coverage = 1.0` — the claim cites a real chunk, so the deterministic metric is blind to the conflict.
- Ragas `faithfulness = 0.0` — judged against the *whole* context (which also says 8 bar), the claim isn't entailed.
- `eval compare` flagged exactly this as the **1 divergent case**; `eval run` flagged the same case via `behavior_conformity = 0.875`. Two independent signals, one defect.

**Root cause:** grounding validation is **per-claim against its own cited evidence** — it never checks that two *current* sources contradict each other, so a cherry-picked value is "grounded".

## The fix — prompt config v2 (versioned + gated)
Rather than a code change, the fix is a new **versioned prompt config** (Story 5.5 machinery): `v2` adds one rule to `generate_system` —

> *If two or more CURRENT sources give different/contradictory answers, do NOT pick one: abstain and name the conflict. A superseded/older revision the evidence says is replaced is NOT a conflict — use the current one.*

Everything else (judge prompt, notice, model config) is identical to v1. Shipped through the gate:
`config activate v1` → `config promote --version v2 --eval eval-results` → gates **retrieval=ok, groundedness=ok, safety=ok** → **v2 active** (+ Langfuse sync). This is the full 5.5 loop exercised on a real finding: measure → version → gated promote → re-measure.

## Verification (live, real Azure judge)
- After v2, `conflicting-sources` **abstains** and `behavior_conformity = 1.0` (was 0.875); `outdated-manual` still **answers** "G-48 (current), G-30 superseded" — the superseded≠conflict distinction holds (no over-abstention); positive controls still answer.
- **Reliability (honest):** the chat model is a reasoning model at temperature 1 → **non-deterministic**. Measured abstention on the conflict case: **5–6 / 6 runs** abstain under v2 (vs **0/1** under v1). A strong, measurable mitigation — **not a hard guarantee**.
- Deterministic tests: v1 still == `BUILTIN_V1` (drift guard); active == v2 with conflict handling; graph/wiring/safety suites green.

## Follow-up — make it deterministic (noted)
A prompt hint depends on model obedience. The robust version is a **structural conflict guard**: have the grounding step judge each kept claim against the FULL current-source evidence set (not just its citation) and mark it `unsupported` when contradicted by another `is_current` source → the policy then abstains regardless of what `generate` produced. Uses the existing LLM-judge seam (ADR 0022) + the `is_current` metadata; scoped as a grounding enhancement (Epic 6 / provenance). Until then, v2 is a documented probabilistic mitigation that the eval gate will catch if it regresses.

## Before → after (live custom-vs-Ragas comparison)
| | answered cases | divergent | agreement |
|---|---|---|---|
| **v1 (before)** | 5 | 1 (`conflicting-sources`, faith 0.0) | 0.80 |
| **v2 (after)** | 4 (conflict now abstains) | **0** | **1.00** |

Artifacts: `evidence/comparison.live.json` (before) + `evidence/comparison.v2-after.json` (after). The defect is gone: the conflict case abstains, so it no longer appears as an answered, unfaithful claim.

## Deliverables
- `llm/prompt_config/v2.json` + `active.json` (active=v2); `tests/test_prompt_registry.py` (v1 drift guard + v2 active/conflict assertions).
- `docs/learning/concepts/rag-evaluation-metrics.md` (how to read the numbers).
- Artifacts `MISSION-029/evidence/comparison.{live,v2-after}.json` (before/after).

## Concepts
Driven by [[MISSION-032]] (the comparison that found it). Explained in [[rag-evaluation-metrics]]. Uses [[MISSION-028]] (versioned config + gated promotion).
