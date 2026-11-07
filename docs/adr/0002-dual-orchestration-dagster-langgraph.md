# 0002. Dual orchestration — Dagster for the data pipeline, LangGraph + LangChain for RAG

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** FR1–FR10 (ingestion/indexing), FR14–FR18 (RAG), FR30 · NFR15 · Epic 2, Epic 3, Story 5.4 · `../architecture.md` (High Level Architecture, Core Workflows, Components)
- **Explainers:** [Why LangGraph (and not just LangChain)?](../architecture/why-langgraph.md) · [Why both Dagster *and* LangGraph?](../architecture/dagster-vs-langgraph.md)

## Context
IKIP contains two workflow systems with fundamentally different execution characteristics:

1. **Knowledge-base construction** — scheduled/event-driven, batch, long-running: ingest → parse/OCR → clean → validate → dedup → version → enrich → chunk → embed → index. It needs asset dependencies, lineage, schedules/sensors, backfills, partitions, retries and asset-aware reprocessing (FR1–FR10, NFR15, Epic 2).
2. **Technician-facing RAG** — request-time, stateful, conditional: query analysis → equipment ID → hybrid retrieval → rerank → sufficiency check → cited generation → abstention, with checkpointing and auditable branching (FR14–FR18, Epic 3).

A single tool could technically cover both, but each class of workflow is well served by different tooling, and conflating them couples request-time AI logic to batch data-engineering concerns.

## Decision
Use **two orchestrators, one shared data model**:
- **Dagster** orchestrates and observes the data/knowledge-base pipeline as software-defined assets (schedules, sensors, lineage, backfills, quality checks). Dagster triggers/observes work; heavy processing may run in container workers rather than inside the Dagster process.
- **LangGraph + LangChain** orchestrate the request-time RAG workflow: LangGraph for the stateful graph (nodes, conditional edges, abstention path, checkpointing); LangChain for model/retriever/tool integrations.

They are **complementary, not interchangeable**. Both read/write the same PostgreSQL + object storage but never share an execution runtime. LangGraph is not the system's job queue or storage; Dagster is not used for request-time AI reasoning.

## Consequences
**Positive**
- Each workflow uses tooling fit for its execution model: Dagster gives native lineage/backfill/asset-aware reprocessing (answers "which docs failed yesterday", "reprocess after a parser change" — Stories 2.6); LangGraph gives auditable, resumable, conditional RAG with a first-class abstention edge.
- Clean separation: batch data concerns never leak into request-time latency paths.
- Tracing (`query_trace`, Story 5.4) maps naturally onto LangGraph nodes.

**Negative / risks**
- Two orchestration frameworks to learn, operate and monitor (added operational surface and, on Azure, some extra compute/storage for the Dagster scheduler/UI/run workers).
- Two mental models for contributors.

**Neutral**
- The LangGraph runtime runs inside FastAPI/worker containers (no separate paid hosting required) provided durable persistence is configured.

## Alternatives Considered
- **LangGraph only (replace Dagster):** feasible for a small system — ingestion could be LangGraph nodes — but you would hand-build schedules, sensors, asset dependencies, lineage, backfills and partitions that Dagster provides natively. Rejected for a data-intensive industrial platform.
- **Dagster only (replace LangGraph):** Dagster is not designed for stateful, conditional, request-time AI reasoning with human-in-the-loop and abstention. Rejected for the technician-facing path.
- **A single general-purpose workflow engine (e.g., Temporal) for both:** more generic power but neither the data-asset ergonomics of Dagster nor the AI-graph ergonomics of LangGraph; higher build cost. Rejected at MVP.

## Dagster hosting (2026-11-07)
- **Dev:** Dagster OSS runs in a **Docker image** (webserver + daemon). Free; the one containerized dev component (the managed data backends — Neon/R2/Redis/Langfuse — are not). Note: `dagster dev` as a plain process is also possible, but we standardize on a Docker image for dev parity.
- **Prod:** hosting is **deferred / open** — candidates: self-host on Azure Container Apps (daemon ~always-on), a managed alternative (e.g. Prefect Cloud free tier), or lighter orchestration (GitHub Actions + the existing `JobQueue`). Decided when Epic 2 orchestration (Story 2.2) lands and the prod cost/benefit is concrete. The always-on daemon is the main prod cost to weigh.

## Revisit When
- The system is small enough that one orchestrator's overhead outweighs the benefit (collapse to LangGraph-only), **or**
- Operational burden of running Dagster on Azure is disproportionate to pipeline complexity, **or**
- A single durable-execution engine would materially simplify operations without losing asset lineage or AI-graph ergonomics.
