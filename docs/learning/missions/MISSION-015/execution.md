# MISSION-015 — Execution log

Evidence labels: `[verified]` run with output · `[untested]`. Secrets redacted.

## Step 0 — EnsembleRetriever availability — [verified]
Intended to reuse LangChain's `EnsembleRetriever` for RRF. Probing the installed env:
```
langchain 1.4.9 installed, but `langchain.retrievers` is gone in 1.x;
langchain_classic not resolvable; EnsembleRetriever not in langchain_core.
```
Decision: implement RRF in-house (~15 lines; identical algorithm) and keep `langchain`
in the group for **langgraph** (Story 3.5). Dep comment updated to say so.

## Step 1 — Filters + floors in the data-plane — [verified]
`db/retrieval.py`: `RetrievalFilters` (current_only/document_type/metadata) + `_apply_filters`
(adds `is_current IS true`, `Document.type == …`, `chunk_metadata @> …`); `min_score`
floor (`_floor`). Both arms (`_lexical_stmt`/`_vector_stmt`) take `filters`; public
functions take `filters` + `min_score`. `IkipRetriever` gains `filters`/`min_score` and
passes them through.

## Step 2 — Hybrid module — [verified]
`llm/hybrid.py`: `reciprocal_rank_fusion` (RRF, k=60, dedup by chunk_id, adds rrf_score),
`Reranker` Protocol + `IdentityReranker`, `RetrievalOutcome`, `hybrid_retrieve`
(compose both `IkipRetriever` arms → RRF → rerank → abstain). Operates in
`langchain_core.Document` space; citations preserved in metadata.

## Step 3 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_retrieval.py packages/common/tests/test_hybrid.py \
              packages/common/tests/test_retriever_adapter.py -q
# 12 passed, 6 skipped (DB)
uv run pytest packages/common/tests -q        # 33 passed, 27 skipped
uv run ruff check packages/common             # OK (after --fix import order)
uv run ruff format --check packages/common    # OK
```
- Pure: RRF (doc in both lists ranks first; union+dedupe; rrf_score; empty lists),
  IdentityReranker (passthrough + top_k), RetrievalOutcome; filter SQL shape
  (`is_current IS true` present/absent, `document.type`, JSONB `@>`).
- DB-gated (CI ephemeral Neon branch): `hybrid_retrieve` fuses both arms with citations
  + rrf_score; abstains ("insufficient evidence") under impossible floors.

**Pitfalls:**
- Asserting `"is_current"` in compiled SQL was ambiguous (it's also a SELECTed column) →
  assert on the WHERE predicate text `"is_current is true"`.
- ruff import-order (I001) on `langchain_core` vs `ikip_common` imports after
  `importorskip` → `ruff --fix` reordered.

No migration: filters use existing columns (`is_current`, `type`, `chunk_metadata`).

**Local DB caveat:** DB tests run in CI (ephemeral Neon branch); not executed locally
(no Docker/Neon branch here).
