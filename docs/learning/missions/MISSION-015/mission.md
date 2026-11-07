# MISSION-015 — Hybrid retrieval, reranking & filters (Epic 3, Story 3.4)

**Mode:** Guidé (reranking-depth decision) → Autonome (impl) + knowledge transfer.
**Objective:** fuse the lexical + vector arms into one ranked set, rerank it, apply equipment/version filters, and abstain when evidence is insufficient — the retrieval contract the grounded-answer graph (3.5) consumes.
**Maps to:** Epic 3 / Story 3.4. Builds on Story 3.3 (two arms); applies [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Decision
**RRF fusion (in-house) + pluggable `Reranker` port (IdentityReranker default)** (user-chosen). RRF = what LangChain's `EnsembleRetriever` does; it moved to a legacy compat pkg in LangChain 1.x, so we implement the ~15-line algorithm and keep a port where a cross-encoder/Cohere reranker slots in later. No heavy/cross-provider dep at MVP. See [decisions.md](./decisions.md).

## Acceptance criteria
1. Lexical + vector fused into a hybrid result set. — **[verified]** (`reciprocal_rank_fusion`; pure tests; DB fusion test)
2. A reranking step orders results by relevance. — **[verified]** (`Reranker` port + `IdentityReranker`; applied in `hybrid_retrieve`; pure test)
3. Metadata filters: equipment model/revision + version-awareness (applicable vs obsolete). — **[verified]** (`RetrievalFilters`: `is_current`, `document_type`, JSONB `@>`; applied in SQL on both arms; pure SQL-shape tests)
4. Abstention returns "insufficient evidence" under thresholds. — **[verified]** (per-arm `min_score` floors; `RetrievalOutcome(abstained=True)`; DB abstain test)

## Deliverables
- `ikip_common/llm/hybrid.py` — `reciprocal_rank_fusion`, `Reranker` port + `IdentityReranker`, `RetrievalOutcome`, `hybrid_retrieve` (composes the two `IkipRetriever` arms, fuse → rerank → abstain).
- `ikip_common/db/retrieval.py` — `RetrievalFilters` + `_apply_filters` + `min_score` floors on both arms.
- `ikip_common/llm/retriever.py` — `IkipRetriever` gains `filters` + `min_score`.
- Tests: `test_hybrid.py` (4 pure + 2 DB), `test_retrieval.py` filter cases (+2 pure). No migration (filters are pure SQL over existing columns).

## Concepts
Introduces [hybrid-retrieval](../../concepts/hybrid-retrieval.md) (RRF, reranker port, filters, abstention). Reuses [retrieval](../../concepts/retrieval.md), [rag-orchestration](../../concepts/rag-orchestration.md), [dedup-versioning](../../concepts/dedup-versioning.md).
