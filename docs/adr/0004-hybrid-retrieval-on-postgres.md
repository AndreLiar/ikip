# 0004. Hybrid retrieval on PostgreSQL (full-text + pgvector) before managed/dedicated search

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** FR11, FR12, FR13, FR14 · NFR1, NFR6 · Stories 3.3, 3.4, 3.6 · `../architecture.md` (Tech Stack, Core Workflows) · builds on [ADR 0001](./0001-vector-store-pgvector.md)

## Context
Finding the correct technical information requires more than vector similarity. Technicians search by **exact terms** (fault codes, part numbers, model identifiers) *and* by **meaning**, with results filtered by equipment model/revision and version-awareness and constrained by tenant/document ACL (FR11–FR14). The lexical half of this could be served by Postgres full-text search or by a dedicated search engine (Elasticsearch/OpenSearch) or managed search (Azure AI Search). ADR 0001 already selected pgvector for the vector half; this ADR decides the **overall retrieval strategy and the lexical engine**.

## Decision
Implement **hybrid retrieval inside PostgreSQL**: lexical via Postgres full-text (`tsvector`/GIN, BM25-style ranking) + vector via pgvector, their result sets **fused and then reranked**, with metadata filters (equipment model/revision, version-awareness) and ACL applied in the same query. Add **no dedicated search engine or managed search service at MVP**. Reranking is a distinct step after fusion. Retrieval is reached only through the `VectorStore`/retrieval interfaces so the engine can change later.

## Consequences
**Positive**
- Lexical + vector + filters + ACL resolve in **one query over one system** — no fan-out, no cross-store re-join, consistent tenant isolation (ties to [ADR 0001](./0001-vector-store-pgvector.md), [ADR 0003](./0003-local-first-ports-and-adapters.md)).
- Nothing extra to run locally (NFR17) and nothing extra to pay for / operate on Azure.
- Quality is measurable from day one (Recall@K, citation resolution — Story 3.6) without standing up another service.

**Negative / risks**
- Postgres full-text is less feature-rich than Elasticsearch/OpenSearch (no advanced analyzers, custom scoring plugins, or large-scale sharded lexical search) and than Azure AI Search's built-in semantic ranker + native hybrid fusion.
- Fusion and reranking logic is ours to build and tune (vs. a managed hybrid pipeline).
- Very large corpora or high lexical QPS may eventually outgrow Postgres full-text.

**Neutral**
- A reranking model/step is required regardless of which lexical/vector engines are used.

## Alternatives Considered
- **Elasticsearch / OpenSearch for lexical (+ separate vector):** powerful analyzers and scale, but adds a service to run locally and in prod, splits ACL/tenant enforcement and consistency across systems, and complicates the single-query model. Rejected at MVP.
- **Azure AI Search (managed hybrid + semantic ranker):** removes fusion/rerank build effort, but is a paid managed service, still needs our ACL/tenant layer, and has no true local equivalent — breaking local-first parity ([ADR 0003](./0003-local-first-ports-and-adapters.md)). Deferred.
- **Vector-only retrieval (drop lexical):** fails exact-term needs (fault codes, part numbers) and hurts Recall on identifier queries (FR11). Rejected.

## Revisit When
- Recall@K / ranking quality plateaus below targets (NFR6: Recall@5 ≥ 90%) and analysis attributes it to lexical/fusion limits, **or**
- p95 retrieval latency breaches NFR1 (< 1.5 s) under load attributable to Postgres full-text, **or**
- Corpus/QPS scale outgrows Postgres full-text (see also [ADR 0001](./0001-vector-store-pgvector.md) vector triggers), **or**
- A managed semantic ranker (Azure AI Search) demonstrably lifts quality enough to justify its cost and the loss of local parity.
