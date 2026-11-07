# 0021. Framework boundary: reuse LangChain/LangGraph components *behind* our business ports (domain keeps schema, citations, tenant isolation, versioning)

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR13–FR16 · NFR1, NFR10 · Stories 3.2, 3.3, 3.4, 3.5 · refines [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md); builds on [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0004](./0004-hybrid-retrieval-on-postgres.md), [ADR 0001](./0001-vector-store-pgvector.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0020](./0020-embedding-model-text-embedding-3-small.md)

## Context
[ADR 0002](./0002-dual-orchestration-dagster-langgraph.md) set the dual-orchestration split (Dagster builds the knowledge base; LangGraph + LangChain orchestrate the request-time RAG workflow). As Epic 3 is implemented, a sharper question arises: **LangChain can also provide embeddings wrappers, vector stores (incl. PGVector), retrievers, hybrid search and rerankers** — so should Stories 3.2 (embeddings), 3.3 (lexical+vector search) and 3.4 (hybrid + rerank + filters) be built *with LangChain*, or with direct SQL/SDK? Observed in the code so far: embeddings (3.2) use the `openai` SDK directly, not LangChain. This ADR makes that boundary explicit so it is a decision, not an accident.

Forces specific to IKIP:
- Retrieval is **hybrid-and-relational**: vector + full-text (`tsvector`/GIN) + equipment/version filters + **tenant ACL**, ideally in one SQL query ([ADR 0004](./0004-hybrid-retrieval-on-postgres.md), [ADR 0001](./0001-vector-store-pgvector.md)).
- **Tenant isolation is a hard security requirement (NFR10)** — every read goes through the tenant-scoped repository (`WHERE tenant_id = …`).
- We must control the embedding **dimension (Matryoshka 512)** and **`model_version`** versioning ([ADR 0020](./0020-embedding-model-text-embedding-3-small.md), FR14).
- Infra must stay swappable behind **our own ports** ([ADR 0003](./0003-local-first-ports-and-adapters.md)).

## Decision
**Maximise reuse of mature LangChain/LangGraph components, but keep them *behind* our business ports** so the domain never depends on the framework and never delegates business invariants, security or data governance to it.

Concretely:
- **Reuse LangChain bricks:** `AzureOpenAIEmbeddings` (supports the `dimensions=512` Matryoshka param — [ADR 0020](./0020-embedding-model-text-embedding-3-small.md)), relevant retrieval/reranking components (e.g. `EnsembleRetriever`, cross-encoder/Cohere rerankers), **LCEL**, and **LangGraph** for the request-time graph (Story 3.5).
- **The domain keeps what it must own:** our relational business schema (`document_version`/`section`/`chunk`/`embedding`), **provenance/citation IDs** (FR16), **embedding `model_version`** (additive re-embedding, FR14), and the **tenant-scoped repository**.
- **Expose business retrieval as a `BaseRetriever`-compatible adapter** so LangChain components (rerankers, ensembles) and LangGraph plug in *on top of* our search — **without the domain importing LangChain**. LangChain lives inside adapters (e.g. the `EmbeddingClient` adapter wraps `AzureOpenAIEmbeddings`), not in the core.
- **Enforce tenant isolation at the repository layer** (`WHERE tenant_id = …`), ideally with **PostgreSQL RLS as defense-in-depth** (Story 6.2). No generic retriever may issue an un-scoped query.
- **Preserve citation references through fusion, filtering and reranking** — a reranked/ fused result must still resolve `chunk → section → document_version → page` (FR16).
- **Keep `langchain_postgres.PGVectorStore` as a technical alternative to evaluate**, not reject: its current version can operate over **existing tables**, so it may later back our `VectorStore` port. It is not dismissed on the basis of the legacy `PGVector` schema.

Rule of thumb: **reuse the framework's components freely; never hand it the business invariants, security, or data governance.**

