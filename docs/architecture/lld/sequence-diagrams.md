# LLD — Sequence Diagrams

_Call-level flows for the two core workflows, below the topology diagrams in [`../img/`](../img). Design artifact; actual calls finalize per story. Complements [core-workflows.md](../core-workflows.md)._

## 1. Ingestion (Dagster, batch) — one document, raw→indexed

```mermaid
sequenceDiagram
    autonumber
    participant SRC as Source connector
    participant DAG as Dagster (assets)
    participant OBJ as ObjectStorage
    participant PROC as document-processing
    participant IDX as indexing
    participant LLM as LLMClient (embeddings)
    participant PG as PostgreSQL + pgvector

    SRC->>DAG: new/changed document (sensor/schedule)
    DAG->>PG: INSERT ingestion_job (state=pending)
    DAG->>OBJ: put(raw/…)  (store original)
    DAG->>PROC: parse + OCR fallback (two-stage)
    alt extraction quality OK
        PROC->>OBJ: put(curated/…)
        PROC->>PG: upsert document_version (dedup by checksum; supersede prior)
        PROC->>PG: insert sections
        DAG->>IDX: chunk sections
        IDX->>LLM: embed(chunks, model_version)
        LLM-->>IDX: vectors
        IDX->>PG: insert chunk (tsv) + embedding (hnsw)
        DAG->>PG: UPDATE ingestion_job (state=succeeded)
    else extraction fails / low quality
        PROC->>PG: UPDATE ingestion_job (state=failed, error_info)
        DAG->>DAG: retry w/ backoff → dead_letter
    end
    DAG->>PG: write lineage + data-quality report
```

Key points: raw is stored **before** processing (evidence preserved, NFR15); a new revision **supersedes** via `is_current` without deleting the old (FR14); failures dead-letter and are reprocessable (Story 2.6).

## 2. RAG query (LangGraph, request-time) — authorize → answer / abstain

```mermaid
sequenceDiagram
    autonumber
    actor U as Technician
    participant WEB as Next.js (BFF)
    participant API as FastAPI
    participant LG as LangGraph
    participant VS as VectorStore (pg)
    participant RR as Reranker
    participant LLM as LLMClient
    participant PG as PostgreSQL

    U->>WEB: ask question (+equipment)
    WEB->>API: POST /assistant/query (bearer: tenant+role)
    API->>API: authorize BEFORE retrieval (FR21)
    alt not authorized
        API-->>WEB: 403 (no leakage)
    else authorized
        API->>LG: run(state: question, tenant, equipment)
        LG->>LG: analyze query → identify model/revision
        LG->>VS: hybrid search (tenant-scoped, only_current)
        VS->>PG: lexical (tsv) + vector (hnsw) + filters
        PG-->>VS: candidates
        VS-->>LG: candidates
        LG->>RR: rerank(top-k)
        RR-->>LG: ordered evidence
        alt evidence sufficient
            LG->>LLM: stream(cited generation + warnings)
            LLM-->>WEB: tokens (SSE, TTFT < 5s)
            LG->>PG: insert query_trace (abstained=false, cost, latency)
            LG-->>API: final: answer + citations
        else insufficient
            LG->>PG: insert query_trace (abstained=true)
            LG-->>API: final: abstain ("insufficient evidence")
        end
        API-->>WEB: final event
        WEB-->>U: streamed answer or honest refusal
    end
```

Key points: authorization is resolved **before** any retrieval/source access; retrieval is tenant-scoped and version-aware; the graph takes the **abstention branch** rather than inventing content (FR17); every run writes a `query_trace` (FR30) — answered *or* abstained.

> These are design-level sequences. Exact node boundaries, retry edges, and the sufficiency threshold are inside-the-box LLD, finalized in Stories 3.4/3.5 and tuned against the evaluation sets (Epic 5).
