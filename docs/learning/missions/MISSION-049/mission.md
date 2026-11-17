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
the multi-hop **structure**, not missing data. Deterministic `eval run`, NTRS tenant (~$0.015/arm).
Then a **decision battery** to rule out the cheap fixes: k-sweep (k=10/20), the existing `--rewrite`,
and a decomposition baseline (per-part retrieval unioned — computed free from the single-hop run).

## Results
### A. The gap (single-shot, k=5)
| arm | chunks needed | recall@5 | abstention | behavior conformity |
|---|--:|--:|--:|--:|
| single-hop (baseline) | 1 | **0.889** | 0.056 | 0.944 |
| 2-hop probe | 2 | **0.444** | 0.111 | 0.889 |
| 3-hop probe | 3 | **0.278** | 0.333 | 0.667 |

### B. Decision battery — rule out the cheap fixes before concluding "go agentic"
A real reason to change the pipeline must survive the cheaper alternatives. It does:

| fix | 2-hop recall | 3-hop recall | ruled out? |
|---|--:|--:|---|
| single-shot @k=5 (baseline) | 0.444 | 0.278 | — (the gap) |
| **bigger k** @k=10 | 0.444 | 0.389 | ✓ no help |
| **bigger k** @k=20 (4×) | 0.500 | 0.444 | ✓ 4× budget barely moves it |
| **existing query-rewrite** @k=5 | 0.444 | 0.111 | ✓ no help — *hurts* 3-hop |
| **decomposition (multi-query)** @k=5 | **0.889** | **0.889** | ← the only thing that fixes it |

"decomposition" = split the compound question into its parts, retrieve each **separately** at k=5,
union the results (computed from the single-hop run's per-case retrieved ids — the baseline *is* the
decomposed retrieval). It **fully recovers** recall at both arities.

## Discovery — single-shot retrieves ≈one hop, and only decomposition fixes it
1. **Recall collapses with hops, and it is NOT a k-budget problem.** k=5 easily holds 2–3 chunks, and
   raising k to **20 (4×) barely moves it** (2-hop 0.444→0.500; 3-hop 0.278→0.444). The arithmetic is
   the tell: single-shot fetches **≈one hop's worth of evidence** regardless of arity. The failure is
   **query representation** — one blended embedding of a multi-part question is dominated by one part,
   so the other parts' chunks never rank into the top-k, *even at k=20*.
2. **The one single-query knob we already have makes it worse.** `--rewrite` (ADR 0026 reformulation)
   leaves 2-hop flat (0.444) and **drops 3-hop to 0.111** — reformulating into *one* query can only
   re-blend the hops, not separate them. Confirms the fix must be **multi-query**, not a better single
   query.
3. **Decomposition fully recovers recall (0.444/0.278 → 0.889).** Retrieve each sub-question
   separately and union — the baseline single-hop run *is* that decomposition — and recall returns to
   the single-hop level at both arities. The mechanism is proven, not assumed.
4. **The end answer degrades too, not just the metric.** Abstention climbs 0.056 → 0.111 → 0.333 as
   hops increase — a real failure, not a recall artifact.

## Verdict — a real reason for *decomposition*, not (yet) for a full agent
**The multi-hop failure is real, and the cheap fixes are ruled out** (bigger k: no; single-query
rewrite: no/worse) — **only multi-query decomposition recovers recall.** That is a genuine,
measured reason to go beyond single-shot retrieval, and it is the *opposite* of BM25 (MISSION-046) /
dedup (MISSION-047), where the baseline was already strong and the add-on didn't earn its place.

But be precise about **what** is justified:
- **Justified now (measured):** **query decomposition / multi-query retrieval** — Epic 10
  **Story 10.5** (+ the retrieval half of 10.3). The minimal form is bounded and barely "agentic":
  *one* LLM split-call → N parallel retrievals → synthesize with per-part citations. One extra LLM
  call, deterministic fan-out. This probe is its gold set; `recall 0.444 → ~0.89` is its target.
- **NOT yet justified:** the **full cyclic plan–act–observe agent** (Story 10.2), self-critique
  (10.6), tool-selection, iterative conditional steps. This probe says nothing about them — they
  answer a *different* failure (decomposition not knowable up front, cross-tool reasoning) that we
  have **not** measured. Building the whole controller on this evidence would repeat the mistake we
  avoided with the reranker: paying for complexity the measurement doesn't demand.

So: **yes, there is a real reason to evolve — but the measured reason is a decomposition *step*, the
smallest slice of Epic 10, not a wholesale switch to an agentic pipeline.**

## Honest limits — what this does and does NOT justify
- **Capability failure, not proven demand.** This shows the flow *can't* do multi-hop; it doesn't show
  users *ask* multi-hop. Before shipping even the decomposition step, confirm multi-hop/compositional
  questions are a real share of traffic (sample `trace`/conversation logs — none meaningful yet, this
  is pre-production). The probe justifies the *capability*, not the priority.
- **Recall, not end-to-end answer quality.** Measured retrieval recall, not final `answer_correctness`.
  But recall is the binding ceiling — un-retrieved evidence can't be answered — so 0.444 caps answer
  quality regardless. The natural confirmation is a decomposed-vs-baseline Ragas run (deferred).
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
