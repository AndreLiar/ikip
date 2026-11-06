# Core Workflows

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

**Ingestion (Dagster, batch):** connector → raw stored in object storage + `IngestionJob` created → parse/OCR (two-stage) → clean/normalize/validate → dedup → create/supersede `DocumentVersion` → enrich metadata → chunk into `Section`/`Chunk` → embed (`Embedding`) → index (full-text + pgvector) → lineage + quality report. Failures → dead-letter + retry; reprocessing via asset-aware re-run. See [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md).

![IKIP Data Engineering Pipeline](./img/02_ingestion_pipeline.png)

> Generated as code (`diagrams/02_ingestion_pipeline.py`). Solid = principal flow; dashed = backing dependency.

**RAG (LangGraph, request-time):**

```mermaid
flowchart LR
  A[User query + tenant/role] --> AuthZ{Authorized?}
  AuthZ -->|no| Deny[403]
  AuthZ -->|yes| B[Query analysis]
  B --> C[Equipment identification]
  C --> D[Hybrid retrieval + equipment/version filters]
  D --> E[Rerank]
  E --> F{Evidence sufficient?}
  F -->|no| G[Abstain: insufficient evidence]
  F -->|yes| H[Cited generation + surface warnings]
  H --> I[Answer + citations + QueryTrace]
  G --> I
```

![IKIP RAG Request Workflow](./img/03_rag_workflow.png)

> Generated as code (`diagrams/03_rag_workflow.py`). Solid = principal flow; dashed = backing dependency.

Authorization is resolved before retrieval; traces (`QueryTrace`) capture retrieval IDs, model, latency and cost.
