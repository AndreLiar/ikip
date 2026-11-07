# MISSION-014 — Lexical & vector search (Epic 3, Story 3.3)

**Mode:** Guidé (FTS-config + LangChain-boundary decisions) → Autonome (impl) + knowledge transfer.
**Objective:** build the two retrieval arms — BM25/full-text (`tsvector`/GIN) and semantic (pgvector/HNSW) — both tenant-scoped and both returning the full citation chain, exposed to LangChain via a `BaseRetriever` adapter.
**Maps to:** Epic 3 / Story 3.3. Builds on Story 3.2 (embeddings); applies [ADR 0004](../../../adr/0004-hybrid-retrieval-on-postgres.md), [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Decisions
- **FTS config = `simple`** (user-chosen): language-neutral, code/ref-friendly, FR+EN; the vector arm covers meaning. See [decisions.md](./decisions.md) D1.
- **LangChain via `IkipRetriever(BaseRetriever)` over our SQL** (user-ratified option 1): reuse LangChain on the read path *behind* our tenant-scoped SQL; citations preserved in Document metadata. [decisions.md](./decisions.md) D2.

## Acceptance criteria
1. BM25/full-text over curated content via Postgres `tsvector`/GIN. — **[verified]** (generated `content_tsv` + GIN; `lexical_search`; pure SQL test + DB test)
2. Vector similarity via pgvector HNSW. — **[verified]** (HNSW `vector_cosine_ops` index; `vector_search` cosine; pure + DB test)
3. Both return document/version/page/section references. — **[verified]** (`SearchHit` citation chain; DB tests assert refs; `IkipRetriever` puts them in Document metadata — FR16)
4. Retrieval latency measured and logged. — **[verified]** (`_timed` context logs `arm`/`tenant`/`latency_ms`)

## Deliverables
- `ikip_common/db/retrieval.py` — `lexical_search`, `vector_search`, `SearchHit`, latency logging; statement builders for pure tests.
- `ikip_common/llm/retriever.py` — `IkipRetriever` (LangChain `BaseRetriever`) + `hit_to_document` (citations in metadata). **The LangChain boundary.**
- `ikip_common/db/models.py` — `chunk.content_tsv` (generated) + GIN index; `embedding` HNSW index.
- Migration `3a15a5ad99fe_add_fts_and_hnsw_indexes.py` (reversible; offline-verified both ways).
- Tests: `test_retrieval.py` (3 pure SQL-shape + 3 DB), `test_retriever_adapter.py` (3 pure + 1 DB; `importorskip langchain_core`).

## Concepts
Introduces [retrieval](../../concepts/retrieval.md) (lexical vs vector, tsvector/GIN, HNSW/cosine, BaseRetriever boundary). Reuses [embeddings](../../concepts/embeddings.md), [rag-orchestration](../../concepts/rag-orchestration.md), [multi-tenancy](../../concepts/multi-tenancy.md).
