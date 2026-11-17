# MISSION-049 — Does the fixed flow actually fail on multi-hop? (measure before building Epic 10)

- **Mode:** Autonome (measurement — turn "should we build agentic RAG?" into evidence)
- **Date:** 2026-11-17
- **Related:** [ADR 0026](../../adr/0026-agentic-rag-evolution.md) (agentic evolution — triggered) · [Epic 10](../../prd/epic-10-agentic-rag.md) (Stories 10.3 iterative retrieval / 10.5 decomposition) · [MISSION-046](../MISSION-046/mission.md) (BM25 "measure first") · [MISSION-047](../MISSION-047/mission.md) · concept [hybrid-retrieval](../concepts/hybrid-retrieval.md)

## Objective
ADR 0026 says build agentic RAG only when "the eval harness shows a **recurring failure class** the
fixed flow can't fix." Epic 10's first high-value step is decomposition / iterative retrieval for
**multi-hop** questions. Before implementing any of it, **measure** whether the fixed single-shot
flow actually fails on multi-hop — or whether k=5 already copes.

## Method — grounded, not invented
`scripts/dataset/gen_multihop_probe.py` combines N existing single-hop `ntrs_gold_v2` cases into ONE
compound question whose `relevant_chunk_ids` is the **union** of the parts (9 two-hop, 6 three-hop).
The fixed flow does **one** retrieval for the whole question, so `recall@5` on the union measures
whether a single query embedding can surface **all** the distinct chunks at once. Each chunk is known
to exist and be individually retrievable (single-hop recall@5 = 0.89), so any drop is attributable to
the multi-hop **structure**, not missing data. Deterministic `eval run`, k=5, NTRS tenant (~$0.015/arm).

## Results
| arm | chunks needed | recall@5 | abstention | behavior conformity |
|---|--:|--:|--:|--:|
| single-hop (baseline) | 1 | **0.889** | 0.056 | 0.944 |
| 2-hop probe | 2 | **0.444** | 0.111 | 0.889 |
| 3-hop probe | 3 | **0.278** | 0.333 | 0.667 |

## Discovery — single-shot retrieves ≈one hop, no matter how many the question needs
1. **Recall collapses with hops, and it is NOT a k-budget problem.** k=5 easily holds 2–3 chunks, yet
   recall falls 0.889 → 0.444 → 0.278. The arithmetic is the tell: 0.444×2 ≈ **0.89 chunks** retrieved
   of 2; 0.278×3 ≈ **0.83 chunks** of 3. Single-shot retrieval reliably fetches **about one hop's
   worth of evidence** regardless of the question's arity. The failure is **query representation** —
   one blended embedding of a multi-part question is dominated by one part, so the other parts' chunks
   never rank into the top-k. This is exactly the gap decomposition (Story 10.5) / iterative retrieval
   (Story 10.3) target.
2. **The end answer degrades, not just the metric.** Abstention climbs 0.056 → 0.111 → 0.333 and
   behavior conformity falls 0.944 → 0.889 → 0.667: as hops increase, the flow increasingly can't
   ground and gives up — a real failure, not a recall-metric artifact.
3. **The fix is already quantified.** The single-hop baseline *is* the decomposed case: each
   sub-question retrieved **alone** scores 0.889. So decomposing the 2-hop question into its parts and
   unioning the retrievals would recover recall **0.444 → ~0.89**. That's the measured value of
   Story 10.5, in one number, before writing it.

## Verdict
**The multi-hop failure class is real and measured — the ADR 0026 trigger is met for decomposition /
iterative retrieval (Epic 10 Stories 10.5 / 10.3).** This is the opposite of the BM25 (MISSION-046)
and dedup (MISSION-047) results: there the add-on couldn't beat an already-strong baseline; here the
baseline **structurally fails** (recall halves at 2 hops) and the decomposed recall shows the fix
works. If/when Epic 10 is built, this probe is its gold set and `recall@5 0.444 → ~0.89` is its target.

## Honest limits — what this does and does NOT justify
- **Capability failure, not proven demand.** This shows the flow *can't* do multi-hop; it doesn't show
  users *ask* multi-hop. Before shipping Epic 10, confirm multi-hop/compositional questions are a real
  share of traffic (sample `trace`/conversation logs). The probe justifies the *capability*, not the
  priority.
- **Compound phrasing is synthetic.** "q1 Separately q2" concatenates two NTRS topics; real multi-hop
  ("compare X vs Y") is more integrated — but that blends the embedding *more*, so the measured
  degradation is a floor, not an exaggeration.
- **Scope = decomposition/iterative retrieval only.** It does **not** justify the full agentic
  controller, self-critique, or planning — each needs its own evidence (ADR 0026's per-step gate).
- **Cross-domain (cross-corpus) is a separate, even stronger argument** and was *not* tested here:
  retrieval is tenant-scoped (NFR10), so the fixed flow **structurally cannot** reach a second corpus
  at all — that's multi-corpus routing (Story 10.4), provable by construction, not by this probe.

## See also
`scripts/dataset/gen_multihop_probe.py` (reproduce the gold). Probe gold: `eval-results/ab/
ntrs_multihop_probe_{2,3}hop.json` (gitignored; regenerate). Supplies [ADR 0026](../../adr/0026-agentic-rag-evolution.md)'s "recurring failure class" trigger with measured backing.
