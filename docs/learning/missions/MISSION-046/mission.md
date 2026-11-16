# MISSION-046 — Would BM25 / a dedicated search engine help? (measure the lexical arm first)

- **Mode:** Autonome (measurement — answer a "should we add X" architecture question with evidence)
- **Date:** 2026-11-16
- **Related:** [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) (hybrid on Postgres; `ts_rank` not true BM25) · concept [retrieval](../concepts/retrieval.md) · [MISSION-044](../MISSION-044/mission.md) / [MISSION-045](../MISSION-045/mission.md) (FR gold)

## Objective
Recurring question: our lexical arm is Postgres `ts_rank`, not true BM25 — would **BM25 (via a pg
extension or OpenSearch)**, or a **French analyzer**, improve retrieval? Rather than adopt on
intuition (and pay a second datastore's run/sync/secure cost), **measure whether the lexical arm is
even the bottleneck.**

## Method
`scripts/probe_lexical_value.py` — isolates the **lexical arm only** (hybrid would let the strong
vector arm mask it) and measures **lexical-only recall@5** against each FR gold (fully SME-reviewed,
MISSION-045), across:
- **query type:** natural-language question (what users ask) vs keyword/identifier query (extracted
  refs/rare terms from the gold chunk — **BM25's actual strength**);
- **analyzer:** `simple` (current, no stemming) vs `french` (stemming/accent-folding).

Free + deterministic (recall@5 on `relevant_chunk_ids`, no Azure).

## Results (lexical-only recall@5)
| corpus | NL `simple` | NL `french` | KW `simple` | KW `french` |
|---|--:|--:|--:|--:|
| law_fr | 0.000 | 0.000 | 0.833 | 0.667 |
| assurance_fr | 0.000 | 0.000 | 0.909 | 0.909 |
| banque_finance_fr | 0.000 | 0.083 | 0.917 | 0.917 |
| credit_conso_fr | 0.000 | 0.083 | 0.917 | 0.750 |

## Discovery — three measured findings, all pointing the same way
1. **On natural-language questions the lexical arm is ~dead (recall ~0).** `websearch_to_tsquery`
   ANDs the question's terms; a long NL question never shares *all* its words with the target chunk.
   **The vector arm carries 100% of NL retrieval** (confirms the MISSION-044 messy-question hint).
   BM25 is a *ranking* refinement — it cannot rank what does not match. **BM25 helps nothing for the
   queries users actually ask.**
2. **On keyword/identifier queries (BM25's home turf) the lexical arm is ALREADY strong (0.83–0.92)
   with plain `ts_rank`.** Even in its best case BM25 would re-rank an already-mostly-correct set —
   a marginal gain on a narrow query type our users rarely issue.
3. **The French analyzer is rejected too.** No help on NL (+0.04) and **worse** on identifier
   matching (law 0.83→0.67, credit 0.92→0.75) — French stemming mangles legal shorthand (`l 1950`,
   article refs). My own "try the `french` config first" hypothesis: **disproven by measurement.**

## Verdict
**Do not add BM25 or OpenSearch; do not switch to the `french` analyzer.** The lexical arm already
does its one real job (exact-term matching) well, and the job it *can't* do (natural language) is
the **vector arm's**, which is already strong (MISSION-045: faithfulness 0.94–1.0). ADR 0004's
revisit trigger — *"recall plateaus AND it's attributable to the lexical arm"* — is **not met.**
And BM25 ≠ OpenSearch: if BM25 ever *were* warranted, a **pg extension** (ParadeDB `pg_search`)
keeps it in one datastore — OpenSearch's second-datastore tax (sync a copy of all text, enforce
tenant isolation twice) is the worst-value path to a ranking refinement we don't need.

## Honest limits
- Keyword queries are **synthetically** extracted from the gold chunks (identifiers/rare terms) —
  indicative of the exact-term case, not a real user-query distribution.
- Single-gold-chunk recall (the law sibling-chunk caveat, MISSION-045); n≈12/corpus; silver→reviewed.
- Tests the **FR** corpora; an identifier-heavy EN manual corpus *could* differ — re-run the probe there before revisiting.

## See also
`scripts/probe_lexical_value.py` (reproduce). Strengthens [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md)'s "no dedicated search engine at MVP" with measured backing.
