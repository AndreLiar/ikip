# MISSION-043 — First *measured* RAG quality on the multi-tenant corpora (anecdote → numbers)

- **Mode:** Autonome (measurement + honest retrospective)
- **Date:** 2026-11-14
- **Related:** Epic 5 (eval) · [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md) · concept [rag-evaluation-metrics](../concepts/rag-evaluation-metrics.md) · [Epic 10 agentic](../../prd/epic-10-agentic-rag.md)

## Objective
After ingesting 7 tenants, the only quality signal was a single `/ask` anecdote — and I had
over-interpreted it twice (claimed "quality is bad", then hypothesised "boilerplate pollution").
Replace anecdote with **numbers**: prove/disprove the boilerplate claim, and run **Ragas** (LLM-judged)
on a gold set to measure **correctness + recall**, not just faithfulness.

## Method
1. **Boilerplate probe** — dump the chunks actually retrieved for an NTRS question + count corpus-wide
   STI-boilerplate markers.
2. **Silver gold set** — for NTRS (EN) and the law corpus (FR), an LLM generated one `question +
   reference answer` from each of 5 real chunks (saved `eval-results/gold_mini.json`). **Silver**, not
   human-verified — stated plainly.
3. **System run** — `make_hybrid_retrieve` (tenant-scoped) + `grounded_answer` per question.
4. **Ragas** (`RagasAdapter`, Azure judge): faithfulness, answer_relevancy, context_precision,
   **context_recall**, **answer_correctness**.

## Results

### Boilerplate pollution — DISPROVEN
Top-6 retrieved for *"What test or operational procedures are described?"* were real content
(`Emergency Procedures`, `Detailed Test Plan`, `OPERATIONS AND TEST PROCEDURE MANUAL`), **0/6 boilerplate**.
Corpus-wide: **71 / 157 607** NTRS chunks carry STI markers (**0%**). My earlier "boilerplate" diagnosis
was wrong; the bad first answer came from **my question phrasing** + variance.

### Ragas (silver gold, n=5/corpus)
| metric | NTRS EN | Droit FR |
|---|--:|--:|
| faithfulness | 0.60 | **1.00** |
| answer_relevancy | 0.52 | **0.89** |
| context_precision | 0.57 | **0.98** |
| context_recall | 0.60 | **1.00** |
| answer_correctness | 0.53 | 0.69 |

## Discovery (it corrected BOTH of my wrong calls)
- **There IS a real quality gap** — but not where I thought. **Droit FR is strong** (recall 1.0, faithfulness 1.0,
  precision 0.98); **NTRS EN is mediocre** (recall 0.60, faithfulness 0.60, correctness 0.53).
- **Cause = scale/corpus, not boilerplate.** NTRS = 500 large scientific PDFs → **157k chunks**, and the gold
  questions ask for **specific details** (needle-in-haystack). Law = 500 **short, self-contained** decisions →
  **1.8k chunks** → retrieval nails it.
- **Honest caveat — the silver gold is uneven.** The LLM generated some **degenerate NTRS questions** (e.g.
  *"what value appears immediately after `0.000000E+00` in the passage?"* — a positional table lookup, not a
  semantic RAG question). Those unanswerable-by-design items **drag NTRS down** independently of retrieval.
  So NTRS's 0.60 is *partly* a weak-gold artifact, not pure retrieval failure.

## Honest limits of this eval
- **Silver gold** (LLM-from-corpus), **N=5** per corpus → indicative, not definitive.
- **LLM self-judge** (Ragas + our own validator use the same model family) → self-consistency bias.
- `answer_relevancy` warning ("1 generation instead of 3") → minor noise.

## Meta-lesson
**Both my pessimism AND the boilerplate hypothesis were anecdote; measurement overturned both.** The engineering
plumbing (tenant-scoped retrieval, citations, grounding/abstention) is solid; measured **faithfulness/recall are
excellent on a focused corpus (law)** and **weak on a large, detail-heavy one (NTRS)**.

## Next (the real quality work)
1. **Human-verified gold** (10–15 Q/A/corpus) + larger N; filter degenerate auto-questions.
2. **NTRS retrieval**: better chunking for large PDFs + reranking/query-analysis tuned per domain.
3. Wire these gold sets into the **Epic 5 harness** (custom Recall@K + Ragas) as a per-corpus regression gate.
4. NTRS "specific detail" is the **weak-first-retrieval** case for **agentic reformulation** (Epic 10).

## See also
Raw numbers + gold: `eval-results/gold_mini.json`. Concept: [rag-evaluation-metrics](../concepts/rag-evaluation-metrics.md).
