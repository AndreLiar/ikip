# Concept — Hybrid retrieval: fusion, reranking, filters, abstention

_Write-once concept note. First used by Story 3.4. Decisions: [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md), [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md). Follows [retrieval](./retrieval.md)._

## Why fuse the two arms
Lexical (exact terms) and vector (meaning) each miss what the other catches ([retrieval](./retrieval.md)). Running both and **fusing** their ranked lists gives results that are strong on *either* signal — the hybrid set is more robust than either arm alone.

## Reciprocal Rank Fusion (RRF) — why rank-based
The two arms produce **incomparable scores**: `ts_rank` (lexical) and cosine similarity (vector) live on different scales, so you can't just add them. **RRF** sidesteps this by using only **rank position**:

```
score(d) = Σ_arms  1 / (k + rank_arm(d))      # k = 60 (standard), rank 1-based
```

A document ranked high in *either* arm scores well; a document high in *both* wins. No normalization, no score calibration — robust and parameter-light. (This is exactly what LangChain's `EnsembleRetriever` computes; in LangChain 1.x it moved to a legacy compat package, so IKIP implements the ~15-line algorithm itself to keep control of citations + thresholds — [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).)

Dedup is by `chunk_id`; the fused Document keeps its citation metadata and gains `rrf_score`.

## Reranking — a pluggable port
After fusion, an optional **`Reranker`** reorders by true relevance to the query. IKIP ships an **`IdentityReranker`** (no-op, keeps RRF order, truncates to `top_k`) as the default **seam**: a real cross-encoder (local `sentence-transformers`) or a hosted reranker (Cohere) can slot in behind the port later **without touching callers**. We defer the heavy/cross-provider reranker until eval (Story 3.6) shows it's needed — avoiding a GPU/torch dependency (against [ADR 0012](../../adr/0012-local-first-dev-cloud-models-only.md)) or a new vendor key at MVP.

## Filters — version-awareness + equipment (in our SQL)
`RetrievalFilters` applies in SQL on **both** arms, so filtering happens in the database, not after:
- **`current_only`** → `DocumentVersion.is_current` — only **applicable** versions, never a superseded/obsolete revision (FR14/NFR15). This is the version-awareness requirement.
- **`document_type`** → `Document.type`.
- **`metadata`** → JSONB containment (`@>`) on `chunk.chunk_metadata` for equipment model/revision — lightweight at MVP (no dedicated equipment table yet; a planned extension).

## Abstention — "insufficient evidence"
Each arm takes a **`min_score` floor**; hits below it are dropped *before* fusion. If nothing survives (floors + filters), `hybrid_retrieve` returns `RetrievalOutcome(abstained=True, reason="insufficient evidence")` with **no documents**. This is the safety contract: the system would rather **say nothing** than ground an answer in weak evidence — the request-time graph (Story 3.5) turns this into a refusal instead of a hallucination.

## Where LangChain is / isn't
Fusion + rerank operate in **`langchain_core.Document`** space, the arms are **`IkipRetriever`** (LangChain `BaseRetriever`), and the reranker is a port a LangChain reranker can implement. But **tenant scoping + filters + citations stay in our SQL** — governance is structural, not delegated ([ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md)).

## Rules to remember
1. Fuse with **RRF** (rank-based) — don't add raw lexical + cosine scores.
2. `k=60` is the standard dampening; dedup by `chunk_id`; keep citations + add `rrf_score`.
3. Reranking is a **port**; `IdentityReranker` by default, cross-encoder later behind it.
4. Filters (version-awareness `is_current`, type, metadata) apply **in SQL on both arms**.
5. **Abstain** when nothing passes floors/filters — never ground on empty/weak evidence.
6. Fusion/rerank in Document space; tenant + citations stay structural in our SQL.

## Related
- Decisions: [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) · [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) · [ADR 0012](../../adr/0012-local-first-dev-cloud-models-only.md).
- Concepts: [retrieval](./retrieval.md) · [embeddings](./embeddings.md) · [rag-orchestration](./rag-orchestration.md) · [dedup-versioning](./dedup-versioning.md) (is_current).
- Next: LangGraph grounded-answer graph (Story 3.5) consumes `RetrievalOutcome` — cited generation or abstention; eval (3.6) tunes thresholds + reranker.
