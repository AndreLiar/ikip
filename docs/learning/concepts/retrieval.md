# Concept — Retrieval: lexical + vector (the two arms)

_Write-once concept note. First used by Story 3.3. Decisions: [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) (hybrid on Postgres), [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (LangChain behind ports). Follows [embeddings](./embeddings.md)._

## Why two arms
No single search method is enough:
- **Lexical** (keyword) matches **exact terms** — fault codes (`E42`), part numbers, model refs. It can't match synonyms or paraphrases.
- **Vector** (semantic) matches **meaning** — "won't start" ≈ "fails to spin up", across languages. It can miss an exact rare token.

IKIP runs **both** and fuses them (hybrid, Story 3.4). Story 3.3 builds the two arms separately; each returns the full citation chain (FR16).

## Lexical arm — Postgres full-text (`tsvector`/GIN)
- `to_tsvector(config, text)` turns text into a **`tsvector`** (normalized lexemes). We store it as a **generated, STORED column** on `chunk` (`content_tsv`), always kept in sync by Postgres — no app code to maintain.
- A **GIN index** over that column makes matching fast.
- A query becomes a **`tsquery`** via `websearch_to_tsquery(config, q)`; `content_tsv @@ tsquery` matches; **`ts_rank`** orders by relevance. `ts_rank` is a BM25-**family** lexical score but **not** Okapi BM25 — it lacks BM25's TF-saturation (`k1`) and document-length normalization (`b`). Vanilla Postgres/Neon ships `ts_rank`, not BM25; a true-BM25 upgrade (ParadeDB `pg_search`/VectorChord-bm25) is a documented future option ([ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md)).
- **Config = `simple`** (decision): no stemming, language-neutral → best for codes/refs and mixed FR/EN. The vector arm already covers meaning/synonyms, so lexical is the *exact-term* matcher. Per-language stemming is a post-MVP upgrade.

## Vector arm — pgvector ANN (HNSW, cosine)
- Each chunk has an embedding (`vector(512)`, [embeddings](./embeddings.md)). Search embeds the **query** with the same model, then finds the **nearest** chunk vectors.
- Distance metric: **cosine** (`<=>` in pgvector). Score = `1 - distance` (higher is better).
- Index: **HNSW** (Hierarchical Navigable Small World) — an **approximate** nearest-neighbour graph: near-exact results, far faster than scanning every vector. Only vectors of the **same `model_version`** are comparable, so search filters on it.

## Exact vs approximate (why HNSW)
A brute-force k-NN scans every vector — accurate but O(n) per query. **HNSW** trades a tiny bit of recall for large speed-ups by navigating a layered proximity graph. At IKIP's scale this keeps vector search within the latency budget (NFR1); recall is tunable via index params.

## Tenant isolation + citations (non-negotiable)
Both arms query through **tenant-scoped** SQL (`WHERE tenant_id = …`, NFR10) and **join** chunk → section → document_version → document so every hit resolves to document/version/page/section (FR16). This is **our SQL**, not a generic retriever — the governance stays structural ([ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md)).

## Why one datastore (ts_rank over true BM25, pgvector over Qdrant)
A recurring question: the lexical arm is `ts_rank`, not true BM25 — and true BM25 ranks keyword queries better. Why not use it? Because true BM25 lives in a **search engine** (Elasticsearch/OpenSearch/Lucene), i.e. a **second datastore** next to Postgres. The core IKIP principle ([ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md)) is **keep lexical + vector + the citation chain + tenant isolation all in one datastore (Postgres)** and only split when a measured limit forces it.

A **datastore** = a system that holds data and answers queries about it. Every *extra* one triples your failure modes — the classic **run / sync / secure**:
- **Run:** a second system to deploy, patch, monitor, pay for, and keep alive — one more thing that breaks.
- **Sync:** the search engine needs its **own copy** of the text. Every add/edit/version/delete must land in **both** systems and keep them agreeing. Drift = search returns documents that don't exist, or misses ones that do. (The vector↔chunk consistency we already manage is this same problem, for *every* document.)
- **Secure:** IKIP is **multi-tenant** — isolation (NFR10) must then be enforced **twice**, identically, and proven in **both** stores (mirrored isolation tests). Double the surface for a cross-tenant leak, in a system whose whole value is trustworthiness.

Keeping all four in Postgres means **one SQL query** does keyword + semantic + tenant filter + citation fetch **atomically and consistently** — which is what makes the grounding guarantee *provable*, not just a performance nicety. A slightly weaker `ts_rank` is a fair price for that.

**The honest discipline (not dogma):** the same spine runs through `pgvector` over Qdrant ([ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md)) — the specialist tool is better at its one job, but the second-datastore tax outweighs the gain **until the data says otherwise**. Qdrant only entered the roadmap when free-Postgres storage ran out (**forced**, not chosen); a true-BM25 upgrade is likewise gated on *measuring* the lexical arm as the bottleneck first — and MISSION-044 found retrieval is already robust via the vector arm + RRF, so that upgrade must be A/B'd, not assumed. **Earn the second datastore with evidence.**

## Where LangChain plugs in
`IkipRetriever` (a `langchain_core` `BaseRetriever`) wraps our `lexical_search`/`vector_search` and maps each hit to a LangChain `Document` with the **citation in `metadata`**. So rerankers, `EnsembleRetriever` (Story 3.4) and LangGraph (3.5) compose **on top of** our search — LangChain lives in the adapter, the domain SQL never imports it.

## Rules to remember
1. Lexical = exact terms (`tsvector`/GIN, `simple`); vector = meaning (pgvector/HNSW, cosine). Use both.
2. `content_tsv` is a **generated STORED** column — Postgres keeps it in sync; never set it from Python.
3. Vector search only compares the **same `model_version`**; filter on it.
4. HNSW = approximate but fast; fine for ANN at MVP scale.
5. Both arms stay **tenant-scoped** and return the **citation chain** (NFR10, FR16).
6. LangChain enters only via the `IkipRetriever` adapter; latency is measured + logged (AC4).
7. **One datastore until forced:** lexical + vector + citations + tenant all in Postgres. A second store (Elasticsearch for BM25, Qdrant for vectors) costs **run/sync/secure** — earn it with measured evidence, not intuition.

## Related
- Decisions: [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) (hybrid on Postgres + the `ts_rank`-not-BM25 note) · [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) · [ADR 0001](../../adr/0001-vector-store-pgvector.md) · [ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md) (the one-datastore principle applied to vectors → Qdrant when forced).
- Concepts: [embeddings](./embeddings.md) · [rag-orchestration](./rag-orchestration.md) · [multi-tenancy](./multi-tenancy.md) · [chunking](./chunking.md).
- Next: hybrid fusion + reranking + filters (Story 3.4); LangGraph grounded answer (3.5).
