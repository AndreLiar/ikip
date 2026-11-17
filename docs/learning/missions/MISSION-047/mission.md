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

## Verdict
**Do not promote any knob on this evidence** — ADR 0032's bar (faithfulness ≥ baseline AND a
recall/correctness win) is not cleared. But the two knobs now have **different** standing:
- **`dedup` → reject** (real recall cost + worse answers; its premise, redundant chunks, barely
  exists in this gold).
- **`litm` → promising, unproven.** Recall-neutral by construction and faithfulness +0.050, but a
  single noisy run can't promote it. It is the **one knob worth a proper `--runs`-averaged re-test**
  before a promote/reject call. Stays opt-in until then.

This is the MISSION-044 result with a sharper edge: *context changes are a trade-off* — and the A/B
is what separated a knob that hurts (`dedup`) from one that might help (`litm`). The value delivered
is the **measurement + the reusable instrument**, not a new default; the opt-in + A/B-gated design is
vindicated — as defaults, dedup would have silently degraded quality.

## Honest limits
- **n=18, single Ragas run per arm** → the context metrics swing on an *identical* chunk set
  (proof above), so treat all deltas < ~0.05 as noise. Promoting `litm` needs `--runs`-averaged
  Ragas (ideally a larger n); the *rejections* (dedup, combined arm) are safe — they lost broadly.
- **litm's faithfulness win is single-run** and `answer_correctness`/`relevancy` were flat-to-down,
  so even the optimistic read is "maybe helps grounding, doesn't help correctness."
- **NTRS (EN) only**, k=5. A corpus with genuinely redundant/duplicated chunks (where `dedup` has
  real work) could differ — this gold had few near-duplicates, so dedup mostly just lost a chunk.
- The cross-encoder reranker (ADR 0032 §3) is **not** tested here — it's model-dependent and belongs
  behind the `Reranker` port, measured separately.

## Operational lesson (recorded)
Running the two Ragas arms **in parallel** tripped Azure **429 rate-limits** (`gpt-5.4-mini`,
francecentral — shared TPM, same class as MISSION-045/PR #102). The treatment arm crashed; re-running
the arms **serially** succeeded cleanly. **Serialize paid LLM-judged A/B arms** — they share one
quota; parallelism buys nothing but throttling.

## See also
Reproduce (**serial**, one arm at a time): `… eval ragas --gold eval-results/ab/ntrs_gold_v2.json
--tenant <ntrs> --k 5 [--ctx-litm] [--ctx-dedup] --out eval-results/ab/<arm>`. Results:
`eval-results/ab/{ctx_baseline,ctx_litm_only,ctx_dedup_litm}/ragas.json`. Strengthens
[ADR 0032](../../adr/0032-memory-and-context-engineering.md)'s opt-in + A/B-gated stance with
measured backing — and leaves `litm` flagged for a `--runs`-averaged re-test.
