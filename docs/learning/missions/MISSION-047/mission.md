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
- **treatment** = `--ctx-dedup --ctx-litm` (the combined context-engineering pipeline).

Two measurement layers: the **deterministic harness** (free — recall@k / citation coverage) for the
retrieval-side cost, and **Ragas** (LLM-judged, gpt-5.4-mini) for the generation-side effect
(faithfulness / answer_correctness / context_recall / precision).

## Results

### Deterministic harness (recall + citations)
| arm | recall@5 | citation grounding | behavior conformity | abstention |
|---|--:|--:|--:|--:|
| baseline | **0.889** | 1.000 | 0.944 | 0.056 |
| dedup+litm | 0.833 | 1.000 | 0.944 | 0.056 |

### Ragas (n=18, single run per arm)
| metric | baseline | dedup+litm | Δ |
|---|--:|--:|--:|
| faithfulness | **0.890** | 0.874 | **−0.016** |
| answer_correctness | **0.690** | 0.644 | −0.046 |
| answer_relevancy | **0.768** | 0.734 | −0.034 |
| context_precision | **0.770** | 0.675 | −0.096 |
| context_recall | **0.944** | 0.889 | −0.056 |

Cost: baseline $0.063 + treatment $0.064 Azure (+ ~$0.03 deterministic). Judge gpt-5.4-mini.

## Discovery — the treatment lost on every metric
1. **Every Ragas metric regressed**, and `context_recall` (−0.056) tracks the deterministic recall
   drop (0.889→0.833) exactly: **dedup removed a chunk that a gold case needed.** Because dedup keys
   on content (word-set Jaccard ≥ 0.9) but recall is scored by `chunk_id`, a near-duplicate that
   *was* the gold chunk gets dropped even though equivalent text survives — so part of the recall
   penalty is a scoring artifact, but `context_precision` (−0.096) and `answer_correctness` (−0.046)
   fell too, which is **not** an artifact: the pipeline genuinely produced slightly worse answers.
2. **Faithfulness per-case was mixed, not uniformly worse** (+0.143 on two cases, −0.124 and −0.500
   on two others). The −0.016 mean is driven by one case (`ntrs-v2-16`, already weak at 0.50 →
   0.00). At n=18 with a single judge pass this is **within noise** — but noise that fails to clear
   the bar is still a fail: there is **no measured win to justify a regression elsewhere**.
3. **`litm` is recall-neutral by construction; `dedup` carries the cost.** The combined treatment
   conflates them — the recall/precision loss is all dedup's. `litm`'s isolated effect on
   faithfulness is **unmeasured** here (a clean follow-up: `--ctx-litm` only).

## Verdict
**Do not promote. The context-engineering knobs stay opt-in and off by default** — ADR 0032's
promotion bar (faithfulness ≥ baseline AND a recall/correctness win) is **not met**; the treatment
is ≤ baseline on all five metrics. This is the MISSION-044 result again: *more/different context is a
trade-off, not a free win.* The value delivered is the **measurement + the instrument** (the A/B
wiring, now reusable), not a new default. The structural design choice — ship opt-in + A/B-gated —
is vindicated: had these been defaults, they'd have silently degraded quality.

## Honest limits
- **n=18, single Ragas run per arm** → judge noise; per-case faithfulness swings ±0.5. A promotion
  decision would need `--runs`-averaged Ragas; a *rejection* is safe (nothing cleared the bar).
- **Treatment conflates dedup + litm.** The one knob that *cannot* cost recall (`litm`) was never
  isolated — if context engineering is revisited, measure `litm`-only first.
- **NTRS (EN) only**, k=5. A corpus with more redundant/duplicated chunks (where dedup has real work)
  could differ — dedup's premise is near-duplicate chunks, and this gold had few.
- The cross-encoder reranker (ADR 0032 §3) is **not** tested here — it's model-dependent and belongs
  behind the `Reranker` port, measured separately.

## Operational lesson (recorded)
Running the two Ragas arms **in parallel** tripped Azure **429 rate-limits** (`gpt-5.4-mini`,
francecentral — shared TPM, same class as MISSION-045/PR #102). The treatment arm crashed; re-running
the arms **serially** succeeded cleanly. **Serialize paid LLM-judged A/B arms** — they share one
quota; parallelism buys nothing but throttling.

## See also
Reproduce: `… eval ragas --gold eval-results/ab/ntrs_gold_v2.json --tenant <ntrs> --k 5 [--ctx-dedup
--ctx-litm] --out eval-results/ab/<arm>`. Results: `eval-results/ab/ctx_baseline/ragas.json`,
`eval-results/ab/ctx_dedup_litm/ragas.json`. Strengthens [ADR 0032](../../adr/0032-memory-and-context-engineering.md)'s opt-in + A/B-gated stance with measured backing.
