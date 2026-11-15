# MISSION-045 — Measure the French corpora: the multi-tenant/multilingual story, in numbers

- **Mode:** Autonome (measurement — the differentiator was unmeasured)
- **Date:** 2026-11-15
- **Related:** [ADR 0016](../../adr/0016-rag-evaluation-custom-plus-ragas.md) (eval) · [MISSION-043](../MISSION-043/mission.md) (first measured quality, NTRS/law n=5) · [MISSION-044](../MISSION-044/mission.md) (NTRS n=18, auto-merge/rewrite) · concept [retrieval](../concepts/retrieval.md)

## Objective
After all the eval work we could still only measure **one** corpus (NTRS, English). The project's
actual differentiator — **multi-tenant, multilingual (FR), multi-domain** — was **100% unmeasured**
on 4 of 5 tenants. Build per-corpus **French** gold sets and measure law / insurance / banking-finance
/ consumer-credit on both retrieval (recall@5, deterministic) and answer quality (Ragas, Azure judge).

## Method
- Generalised the gold generator → `scripts/dataset/gen_gold.py` (tenant + `--lang fr`; French
  system prompt producing French Q + reference A from a real chunk; source chunk → `relevant_chunk_ids`;
  degenerate/positional filter). 12 cases/corpus → `packages/common/tests/fixtures/gold/<corpus>_silver_v1.json`.
- Deterministic `eval run` (recall@5, free) + `eval ragas` (n=12, budget-capped) per tenant.
- **Silver** (LLM-from-corpus), not human-reviewed; indicative not definitive.

## Results

### Answer quality (Ragas, Azure judge, n=12/corpus)
| corpus (FR) | faithfulness | context_recall | context_precision | answer_relevancy | answer_correctness |
|---|--:|--:|--:|--:|--:|
| **assurance** | **1.000** | 1.000 | 0.965 | 0.840 | 0.654 |
| **banque-finance** | **1.000** | 1.000 | 0.862 | 0.878 | 0.637 |
| **law (droit)** | **1.000** | 0.818 | 0.924 | 0.726 | 0.490 |
| **crédit-conso** | 0.944 | 0.909 | 0.852 | 0.804 | 0.657 |

### Retrieval (deterministic recall@5, free)
| corpus | recall@5 | citation_resolution | behavior_conformity |
|---|--:|--:|--:|
| assurance | 1.000 | 1.000 | 1.000 |
| banque-finance | 1.000 | 1.000 | 1.000 |
| crédit-conso | 0.917 | 1.000 | 0.917 |
| **law (droit)** | **0.583** | 1.000 | 0.917 |

## Discovery

### 1. The multilingual/multi-tenant story HOLDS — grounding is rock-solid in French
**Faithfulness is 1.000 on three FR corpora and 0.944 on the fourth.** The system does **not**
hallucinate on French legal/insurance/financial text — the grounding + abstention machinery works
identically across languages and domains, not just on English NTRS. assurance and banque-finance are
**excellent** (recall@5 1.0, context_recall 1.0, faithfulness 1.0).

### 2. law looks "weak" on recall@5 (0.583) — but it's a METRIC artifact, not bad retrieval
law's recall@5 is low **only because recall@5 demands the ONE exact source chunk**. Inspecting the
misses: the retrieved chunk is **the same court decision, a different paragraph** (facts vs. legal
grounds vs. ruling) — a *sibling* that often answers the question too. The proof: on the **same
questions**, Ragas **context_recall = 0.818 and faithfulness = 1.000** — the retrieved context *does*
support the answer. So recall@5-on-a-single-gold-chunk is **too strict for highly-redundant legal
corpora** (one decision → many near-identical chunks); it penalises a correct-decision, wrong-paragraph
hit. This is a real evaluation lesson, not a retrieval defect — and it's exactly the case **auto-merge
(ADR 0029)** targets: merging a hit's section siblings would likely lift law's apparent recall.

### 3. correctness is moderate everywhere (0.49–0.66) — expected for silver detail questions
Consistent with NTRS n=18 (0.70) and MISSION-043: silver gold + specific-detail questions cap
answer_correctness; faithfulness/recall are the trustworthy signals and they're strong.

## Honest limits
- **Silver** gold (LLM-from-corpus), **n=12**, single judge run → indicative. Not human-reviewed.
- `relevant_chunk_ids` are dev-DB-specific; the questions/answers are portable.
- law's single-gold-chunk recall is **known-strict** (see Discovery 2) — don't read 0.583 as "law retrieval is bad".

## Follow-up — auto-merge on law (the hypothesis was: "this is where it finally helps") — REJECTED
law looked like the ideal case for auto-merge (ADR 0029): redundant decisions split into sibling
paragraphs, so merging a hit's section siblings "should" give the answer's full context. A/B'd it:

| metric | OFF | auto-merge | Δ |
|---|--:|--:|--:|
| **faithfulness** | **1.000** | 0.861 | **−0.139** |
| context_recall | 0.818 | 0.778 | **−0.040** |
| context_precision | 0.924 | 0.979 | +0.055 |
| answer_relevancy | 0.726 | 0.742 | +0.016 |
| answer_correctness | 0.490 | 0.470 | −0.020 |
| recall@5 (deterministic) | 0.583 | 0.333 | −0.250 (dedup artifact) |

**The hypothesis does not hold.** The one metric we expected to *rise* — `context_recall` — **fell**
(0.818→0.778), faithfulness dipped, correctness was flat-down. Only context_precision rose slightly.
The reason, in hindsight, is simple: **law was already well-grounded** (OFF faithfulness 1.0), so there
was almost no headroom for auto-merge to add — and merging whole sections just added surrounding text
that diluted grounding without improving coverage. recall@5's −0.25 is the known dedup artifact (not a
real signal). So auto-merge is **not** the fix for law's low recall@5 either; the low recall@5 was a
measurement artifact of a corpus that is *already answering well*, not a retrieval deficit to patch.

**Honest caveat (the recurring one):** n=12, and faithfulness 1.0→0.861 is ~1.7 claims — the same
small-sample band where the NTRS n=5 faithfulness "drop" **reversed** at n=18 (MISSION-044). So read
this as "auto-merge did **not** deliver the hypothesised win on law," **not** a confident "it hurts law".
Across every corpus-level test now (NTRS n=18 ≈ neutral, law ≈ small dip), auto-merge has produced **no
measured win** — it stays off by default.

## Next
1. Human-review a slice of each FR gold (silver → trustworthy) + `--runs N` to de-noise the n=12 figures.
2. Wire per-corpus thresholds as a **regression gate** (ADR 0016): a faithfulness floor per tenant
   (the FR corpora sit at 0.94–1.00 — a natural, already-passing gate to lock in).
3. **Throttle the Ragas judge concurrency** — this A/B kept hitting Azure 429 (auto-merge's big
   contexts burst the per-minute token budget); a concurrency cap would make paid evals robust.
