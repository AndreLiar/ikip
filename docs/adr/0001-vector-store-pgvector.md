# 0001. Use PostgreSQL + pgvector as the initial vector store

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** FR11, FR12, FR13, FR14, FR21 · NFR10, NFR12, NFR15, NFR17 · Stories 2.5, 2.6, 3.2, 3.3, 3.4, 6.2, 6.5 · `../architecture.md` (Tech Stack, Data Sources, Components)

## Context
IKIP needs a store for chunk embeddings supporting hybrid retrieval. Candidate approaches: (a) **PostgreSQL + pgvector** alongside the relational metadata, or (b) a **dedicated vector database** (e.g., Qdrant) or **managed search** (e.g., Azure AI Search) as a separate system.

Forces specific to IKIP:
- Retrieval is **hybrid and relational**, not pure vector: BM25/full-text **+** vector similarity **+** equipment model/revision filters **+** version-awareness (applicable vs. obsolete) **+** tenant/document ACL, combined into one ranked result (FR11–FR14).
- Security requires **authorize-before-retrieve**, tenant isolation and object-level permissions on chunks, with *zero cross-tenant disclosure* as a CI gate (FR21, NFR10, Story 6.2).
- Versioning, consistent cross-store deletion and lineage are transactional needs (Stories 2.5, 2.6, 6.5; NFR15).
- The platform must run fully on a 16 GB laptop (NFR17) and keep local↔Azure parity with minimal managed services and cost.
- Corpus scale: ~100–500 documents at MVP, ~10k later → low-millions of vectors at most.

## Decision
Use **PostgreSQL 16 + pgvector** as the vector store for the initial platform, co-located with the relational metadata, with vector similarity indexed (HNSW) and lexical retrieval via Postgres full-text. Access the vector store exclusively through a **`VectorStore` interface** (ports & adapters, NFR12) so the implementation can be swapped without touching business logic.

## Consequences
**Positive**
- Hybrid retrieval + metadata filters + ACL execute in a **single query** joining `chunk → embedding → document_version → equipment → tenant` — no cross-system fan-out or re-join.
- **One enforcement point** for tenant isolation / object-level permissions; one system to security-test (Story 6.2).
- Version supersession, consistent multi-store deletion (Story 6.5) and lineage get Postgres transactions, foreign keys and cascades — no dual-write/sync problem.
- **Zero extra service locally** (runs in the Postgres container already required) and **natively supported on Azure PostgreSQL Flexible Server** — no extra managed service, bill, Terraform module, backup/DR target or monitoring surface.
- **Local↔prod retrieval parity** preserved (same engine both places).

**Negative / risks**
- pgvector lacks advanced ANN features (multi-vector/ColBERT late interaction, named vectors, native sparse+dense fusion, aggressive quantization).
- At very large scale or high QPS, vector queries can compete with transactional load and ANN latency/recall tuning is more limited than a specialized engine.

**Neutral**
- Reranking is a separate step regardless of store choice.

## Alternatives Considered
- **Qdrant (dedicated vector DB):** stronger ANN features and scaling, but requires duplicating relational metadata for filtering (or a two-phase fetch + re-join), a second ACL/tenant-isolation surface, and dual-write consistency for versioning/deletion. Not justified at MVP scale.
- **Azure AI Search:** managed semantic ranker and built-in hybrid fusion, but adds a paid managed service, still needs our ACL/tenant layer, and has **no true local equivalent** — breaking the local-first dev story and local↔prod parity. Explicitly deferred.
- **Separate embeddings DB (any):** rejected for MVP because it turns transactional operations (versioning, deletion, lineage) into distributed-consistency problems (conflicts with NFR15).
- **Redis as a vector DB (Redis Query Engine / RediSearch):** Redis *can* do vector KNN + hybrid filtering, so it is a candidate `VectorStore` adapter. Rejected for the MVP vector store because (a) it requires the heavier **Redis Query Engine** tier (Redis Stack/Enterprise/Azure Managed Redis Enterprise), not the lightweight Redis we already run for queue/cache; (b) it is **in-memory**, so holding the embedding index as a durable system-of-record means paying for large RAM and treating a cache-shaped store as primary; and (c) it still splits embeddings from the relational metadata, re-introducing the cross-store join, second ACL surface and sync problems above. Redis stays in its fit-for-purpose roles — job queue ([ADR 0003](./0003-local-first-ports-and-adapters.md)) and cache ([ADR 0009](./0009-caching-strategy.md)) — and remains a candidate vector adapter if the triggers below fire.

## Revisit When
Reopen this decision (and introduce a `VectorStore` adapter for Qdrant, Azure AI Search or Redis Query Engine) when **any** of:
- Vector count reaches **tens-to-hundreds of millions**, or measured vector QPS degrades p95 retrieval latency past NFR1 (< 1.5 s).
- A feature requires **ColBERT/multi-vector, named vectors, heavy quantization, or native sparse+dense fusion**.
- Vector workload measurably contends with transactional Postgres load.
- A product requirement justifies paying for a managed semantic ranker / skillsets (Azure AI Search).

Because retrieval sits behind the `VectorStore` interface, switching is a planned adapter swap, not a rewrite.
