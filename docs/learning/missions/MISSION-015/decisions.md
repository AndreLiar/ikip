# MISSION-015 — Decisions

## D1 — RRF fusion in-house + pluggable Reranker port (IdentityReranker default)
**Problem:** AC1 (fuse) + AC2 (rerank) need a fusion method and a reranking step. Lexical `ts_rank` and vector cosine scores are on incomparable scales. A true cross-encoder reranker is the canonical rerank but needs either a heavy local model (sentence-transformers/torch — against ADR 0012) or a new provider (Cohere + key).
**Choice:** fuse with **Reciprocal Rank Fusion (RRF)** implemented in-house; make reranking a **`Reranker` port** with a no-op **`IdentityReranker`** default.
**Why here:** RRF is rank-based → no score normalization, robust, ~15 lines. It is exactly what LangChain's `EnsembleRetriever` computes, but that moved to a legacy compat package in LangChain 1.x; implementing it ourselves keeps citations + thresholds under our control (ADR 0021). The port leaves a clean seam for a real cross-encoder later without touching callers or adding a dependency now.
**Alternatives:**
- *Weighted score fusion* (normalize + weight lexical vs vector): needs calibration per corpus, brittle. Rejected.
- *Cross-encoder reranker now* (local or Cohere): best quality, but heavy dep / new vendor at MVP before eval proves it's needed. Deferred (revisit after Story 3.6).
- *Use EnsembleRetriever from a compat package*: drags a legacy package for 15 lines; less control of citation dedup. Rejected.
**Prefer the alternative when:** eval (Story 3.6) shows RRF ordering is insufficient → drop a cross-encoder behind the `Reranker` port.

## D2 — Filters applied in SQL on both arms (not post-filtering)
**Choice:** `RetrievalFilters` (`current_only`→`is_current`, `document_type`→`Document.type`, `metadata`→JSONB `@>`) applied inside `_lexical_stmt`/`_vector_stmt`.
**Why:** filtering in the DB keeps `limit`/ranking correct (you rank the *eligible* rows, not a post-filtered slice) and keeps version-awareness (applicable vs obsolete, NFR15/FR14) structural. Post-filtering in Python would silently shrink result sets below `limit`.
**Note:** equipment model/revision uses lightweight JSONB containment on `chunk_metadata` at MVP; a dedicated equipment table/entity is a planned extension.

## D3 — Abstention via per-arm score floors
**Choice:** each arm takes `min_score`; hits below are dropped before fusion; empty fused+reranked set → `RetrievalOutcome(abstained=True, reason="insufficient evidence")`.
**Why:** the safety contract (AC4) — the system must be able to say "insufficient evidence" rather than fuse weak noise. Thresholds are caller-provided so Story 3.6 can tune them against eval, and Story 3.5 turns abstention into a refusal.
