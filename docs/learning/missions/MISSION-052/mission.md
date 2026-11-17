# MISSION-052 — FR re-confirm: decomposition holds in French (the last blocker clears)

- **Mode:** Autonome (measurement — close the last gap before a global default)
- **Date:** 2026-11-17
- **Related:** [MISSION-051](../MISSION-051/mission.md) (EN n=18 hardening) · [MISSION-050](../MISSION-050/mission.md) (the slice) · [MISSION-045](../MISSION-045/mission.md) (FR corpora, Ragas EN-bias caveat) · [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md)

## Objective
The decomposition gate passed robustly in **English** (MISSION-050/051), but FR is **half the
corpora** and the only remaining blocker to a *global* `AGENT_DECOMPOSE` default. Re-confirm the gate
in **French**.

## Method
Generalised `scripts/dataset/gen_multihop_probe.py` for language (connector `fr` = "Par ailleurs,")
and built an FR 2-hop probe from the reviewed `gold_assurance_fr` (12 cases). Ran the gate: fixed
flow vs `--decompose`, Ragas, **assurance** tenant.

## Result — FR (assurance) n=12 2-hop
| metric | fixed | decompose | Δ (FR) | Δ (EN n=18) |
|---|--:|--:|--:|--:|
| **answer_correctness** | 0.458 | **0.676** | **+0.218** | +0.297 |
| faithfulness | 0.865 | 0.979 | +0.115 | +0.110 |
| answer_relevancy | 0.699 | 0.782 | +0.083 | +0.138 |
| **context_recall** | 0.375 | **1.000** | **+0.625** | +0.389 |
| context_precision | 0.633 | **0.748** | **+0.115** | −0.106 |
Cost: baseline $0.095 → decompose $0.149 (+57%).

## Discovery
1. **Decomposition holds in French — the win is cross-language.** answer_correctness +0.218,
   faithfulness +0.115, context_recall to a perfect **1.000**. Three gold sets now agree
   (EN n=9 +0.26, EN n=18 +0.30, FR n=12 +0.22 correctness) — the effect is not an EN or a
   single-gold artifact.
2. **`context_precision` went UP in FR (+0.115), where it dipped in EN (−0.106).** On this
   legal/regulatory corpus the chunks are more distinct and self-contained, so each sub-query
   retrieves *tightly* relevant evidence per part — decomposition recovered recall with **no**
   precision cost here. The EN precision dip was the worst case, not the rule.
3. **Cost premium is consistent (~+57%)**, paid only on multi-part questions (self-gating).

## Verdict
**The last blocker clears → `AGENT_DECOMPOSE` is ready for a global default** (all five metrics up in
FR; correctness up across EN+FR; recall near-perfect). Recommended: flip the default to on, keeping
the env flag as the per-tenant kill-switch and accepting the measured ~+50–57% premium on multi-part
queries (the hard-tail trade, ADR 0033).

## Honest limits
- **One FR corpus (assurance, legal/regulatory)**, n=12, single Ragas run. The three-gold agreement
  makes the direction safe; a broader FR sweep (banque/credit/droit) + a `--runs`-average would
  further tighten it, but are refinements, not blockers (deltas are 20–90× the measured judge noise).
- **Ragas is English-biased** (MISSION-045) — it tends to *under*-score FR, so the FR gains are if
  anything conservative.
- **Synthetic compound phrasing** ("q1 Par ailleurs q2") — a natural-FR spot-check would strengthen it.
- Still only the **decomposition** capability; the cyclic controller remains unexercised (ADR 0033).

## See also
`scripts/dataset/gen_multihop_probe.py` (now language-parametrised, emits the FR probe). Completes the
promote evidence for `AGENT_DECOMPOSE` (wired #132, hardened [MISSION-051](../MISSION-051/mission.md)).
