
# Architecture Decision Records (ADRs)

This directory records significant architectural decisions for IKIP — the context, the choice, and its consequences — so future contributors understand *why*, not just *what*. (Satisfies Epic 1, Story 1.1.)

## Conventions

- One decision per file, named `NNNN-short-title.md` (zero-padded, sequential).
- Status lifecycle: `Proposed` → `Accepted` → (`Superseded by NNNN` | `Deprecated`).
- Never edit the decision of an Accepted ADR; instead write a new ADR that supersedes it and update both `Status` lines.
- Keep them short. Link to `../prd.md`, `../architecture.md` and other ADRs by relative path.

## Template

```markdown
# NNNN. <Title>

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Deciders:** <roles/names>
- **Related:** <FR/NFR ids, stories, other ADRs>

## Context
<The problem, forces and constraints. Why a decision is needed now.>

## Decision
<The choice made, stated plainly.>

## Consequences
<Positive, negative and neutral results. What becomes easier/harder.>

## Alternatives Considered
<Options evaluated and why they were not chosen.>

## Revisit When
<Concrete, measurable triggers that would reopen this decision.>
```

## Index

| ADR                                                             | Title                                                                                 | Status             |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------ |
| [0001](./0001-vector-store-pgvector.md)                          | Use PostgreSQL + pgvector as the initial vector store                                 | Accepted           |
| [0002](./0002-dual-orchestration-dagster-langgraph.md)           | Dual orchestration — Dagster for the data pipeline, LangGraph + LangChain for RAG    | Accepted           |
| [0003](./0003-local-first-ports-and-adapters.md)                 | Local-first, cloud-ready via ports & adapters                                         | Accepted           |
| [0004](./0004-hybrid-retrieval-on-postgres.md)                   | Hybrid retrieval on PostgreSQL (full-text + pgvector) before managed/dedicated search | Accepted           |
| [0005](./0005-managed-containers-not-kubernetes.md)              | Managed containers (Azure Container Apps) over Kubernetes at MVP                      | Accepted           |
| [0006](./0006-monorepo.md)                                       | Single monorepo for all apps, services and infrastructure                             | Accepted           |
| [0007](./0007-pluggable-llm-client-azure-openai.md)              | Azure OpenAI via a pluggable `LLMClient` adapter                                    | Accepted           |
| [0008](./0008-nextjs-over-plain-react.md)                        | Next.js (framework) over plain React (SPA) for the web app                            | Accepted           |
| [0009](./0009-caching-strategy.md)                               | Caching strategy (layered, safety-first; Redis + Postgres backed)                     | Accepted           |
| [0010](./0010-foundry-model-platform-no-dedicated-ai-gateway.md) | Microsoft Foundry as model platform; no dedicated AI gateway at MVP                   | Accepted           |
| [0011](./0011-cloud-first-hybrid-dev-workflow.md)                | Cloud-first (hybrid) development workflow + cost strategy                             | Superseded by 0012 |
| [0012](./0012-local-first-dev-cloud-models-only.md)              | Local-first development, cloud for models only                                        | Accepted           |
| [0013](./0013-llmops-observability-otel-langfuse.md)             | LLMOps observability: OpenTelemetry + Langfuse (self-hosted)                          | Accepted           |
| [0014](./0014-cloudflare-r2-object-storage.md)                   | Cloudflare R2 for object storage (S3-compatible), replacing MinIO + Azure Blob        | Accepted           |
| [0015](./0015-neon-serverless-postgres.md)                       | Neon serverless Postgres (+ pgvector) as the database for all environments            | Accepted           |
| [0016](./0016-rag-evaluation-custom-plus-ragas.md)               | RAG evaluation: custom deterministic harness + Ragas, compared                        | Accepted           |
| [0017](./0017-sqlalchemy-alembic.md)                             | SQLAlchemy (ORM/Core) + Alembic (migrations) for the data layer                       | Accepted           |
| [0018](./0018-pydantic-records-pandera-frames.md)                | Validation: Pydantic for records, Pandera for frames                                  | Accepted           |
| [0019](./0019-structure-aware-chunking.md)                       | Structure-aware chunking with bounded sub-splitting                                    | Accepted           |
| [0020](./0020-embedding-model-text-embedding-3-small.md)         | Embedding model `text-embedding-3-small` @ 512 dims (Matryoshka reduction)             | Accepted           |
| [0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) | Framework boundary: reuse LangChain/LangGraph components behind our business ports (domain keeps schema, citations, tenant isolation, versioning) | Accepted           |
| [0022](./0022-grounded-answer-langgraph-gpt5-mini.md)            | Grounded-answer service: LangGraph + gpt-5.4-mini, server-resolved citations, post-generation grounding validation | Accepted           |
