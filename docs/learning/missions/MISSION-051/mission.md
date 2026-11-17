# MISSION-051 — Harden the decomposition gate (n=9 → n=18): the win is robust

- **Mode:** Autonome (measurement — close the "thin gate" gap before promoting a default)
- **Date:** 2026-11-17
- **Related:** [MISSION-050](../MISSION-050/mission.md) (the slice passed at n=9) · [MISSION-049](../MISSION-049/mission.md) (the multi-hop failure) · [MISSION-047](../MISSION-047/mission.md) (small-n lies: n=5→18 reversed) · [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md)

## Objective
MISSION-050 passed the decomposition gate but at **n=9, single Ragas run** — and MISSION-047 is the
cautionary tale that a small gold can give a confident wrong answer (the auto-merge "regression" at
n=5 vanished at n=18). So before recommending `AGENT_DECOMPOSE` as a default, **re-run the gate on a
wider gold** with *different* question pairings.

## Method
Extended `scripts/dataset/gen_multihop_probe.py` with an **offset pairing** `(i, i+half)` — a
distinct set of compound questions from the consecutive pairing — to widen the 2-hop gold **n=9 →
n=18** (`ntrs_multihop_probe_2hop_wide.json`). Re-ran the ADR 0033 gate: fixed flow vs `--decompose`,
Ragas, NTRS tenant.

## Result — fixed flow vs decompose (n=18)
| metric | fixed | decompose | Δ (n=18) | Δ (n=9, M-050) |
|---|--:|--:|--:|--:|
| **answer_correctness** | 0.454 | **0.751** | **+0.297** | +0.259 |
| **faithfulness** | 0.798 | **0.907** | **+0.110** | +0.178 |
| answer_relevancy | 0.620 | 0.759 | +0.138 | +0.159 |
| **context_recall** | 0.472 | **0.861** | **+0.389** | +0.444 |
| context_precision | 0.702 | 0.596 | **−0.106** | −0.069 |

Cost: baseline $0.073 → decompose $0.109 over 18 cases (**+50%**, ≈ +$0.002/case).

## Discovery
1. **The win is robust, not small-n noise.** Doubling the gold with *different* pairings reproduced
   every delta; `answer_correctness` even grew (+0.26 → **+0.30**), `context_recall` held (+0.39).
   This is the *opposite* of the auto-merge n=5→18 reversal (MISSION-047) — the decomposition signal
   is stable and large, so the promote decision rests on firm ground.
2. **The one real cost is `context_precision` (−0.106), and it's expected**: decomposition merges a
   larger evidence union, so a slightly higher share is non-essential. It is far outweighed by
   +0.30 correctness / +0.39 recall — the generator uses the extra relevant evidence and the
   grounding validator drops the rest (faithfulness still **rose** +0.11).
3. **Cost is a +50% per-query premium (~+$0.002/case)** — paid *only* on multi-part questions, since
   `decompose_question` self-gates a single ask back to the single-shot path. The hard-tail premium
   is the deliberate trade (ADR 0033).

## Verdict
**The gate passes robustly → `AGENT_DECOMPOSE` is promotable.** Recommendation: **enable it (per
tenant) now**; the global default-on flip still warrants two cheap follow-ups kept honest below.

## Honest limits (what still gates a *global* default-on)
- **Single Ragas run per arm** (both n). The *direction + magnitude* are far outside one-run judge
  noise (M-047 measured faithfulness judge-std ≈0.004; these deltas are 20–90×), so a `--runs`-average
  is a nicety, not a blocker — but do it before flipping the global default.
- **EN / NTRS only.** The decompose split is language-general, but **re-confirm on an FR corpus**
  (an FR multi-hop probe from the existing FR gold) before a global default — FR is half the corpora.
- **Synthetic compound phrasing** ("q1 Separately q2"); real integrated multi-hop ("compare X vs Y")
  may split less cleanly — a natural-phrasing spot-check would strengthen it further.
- Still only the **decomposition** capability; the cyclic controller remains unexercised (ADR 0033).

## See also
`scripts/dataset/gen_multihop_probe.py` (now emits the wide set). Hardens [MISSION-050](../MISSION-050/mission.md)'s result; backs promoting `AGENT_DECOMPOSE` (wired in ADR 0033 / #132).
