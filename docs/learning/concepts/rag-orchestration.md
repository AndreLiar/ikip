# Concept — RAG orchestration & the framework boundary (Dagster · LangGraph · direct SQL/SDK)

_Write-once concept note. Decisions: [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md) (dual orchestration), [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (framework boundary). First referenced around Story 3.2–3.5._

## Two orchestrations, two different jobs
A production RAG system has **two** pipelines that run at different times and are built with different tools:

| | **Build-time** — fill the knowledge base | **Request-time** — answer a question |
|---|---|---|
| When | offline, batch / on new documents | synchronously, per user query |
| Steps | ingest → OCR → clean → dedup → version → **chunk → embed → index** | analyse query → retrieve → rerank → check sufficiency → **cited answer** → abstain |
| Tool | **Dagster** (data assets, lineage, retries) | **LangGraph** (+ LangChain components) |
| IKIP stories | Epics 1–2, Stories 3.1–3.2 | Story 3.5 |

This is why, building story by story, you reach embeddings (3.2) and retrieval (3.3/3.4) **before any LangGraph appears**: those are the build-time + data-plane halves. LangGraph enters at **3.5**, the request-time answer graph. It is sequencing, not an omission.

## Why LangGraph for request-time (and not a pile of if/else)
The grounded-answer flow is a **stateful graph with branches**: retrieve → *is the evidence sufficient?* → (yes) generate a cited answer / (no) **abstain or re-retrieve**; plus retries and, later, tool calls. LangGraph models this as nodes + conditional edges + shared state — exactly the orchestration a hand-rolled control flow would re-implement badly. That is where the framework earns its place.

## How LangChain is used on the read path (3.2–3.4): behind our ports
We **do** reuse LangChain's mature bricks — but *behind* our business ports, never as the system of record ([ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md)):

- **Reuse:** `AzureOpenAIEmbeddings` (it honours `dimensions=512` — Matryoshka, [ADR 0020](../../adr/0020-embedding-model-text-embedding-3-small.md)), rerankers, `EnsembleRetriever`, LCEL, and LangGraph (3.5).
- **Domain keeps:** our relational schema (`document_version`/`section`/`chunk`/`embedding`), **citation IDs** (FR16), **`model_version`** (FR14), and the **tenant-scoped repository**.
- **Adapter, not dependency:** the `EmbeddingClient` adapter *wraps* `AzureOpenAIEmbeddings`; our retrieval is exposed as a `BaseRetriever`-compatible adapter so LangChain components plug in **on top of** our search — the domain never imports LangChain.

The one real trap it avoids: LangChain's **legacy `PGVector`** store brings its *own* schema (`langchain_pg_embedding`), divorcing vectors from our chunk→section→version chain (breaks citations, FR16) and turning tenant isolation into a forgettable JSON filter (NFR10). So vectors stay in **our** `Embedding` table. (The newer `langchain_postgres.PGVectorStore`, which can use existing tables, is kept as a behind-the-port option to evaluate — not rejected.)

## The boundary (one line to remember)
> **Reuse the framework's components freely; never hand it the business invariants, security, or data governance.** LangChain lives *inside* adapters; the domain owns the schema, citations, tenant isolation and versioning.

## Rules to remember
1. Build-time = Dagster; request-time = LangGraph. Different pipelines, different tools ([ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md)).
2. Reuse LangChain bricks on the read path, but **behind our ports** — the domain never imports LangChain ([ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md)).
3. All reads go through the **tenant-scoped repository** (+ RLS later) — never an un-scoped retriever (NFR10).
4. Vectors live in **our** `Embedding` table with provenance IDs + `model_version`; citations survive fusion/filter/rerank (FR16).
5. LangGraph shows up at **Story 3.5** for the cited-answer / abstention graph.

## Related
- Decisions: [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md) · [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) · [ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md) · [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md).
- Concepts: [why-rag](./why-rag.md) · [embeddings](./embeddings.md) · [dagster-orchestration](./dagster-orchestration.md) · [multi-tenancy](./multi-tenancy.md).
