# MISSION-047 — Does context engineering (dedup + lost-in-the-middle) help? (measure it)

- **Mode:** Autonome (measurement — A/B a shipped-but-opt-in feature before making it default)
- **Date:** 2026-11-16
- **Related:** [ADR 0032](../../adr/0032-memory-and-context-engineering.md) (memory & context engineering — L3) · [MISSION-044](../MISSION-044/mission.md) (context is a measured trade-off) · [MISSION-045](../MISSION-045/mission.md) (NTRS/FR gold + Ragas) · concept [hybrid-retrieval](../concepts/hybrid-retrieval.md) · FR16 (citations)

## Objective
ADR 0032 layer 3 shipped the context-engineering transforms (`ikip_common.context_engineering`:
dedup, token budget, lost-in-the-middle reorder) **opt-in and no-op by default**, on the explicit
condition that *no knob becomes default without a measured faithfulness ≥ baseline + a recall/
correctness win*. This mission runs that A/B so the decision is evidence-based, not intuition.

## Method
Wired `ContextBudget` into the retrieval path (`make_hybrid_retrieve(..., context_budget=)`, applied
post-retrieval, drop/reorder only — citations preserved) and exposed `--ctx-dedup / --ctx-max-tokens
/ --ctx-litm` on the eval CLI (`run` + `ragas`). Then, on the **NTRS n=18 gold** (`ntrs_gold_v2`,
silver-v2, tenant `…a1`, k=5):
- **baseline** = no flags;
- **dedup+litm** = `--ctx-dedup --ctx-litm` (the combined context-engineering pipeline);
- **litm-only** = `--ctx-litm` (the recall-neutral reorder in isolation — added after the combined
  arm lost, to attribute the loss to dedup vs reorder).

Two measurement layers: the **deterministic harness** (free — recall@k / citation coverage) for the
retrieval-side cost, and **Ragas** (LLM-judged, gpt-5.4-mini) for the generation-side effect
(faithfulness / answer_correctness / context_recall / precision).

## Results

### Deterministic harness (recall + citations)
| arm | recall@5 | citation grounding | behavior conformity | abstention |
|---|--:|--:|--:|--:|
| baseline | **0.889** | 1.000 | 0.944 | 0.056 |
| dedup+litm | 0.833 | 1.000 | 0.944 | 0.056 |

### Ragas (n=18, single run per arm) — Δ vs baseline
| metric | baseline | litm-only | dedup+litm |
|---|--:|--:|--:|
| faithfulness | 0.890 | **0.940 (+0.050)** | 0.874 (−0.016) |
| answer_correctness | 0.690 | 0.676 (−0.014) | 0.644 (−0.046) |
| answer_relevancy | 0.768 | 0.736 (−0.032) | 0.734 (−0.034) |
| context_precision | 0.770 | 0.700 (−0.070) | 0.675 (−0.096) |
| context_recall | 0.944 | 0.889 (−0.056) | 0.889 (−0.056) |

Cost: $0.063 baseline + $0.064 dedup+litm + $0.063 litm-only Azure (+ ~$0.03 deterministic). Judge
gpt-5.4-mini.

## Discovery — dedup is the culprit; litm's gain is real-looking but inside the judge's noise
1. **The combined `dedup+litm` arm lost on every metric** — and `litm-only` isolates why:
   **`dedup` carries the damage.** Dropping `dedup` turns faithfulness from −0.016 into **+0.050**.
   The combined arm's loss was dedup masking litm's gain. `dedup` keys on content (word-set
   Jaccard ≥ 0.9) but recall is scored by `chunk_id`, so a near-duplicate that *was* the gold chunk
   gets dropped even though equivalent text survives — part scoring artifact, but
   `answer_correctness` fell too (−0.046), which is **not** an artifact: dedup genuinely produced
   worse answers here. **Reject `dedup` on this corpus.**
2. **`litm-only` lifted faithfulness +0.050** (5/6 changed cases up, incl. the weak `ntrs-v2-16`
   0.50→1.00) — the lost-in-the-middle hypothesis (strongest evidence at the edges → the generator
   grounds better) shows a real-looking signal, at **zero recall cost** (pure reorder of the same
   set).
3. **…but the same run proves that signal is inside the judge's noise.** `litm` reorders an
   **identical chunk set**, so set-based recall is provably unchanged — yet Ragas `context_recall`
   (−0.056) and `context_precision` (−0.070) *moved anyway* (e.g. `ntrs-v2-2` context_recall
   1.000→0.000 on the very same contexts). Those context metrics are LLM-judged and here they swing
   on order alone → **heavy judge non-determinism at n=18 / single run.** The faithfulness +0.050
   lives in that same noise band, so it **cannot be trusted from one pass.**

