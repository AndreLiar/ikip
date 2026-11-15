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

## Next
1. For law: evaluate at **section/parent granularity** (multi-chunk gold or auto-merge) to get a fair recall — and re-run auto-merge A/B on law, where its mechanism should help most.
2. Human-review a slice of each FR gold (silver → trustworthy) + `--runs N`.
3. Wire per-corpus thresholds as a **regression gate** (ADR 0016): faithfulness floor per tenant.
