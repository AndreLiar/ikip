# Epic 3 — Retrieval & RAG Engineering

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Turn curated documents into a measurable retrieval + grounded-answer service: structure-aware chunking, versioned embeddings, BM25 + vector + hybrid retrieval with reranking and equipment/version filters, and a LangGraph workflow that synthesizes cited answers and abstains when evidence is missing.

**Related requirements:** FR9–FR18 · NFR1, NFR6, NFR7, NFR8, NFR9, NFR18 · depends on Epic 2 (curated documents)

---

## Story 3.1 Structure-Aware & Semantic Chunking
As an engineer, I want documents chunked by structure and semantics with section/page metadata, so that retrieval units are coherent and citable.
**Acceptance Criteria:**
1. `section` and `chunk` records capture hierarchy, heading, page range and metadata.
2. Chunking respects document structure (sections/headings) and semantic boundaries.
3. Each chunk retains a resolvable back-reference to document, version, page and section.
4. Tests validate chunk boundaries and metadata integrity.

## Story 3.2 Embedding Generation & Version Management
As an engineer, I want versioned embeddings via a pluggable client, so that we can re-embed and compare models safely.
**Acceptance Criteria:**
1. `LLMClient`/embedding adapter generates embeddings via Azure OpenAI (pluggable).
2. `embedding` records store chunk ID, model version and vector in pgvector (on Neon).
3. Embedding-model version is tracked; re-embedding does not destroy prior vectors needed for comparison.
4. **Embedding dimension is chosen mindful of Neon storage** (e.g., 256–512 dims and/or `halfvec`) so the vector index fits the tier — see [ADR 0015](../adr/0015-neon-serverless-postgres.md).
5. Tests cover embedding generation and version tagging.

## Story 3.3 Lexical & Vector Search
As a user, I want both keyword and semantic search, so that I can find content by terms or meaning.
**Acceptance Criteria:**
1. BM25/full-text search over curated content via Postgres (Neon) `tsvector`/GIN.
2. Vector similarity search via pgvector (HNSW).
3. Both return results with document/version/page/section references.
4. Retrieval latency is measured and logged.

## Story 3.4 Hybrid Retrieval, Reranking & Filters
As a user, I want hybrid retrieval with reranking and equipment/version filters, so that results are precise and applicable.
**Acceptance Criteria:**
1. Lexical + vector results are fused into a hybrid result set.
2. A reranking step orders results by relevance.
3. Metadata filters support equipment model/revision and version-awareness (applicable vs. obsolete).
4. Abstention path returns "insufficient evidence" when no result passes thresholds.

## Story 3.5 LangGraph Grounded-Answer Service with Citations
As a technician, I want a grounded answer with precise citations and surfaced warnings, so that I can trust and verify it.
**Acceptance Criteria:**
1. LangGraph workflow: query analysis → equipment identification → retrieval → rerank → sufficiency check → cited generation.
2. Answers are grounded only in retrieved evidence; each claim carries a citation to document/version/page/section.
3. Safety warnings and uncertainty present in evidence are surfaced.
4. The workflow abstains rather than inventing content when evidence is insufficient.
5. The service never presents output as certified manufacturer instruction.

## Story 3.6 Retrieval & Answer Quality Baseline
As an engineer, I want an initial gold dataset and retrieval/answer metrics, so that quality is measurable before building the UI.
**Acceptance Criteria:**
1. `evaluation_case` records capture question, relevant evidence and expected behavior.
2. Recall@K and citation-resolution are computed over the gold set.
3. A groundedness check flags unsupported claims.
4. Results are reproducible via a documented command and stored for regression comparison.

## Story 3.7 Caching (deterministic + exact-match answer)
As an engineer, I want layered caching behind a `Cache` port, so that cost and latency drop without compromising tenant isolation or version-awareness ([ADR 0009](../adr/0009-caching-strategy.md)).
**Acceptance Criteria:**
1. Embedding reuse: embeddings are not regenerated when `(chunk_id, model_version)` already exists (Postgres-backed); re-index/backfill reuses them.
2. Query-embedding cache and an exact-match answer cache are implemented behind a `Cache` port (Redis — Cloud or Docker).
3. Answer/retrieval cache keys are tenant-partitioned and encode equipment model + revision + current document-version set; a cache hit never crosses tenants and never serves a superseded version.
4. Cache entries are invalidated when a new/superseded `document_version` is published by ingestion.
5. A cache hit does not change the abstention decision vs. a cold run; security tests cover cross-tenant cache isolation (extends Story 6.2).
6. Fuzzy/semantic "similar question" caching is explicitly **out of scope** here (deferred per [ADR 0009](../adr/0009-caching-strategy.md)).