## Acceptance criteria (how we prove the boundary holds)
1. **Cross-tenant isolation tests** — a tenant can never retrieve another tenant's vectors/chunks (repository scoping; RLS when added).
2. **Citation integrity** — every retrieved/reranked result resolves back to document/version/page/section (FR16), after fusion + filtering + rerank.
3. **Model-version coexistence** — vectors from two `model_version`s coexist; re-embedding is additive, never destructive (FR14).
4. **Ranking regression tests** — retrieval ordering is covered so a reranker/fusion change is caught.
5. **Performance benchmark** — retrieval latency measured against NFR1 (p95 < 1.5 s).

## Consequences
**Positive**
- **Reuse of mature components:** `AzureOpenAIEmbeddings`, rerankers, ensembles, LCEL, LangGraph — less code to write/maintain, and demonstrable LangChain competence (thesis value).
- **Tenant isolation stays enforceable (NFR10):** reads go through the scoped repository (+ RLS later); the `BaseRetriever` adapter injects tenant scope, so no LangChain component emits an un-scoped query.
- **Citations + versioning preserved (FR16, FR14):** embeddings live in our relational schema with provenance IDs and `model_version`; fusion/rerank operate on results that still resolve back to document/version/page/section.
- **Ports keep infra swappable** ([ADR 0003](./0003-local-first-ports-and-adapters.md)): LangChain lives inside adapters; the domain never imports it, so a component (even `PGVectorStore`) can be swapped behind a port.
- **Transparent cost/latency** per call for Langfuse ([ADR 0013](./0013-llmops-observability-otel-langfuse.md)).

**Negative / risks**
- **Adapter/boundary code** to wrap our retrieval as a `BaseRetriever` and keep citations through rerank. Mitigated: small, and covered by the acceptance tests above.
- **Version/API churn** in LangChain. Mitigated: contained to adapters behind ports; pin versions.
- **Isolation now depends on the adapter correctly injecting tenant scope** (vs a pure structural `WHERE`). Mitigated: repository scoping remains the source of truth, RLS as defense-in-depth (Story 6.2), explicit cross-tenant tests.

**Neutral**
- `PGVectorStore` vs our own `Embedding` table remains an open, test-driven choice behind the `VectorStore` port (see Alternatives).

## Alternatives Considered
- **Full LangChain incl. its vector store as the system of record (its own schema):** maximal reuse, but makes the domain depend on LangChain for storage and forces citations/tenant/versioning into `metadata` JSON filters (NFR10 less robust, FR16 to rebuild). Rejected as the *default*; the newer `PGVectorStore` (operates over existing tables) is kept as a behind-the-port option to evaluate, not rejected on the legacy `PGVector` schema.
- **No LangChain on the read path at all (pure SQL/SDK):** maximal control, but reinvents mature bricks (rerankers, ensembles, embeddings wrapper) for no benefit and forgoes LangChain competence demonstration. Rejected — this was the earlier, too-absolutist framing corrected by this decision.
- **Avoid LangGraph too, hand-roll request-time in plain Python:** the grounded-answer graph (branching, retries, abstention, future tool use) is exactly what LangGraph is for; hand-rolling re-implements a state machine poorly. Rejected for 3.5.
- **A dedicated managed search / retriever service:** rejected earlier ([ADR 0001](./0001-vector-store-pgvector.md), [ADR 0004](./0004-hybrid-retrieval-on-postgres.md)) to keep the single-store hybrid-relational design.

## Revisit When
- **`PGVectorStore` (existing-table mode)** is shown by the acceptance tests to honour tenant scoping + citations + version coexistence behind our `VectorStore` port → adopt it as the storage adapter.
- A LangChain component on the read path is found to **leak across tenants or drop citations** in testing → pull that responsibility back behind the repository and keep only its non-governance parts.
- Request-time orchestration outgrows LangGraph (e.g. needs a different agent runtime) → reopen [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md).
