# MISSION-053 — litm generation-variance re-test: the +0.076 was a generation artifact → REJECT

- **Mode:** Autonome (measurement — close the last context-engineering promote-candidate)
- **Date:** 2026-11-18
- **Related:** [MISSION-047](../MISSION-047/mission.md) (the +0.076 judge-averaged promote-candidate) · [ADR 0032 §3](../../adr/0032-context-engineering-ab.md) (context engineering) · issue #138
- **Decides:** `ContextBudget(lost_in_the_middle=...)` default — stays **False**.

## Objective
MISSION-047 measured the lost-in-the-middle (litm) reorder as a promote-candidate: judge-averaged
faithfulness **+0.076** (~18× the judge-noise floor), recall-neutral by construction. But
`compare --runs` averaged the **judge**, not the **generation** — each arm generated its answers
**once**. So the gain was a rock-solid *judge* measurement of two specific generations; it did not
rule out generation non-determinism. Re-test with fresh **re-generation** (not just re-judging).

## Method
Ran the `ragas` subcommand **6×** (not `compare --runs`, which re-judges one generation): baseline
**3×** and `--ctx-litm` **3×** on `ntrs_gold_v2` (n=18, version `ntrs-silver-v2`, tenant
`c0f90000-…-a1`), k=5, **serial** (Azure 429 lesson, MISSION-047). Each `ragas` invocation calls
`_live_report` → retrieval **and** generation run fresh, so the three runs per arm are three
independent generations. Averaged each metric across the 3 generations per arm; report mean ± sd.

## Result — NTRS n=18, 3 fresh generations per arm
| metric | base mean ± sd | litm mean ± sd | Δ (litm − base) |
|---|--:|--:|--:|
| **faithfulness** | **0.963 ± 0.037** | **0.907 ± 0.017** | **−0.056** |
| answer_correctness | 0.685 ± 0.038 | 0.684 ± 0.006 | −0.001 |
| answer_relevancy | 0.751 ± 0.008 | 0.776 ± 0.008 | +0.024 |
| **context_precision** | 0.754 ± 0.013 | 0.644 ± 0.002 | **−0.110** |
| context_recall | 0.889 ± 0.000 | 0.889 ± 0.000 | 0.000 |

Raw faithfulness — **base:** [0.913, 0.977, 1.000] · **litm:** [0.900, 0.930, 0.892].
Cost: **$0.38** judge (6 × ~$0.063) + the shared deterministic generation side.

## Discovery
1. **The +0.076 does NOT survive generation variance — it reverses.** Generation-averaged,
   litm faithfulness is **−0.056** vs baseline (point estimate *negative*). MISSION-047's gain was
   the artifact of comparing two **specific** generations, not the effect of the reorder.
2. **Why the earlier measurement was fooled.** The baseline's own faithfulness swings
   **0.913 → 1.000** across fresh generations (sd 0.037) — a spread **larger** than the +0.076
   "gain." A single-generation A/B sits *inside* that noise; the judge was precise about the wrong
   thing (two frozen answers), not about the intervention.
3. **litm still carries its context_precision cost (−0.110, sd 0.002 — tight and real).** Reordering
   strongest evidence to the edges does not change *which* chunks are retrieved (recall flat 0.889)
   but the precision metric penalises the reordered block consistently. answer_relevancy nudges up
   (+0.024) but answer_correctness is flat — no downstream answer-quality win to offset the cost.

## Verdict
**REJECT litm** (like `dedup`, MISSION-047). The faithfulness gain was a generation artifact; across
fresh generations there is no faithfulness or correctness benefit and a consistent precision cost.
`ContextBudget(lost_in_the_middle=False)` **stays the default** — no code change, the knob remains an
opt-in A/B lever. The context-engineering thread (ADR 0032 L3) is now closed: **dedup rejected
(hurts recall), litm rejected (generation artifact)** — neither earns a default.

## The transferable lesson
**Average the generation, not just the judge, before promoting an LLM-pipeline intervention.**
`--runs` on the judge measures judge stability; it says nothing about generation non-determinism.
When the baseline's run-to-run spread (sd 0.037) is comparable to or larger than the measured effect
(+0.076 → but against one generation), a single-generation A/B cannot distinguish signal from the
generation lottery. The cheap guard is N fresh generations per arm — here N=3 was enough to flip the
sign of the conclusion. This retro-justifies the discipline the decomposition gate already used
(MISSION-051/052) and is the measure-first counterpart to a false-positive in classic A/B testing.

## Honest limits
- **n=18, 3 generations per arm, single corpus (NTRS).** The *direction* is safe — litm shows no
  benefit on three independent generations and a tight precision cost — but a very small true effect
  (|Δ| < 0.02) is not distinguishable from noise at this N. That is precisely the "not worth a
  default" regime, which is the decision here.
- **Ragas judge is itself one judge pass per generation** (not `--runs`-averaged on top). The
  generation spread dominates at this N, so adding judge-averaging would tighten the bands but not
  move the −0.056 / −0.110 point estimates across zero.
- Scope is the **litm reorder only**; the other ADR 0032 L3 knobs (token budget) were not re-touched.

## See also
Runs: `eval-results/ab/litm_regen/{base_1,base_2,base_3,litm_1,litm_2,litm_3}/ragas.json`.
Closes issue #138. Default lives in `packages/common/src/ikip_common/context_engineering.py`
(`ContextBudget.lost_in_the_middle=False`). Supersedes the MISSION-047 promote-candidate note.
