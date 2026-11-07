# MISSION-014 — Decisions

## D1 — Full-text search config = `simple`
**Problem:** Postgres FTS needs a text-search config; it governs stemming/stopwords and thus lexical behaviour over mixed FR/EN industrial content full of codes/refs.
**Choice:** `simple` (no stemming, language-neutral).
**Why here:** the **vector arm already handles meaning/synonyms/multilingual**, so the lexical arm should be the **exact-term matcher** — exactly where `simple` shines (fault codes `E42`, part numbers) without mis-stemming across languages.
**Alternative:** `english`/`french` — language-specific stemming; better if the corpus were single-language, but wrong-language stemming hurts mixed content. Rejected for MVP.
**Trade-off:** no stemming → "pumps" ≠ "pump" on the lexical side; acceptable because the vector arm bridges that.
**Prefer the alternative when:** the corpus is confirmed single-language and stemming recall matters more than code precision. Future: per-document language detection → per-language tsvector.

## D2 — LangChain on the read path via `IkipRetriever(BaseRetriever)` over our SQL
**Problem:** reuse LangChain (user requirement) without delegating tenant isolation + citations to it (ADR 0021).
**Choice:** keep `lexical_search`/`vector_search` as our tenant-scoped SQL; wrap them in a `langchain_core` `BaseRetriever` adapter that maps each `SearchHit` to a `Document` with the citation in `metadata`.
**Why here:** LangChain components (rerankers, `EnsembleRetriever`, LangGraph) compose on top via a standard retriever interface, while tenant scoping (`WHERE tenant_id`) and the citation joins stay **structural** in our SQL — not forgettable metadata filters.
**Alternative:** `langchain_postgres.PGVectorStore` as the vector arm (existing-table mode). Kept as a to-evaluate option (ADR 0021); not adopted now to avoid mapping citations into its metadata model before it's proven.
**Trade-off:** we own the small SQL + the adapter; in exchange, governance is structural and the domain never imports LangChain.

## D3 — Generated STORED tsvector column (not computed-on-read, not app-maintained)
**Choice:** `content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED` + GIN index.
**Why:** Postgres keeps it in sync with `content` automatically (no trigger, no app code), and STORED + GIN gives fast matching. A computed-on-read expression index would re-tokenise per query; app-maintained columns drift.
**Alternative:** an expression index on `to_tsvector(...)` without a column — valid, but a named column is clearer to query/rank and inspect. Minor.

## D4 — HNSW + cosine for the vector index
**Choice:** HNSW index with `vector_cosine_ops`; score = `1 - cosine_distance`.
**Why:** cosine suits text-embedding-3 vectors; HNSW gives fast approximate NN within NFR1 latency. AC2 explicitly asks for HNSW.
**Alternative:** IVFFlat (needs training/lists tuning, lower memory) — revisit if index build/memory becomes a constraint.
