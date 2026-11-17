# MISSION-050 — Build + measure the query-decomposition slice (the first agentic flow passes its gate)

- **Mode:** Autonome (build the measured slice, then gate it end-to-end)
- **Date:** 2026-11-17
- **Related:** [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) (design) · [MISSION-049](../MISSION-049/mission.md) (the multi-hop failure + the "only decomposition fixes it" battery) · [MISSION-045](../MISSION-045/mission.md) (recall@id sibling-chunk caveat) · concept [agentic-rag](../concepts/agentic-rag.md) · Epic 10 Story 10.5

## Objective
MISSION-049 proved the fixed flow fails on multi-hop and that **only multi-query decomposition**
recovers it (oracle recall 0.444 → 0.889). This mission **builds** that slice on the agentic
foundation (Tool port, #130) and runs the ADR 0033 **gate** — not chunk-id recall (which MISSION-049
already covered) but the end-to-end answer quality the product actually cares about.

## What was built (`ikip_common/agent/decompose.py`)
`decompose (1 LLM split) → fan-out retrieval over a RetrievalTool → merge (union, dedup) → existing
generate/validate`. Degrades to single-shot for a simple question (zero overhead) and on any LLM
error (never breaks retrieval). Uses the foundation's **Tool port** (provenance + tenant scope) but
**not** the cyclic controller — a static fan-out must run *every* sub-query, whereas the controller's
`no_progress`/loop guards (for a *dynamic* agent) would truncate it. Wired behind `--decompose` on the
eval CLI. 9 pure tests + grounding untouched (generation still answers the *original* question over
merged, cited evidence).

## The gate — fixed flow vs decompose on the 2-hop probe (Ragas, n=9)
| metric | fixed flow | decompose | Δ |
|---|--:|--:|--:|
| **answer_correctness** | 0.483 | **0.742** | **+0.259** |
| **faithfulness** | 0.730 | **0.908** | **+0.178** |
| answer_relevancy | 0.668 | 0.827 | +0.159 |
| **context_recall** (Ragas, semantic) | 0.444 | **0.889** | **+0.444** |
| context_precision | 0.748 | 0.679 | −0.069 |

Plus deterministic end-to-end: **abstention 0.111 → 0.000**, **behavior conformity 0.889 → 1.000**
(3-hop: abstention 0.333 → 0.000, conformity 0.667 → 1.000). The slice **passes**: it fixes the
measured failure all the way to answer correctness, not just retrieval. Only `context_precision`
dipped slightly (−0.069) — the expected "more context = marginally more noise" trade, far outweighed.

## Discovery — the metric trap: `recall@exact-chunk-id` nearly reported a false negative
Running the probe with `--decompose`, the deterministic **`recall@5`-by-chunk-id stayed flat (0.444)**
— even at a union budget (k=10). Taken alone that reads as "decomposition didn't help." It's wrong,
for two compounding reasons:
1. **Union truncation** — decomposition merges *parts × k* candidates; `recall_at_k` only scores the
   top-`k`, so a second hop's chunk at position 6+ is invisible to the metric.
2. **Equivalent-but-different chunks** — the LLM's sub-question retrieves a chunk that *answers* the
   hop but isn't the single gold-labelled id (the MISSION-045 sibling-chunk caveat).

The **semantic** metrics saw through both: Ragas `context_recall` (LLM-judged: can the ground truth be
attributed to the retrieved context?) recovered **0.444 → 0.889** — matching the MISSION-049 oracle —
and `answer_correctness` rose **+0.259**. The per-case answers confirm it directly: `mh-1-2` cites
**[E1] and [E8]** — *both* hops. **Lesson:** for multi-hop / union retrieval, `recall@exact-id` is the
wrong gauge; gate on answer-level + semantic metrics. (I almost shipped the false negative — logging it.)

## Verdict
**Decomposition is a measured win — promote it from behind the flag to the default for multi-part
questions** (gated by a "is this compound?" check so simple lookups keep the zero-overhead single-shot
path). This is the first agentic capability to *earn* its place by measurement, in contrast to the
rejected (BM25, dedup) and deferred (cross-encoder) ones — the discipline cuts both ways.

## Honest limits
- **n=9, single Ragas run.** A promotion-to-default should `--runs`-average (MISSION-047) and widen the
  gold; the *direction* (+0.26 correctness, +0.44 recall, abstention→0) is far outside one-run noise.
- **Synthetic compound phrasing** ("q1 Separately q2"); real integrated multi-hop may split less
  cleanly — re-confirm on natural questions.
- **Cost/latency**: decompose adds 1 LLM split + N retrievals (~7.6 s/case observed vs single-shot);
  acceptable for the hard tail, which is why it stays **off** for simple questions.
- **English/NTRS only.** Re-confirm on an FR corpus before a global default.
- Still only the *decomposition* capability — the cyclic controller remains unexercised by a shipped
  flow; it waits for a capability whose steps depend on prior observations (ADR 0033 scope).

## See also
`ikip_common/agent/decompose.py` · reproduce: `eval ragas --gold eval-results/ab/ntrs_multihop_probe_2hop.json --tenant <ntrs> --k 5 [--decompose] --out …`. Confirms [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md)'s decomposition slice against its gate.