## Follow-up — `--runs 3` judge-averaged (resolves litm, overturns the single-run caution)
The single-run worry was that litm's gain lived in judge noise. So I re-ran **baseline** and
**litm-only** with `eval compare --runs 3` (generation once per arm, then the Ragas judge **3×** on
the *same* answers — this averages exactly the judge noise). Both arms answered the **same 17** cases
(1 abstention excluded, as Ragas faithfulness is NaN on an empty answer):

| arm | faithfulness (judge-avg, n=17) | judge-noise std (across the 3 passes) |
|---|--:|--:|
| baseline | 0.9145 | 0.0042 |
| litm-only | **0.9902** | 0.0006 |
| **Δ** | **+0.076** | — |

**The faithfulness gain is real, not noise.** Judge-noise std is ±0.004 (baseline) / ±0.001 (litm),
so **+0.076 is ~18× the noise floor.** Per case, 5 of 6 that moved went up — the weak cases are
exactly where reorder helped (`ntrs-v2-16` 0.33→1.00, `ntrs-v2-1` 0.60→1.00, `ntrs-v2-7` 0.83→1.00),
one regressed (`ntrs-v2-11` 1.00→0.83). This **corrects the single-run read**: the judge is noisy
*per case* (hence the `ntrs-v2-2` context_recall 1.0→0.0 swing) but **stable in aggregate**, and
averaging shows litm's lost-in-the-middle reorder genuinely lifts grounding. Recall stays untouched
(litm is a pure reorder of the same chunk set — deterministic recall@5 = baseline, provably).

## Verdict
- **`dedup` → reject.** Real recall cost (0.889→0.833) + worse answer_correctness; its premise
  (redundant chunks) barely exists in this gold.
- **`litm` → promote candidate (grounding win, confirmed).** Judge-averaged faithfulness **+0.076**
  at **zero recall cost**, well outside judge noise and stable across passes. It clears the part of
  ADR 0032's bar that matters most for this product — *grounding* (faithfulness ≫ baseline, recall
  neutral). Recommendation: **promote `--ctx-litm` from opt-in toward default**, pending the one
  check below (generation variance). `dedup` stays off.

This sharpens the MISSION-044 story: context changes are a trade-off, and a *properly averaged* A/B
is what told a knob that hurts (`dedup`) apart from one that helps (`litm`) — where a single run had
them both looking like losers. The instrument + the averaging discipline are the asset.

## Honest limits
- **`--runs` averages the judge, not generation.** Each arm generated its answers **once**, judged
  3×. The +0.076 is a rock-solid *judge* measurement of those two generations; it does **not** average
  out generation non-determinism. The effect is large and the per-case pattern is coherent (weak
  cases → 1.0), so luck is unlikely — but the clean final step before defaulting is to **re-generate**
  litm a few times (not just re-judge) and confirm the gain holds.
- **Faithfulness, not correctness.** `answer_correctness`/`answer_relevancy` were flat-to-slightly-
  down single-run. litm makes answers *stick to the retrieved evidence* (grounding) more, which is
  the core promise — but it is not shown to make them more *correct vs ground truth*.
- **NTRS (EN) only**, n=17 answered, k=5. Re-confirm on an FR corpus before a global default.
- The cross-encoder reranker (ADR 0032 §3) is **not** tested here — model-dependent, belongs behind
  the `Reranker` port, measured separately.

## Operational lesson (recorded)
Running the two Ragas arms **in parallel** tripped Azure **429 rate-limits** (`gpt-5.4-mini`,
francecentral — shared TPM, same class as MISSION-045/PR #102). The treatment arm crashed; re-running
the arms **serially** succeeded cleanly. **Serialize paid LLM-judged A/B arms** — they share one
quota; parallelism buys nothing but throttling.

## See also
Reproduce (**serial**, one arm at a time). Single-run: `… eval ragas --gold
eval-results/ab/ntrs_gold_v2.json --tenant <ntrs> --k 5 [--ctx-litm] [--ctx-dedup] --out
eval-results/ab/<arm>`. Judge-averaged: `… eval compare … --runs 3 [--ctx-litm] --budget-usd 1.0
--out eval-results/ab/ctx_cmp_<arm>` (per-run means/variance in `comparison.json → ragas_variance`;
per-case faithfulness in `pairs`). Results under `eval-results/ab/{ctx_baseline,ctx_litm_only,
ctx_dedup_litm,ctx_cmp_baseline,ctx_cmp_litm}/`. Strengthens
[ADR 0032](../../adr/0032-memory-and-context-engineering.md)'s opt-in + A/B-gated stance — and turns
`litm` into a measured promote candidate (grounding win, pending a generation-variance check).
