# Industrial Knowledge Intelligence Platform (IKIP)

> A production-grade, multi-tenant industrial RAG & document intelligence platform.
> Transforms heterogeneous industrial documentation into secure, searchable, citable, continuously-updated knowledge.

**Status:** 📐 Planning / Structuring phase (BMAD) — _no implementation code yet_.

---

## What this is

IKIP ingests industrial equipment manuals, specifications, maintenance procedures, troubleshooting guides and parts catalogs, then exposes them through a hybrid retrieval + Retrieval-Augmented Generation (RAG) system with equipment-aware search, document-level citations, source-version tracking and secure multi-tenant access.

This project is being planned using the **BMAD method** (Breakthrough Method of Agile AI-Driven Development): we produce a Project Brief → PRD → Architecture before any code, so the build phase is driven by sharded, agent-ready epics and stories.

## BMAD document index

The planning artifacts live in [`docs/`](./docs) and are meant to be read in order:

| # | Artifact | Purpose | File |
|---|----------|---------|------|
| 1 | **Project Brief** | Problem, solution, users, MVP scope, constraints, risks | [`docs/brief.md`](./docs/brief.md) |
| 2 | **Product Requirements (PRD)** | Goals, functional/non-functional requirements, epics & stories with acceptance criteria | [`docs/prd.md`](./docs/prd.md) |
| 3 | **Architecture** | System design, tech stack, data models, components, deployment, security, test strategy | [`docs/architecture.md`](./docs/architecture.md) |
| A | **Data Sources** (appendix) | Candidate ingestion sources (51, 9 categories) + evaluation datasets, with licensing gate | [`docs/data-sources.md`](./docs/data-sources.md) |
| B | **RAG Design Challenges** (appendix) | The retrieval difficulty dimensions IKIP is built around, each traced to requirements; + deferred items | [`docs/rag-design-challenges.md`](./docs/rag-design-challenges.md) |

Sharded epics (per-epic story files) live in [`docs/prd/`](./docs/prd) — see [`docs/prd/index.md`](./docs/prd/index.md).

Sharded architecture (per-section files) lives in [`docs/architecture/`](./docs/architecture) — see [`docs/architecture/index.md`](./docs/architecture/index.md).

Low-level / contract-level design (DB schema + ERD, port signatures, API contract, sequence diagrams) lives in [`docs/architecture/lld/`](./docs/architecture/lld).

Architecture Decision Records live in [`docs/adr/`](./docs/adr) — see [`docs/adr/README.md`](./docs/adr/README.md). First decision: [ADR 0001 — vector store (pgvector)](./docs/adr/0001-vector-store-pgvector.md).

Runbooks live in [`docs/runbooks/`](./docs/runbooks) — e.g. [developing on Azure at low cost](./docs/runbooks/dev-on-azure-cost-control.md).

## How to use these documents (BMAD workflow)

1. **Review & refine** the Brief, then the PRD, then the Architecture (each builds on the previous).
2. **Shard** the PRD into per-epic files and the Architecture into per-component files (PO step) when you are ready to build.
3. **Draft stories** one at a time (SM step) from the sharded epics.
4. **Implement** story-by-story (Dev step), validating against the acceptance criteria and the architecture's coding/test standards.

> The epics are ordered so each delivers a vertical, deployable increment. Epic 1 stands up the walking skeleton; later epics layer data engineering, retrieval, the app, LLMOps and production operations on top.

## Scope at a glance

**In scope (MVP):** ingestion & data-quality pipeline, versioned document + equipment repository, hybrid retrieval + grounded RAG with citations and abstention, multi-tenant backend + web app, evaluation harness, security controls, observability, local-first deployment with an Azure production path.

**Out of scope (initial):** autonomous equipment control, certified repair approval, sensor-stream predictive maintenance, large-scale multimodal engineering-drawing interpretation.
