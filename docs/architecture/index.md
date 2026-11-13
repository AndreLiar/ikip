# IKIP Architecture — Sharded (Index)

_Sharded from `../architecture.md` (BMAD PO step). Each file holds one architecture section. The parent `../architecture.md` remains the full, readable document; these shards are the implementation-reference views._

| # | Section | File |
|---|---------|------|
| 1 | Introduction | [`introduction.md`](./introduction.md) |
| 2 | High Level Architecture | [`high-level-architecture.md`](./high-level-architecture.md) |
| 3 | Tech Stack | [`tech-stack.md`](./tech-stack.md) |
| 4 | Data Models | [`data-models.md`](./data-models.md) |
| 5 | Components | [`components.md`](./components.md) |
| 6 | Core Workflows | [`core-workflows.md`](./core-workflows.md) |
| 7 | Database Schema | [`database-schema.md`](./database-schema.md) |
| 8 | Source Tree | [`source-tree.md`](./source-tree.md) |
| 9 | Infrastructure and Deployment | [`infrastructure-and-deployment.md`](./infrastructure-and-deployment.md) |
| 10 | Error Handling Strategy | [`error-handling-strategy.md`](./error-handling-strategy.md) |
| 11 | Coding Standards | [`coding-standards.md`](./coding-standards.md) |
| 12 | Test Strategy | [`test-strategy.md`](./test-strategy.md) |
| 13 | Security | [`security.md`](./security.md) |
| 13a | Threat Model | [`threat-model.md`](./threat-model.md) |

## Diagrams (diagram-as-code)

Python-generated system design diagrams (mingrammer `diagrams` + Graphviz) — source in [`diagrams/`](./diagrams/README.md), rendered PNG+SVG in [`img/`](./img):

1. [System Context](./img/01_system_context.png) — whole platform (embedded in [high-level-architecture](./high-level-architecture.md))
2. [Data Engineering Pipeline](./img/02_ingestion_pipeline.png) — Dagster raw→curated (Epic 2)
3. [RAG Request Workflow](./img/03_rag_workflow.png) — LangGraph (Epic 3)
4. [Azure Production Topology](./img/04_azure_deployment.png) — Container Apps + managed services (Epic 6)
5. [Local Development](./img/05_local_dev.png) — Docker Compose (NFR17)

## Low-Level / Contract-Level Design (LLD)

The HLD above is the stable frame; the contract-level design (schema DDL + ERD, port signatures, API shapes, sequence diagrams) lives in [`lld/`](./lld/index.md). Inside-the-box detail (algorithms, tuning) stays deferred to each story.

- [Data Schema & ERD](./lld/data-schema.md) · [Interfaces / Ports](./lld/interfaces.md) · [API Contract](./lld/api-contract.md) · [Sequence Diagrams](./lld/sequence-diagrams.md)

## Explainers
- [Why LangGraph (and not just LangChain)?](./why-langgraph.md) — companion to [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md) · 🇫🇷 [version française](./why-langgraph.fr.md)
- [Why both Dagster *and* LangGraph?](./dagster-vs-langgraph.md) — companion to [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md)
- [LLMOps stack](./llmops-stack.md) — consolidated LLMOps tooling (OTel + Langfuse + Foundry + pytest); companion to [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)

## Reference
- Parent architecture: [`../architecture.md`](../architecture.md)
- PRD: [`../prd.md`](../prd.md) · Sharded epics: [`../prd/index.md`](../prd/index.md)
- Project Brief: [`../brief.md`](../brief.md)
- Data Sources appendix: [`../data-sources.md`](../data-sources.md)
- Decision records: [`../adr/README.md`](../adr/README.md)
