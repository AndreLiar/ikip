# IKIP — Low-Level / Contract-Level Design (LLD)

_Contract-level design: the interfaces **between** components, stable enough to pin before code. Inside-the-box detail (algorithms, class internals, parameter tuning) remains deferred to each story at implementation time (BMAD), per the HLD → story sequencing. Builds on the HLD in [`../index.md`](../index.md)._

> **Scope boundary.** This is *design*, not implementation: schema DDL, interface signatures, API shapes and sequence diagrams — the contracts. The _mechanics_ that fill each box (chunking parameters, hybrid-fusion weights, rerank model, class internals) are decided when the owning story is built, because they change on first contact with real data.

| # | Artifact | Purpose | File |
|---|----------|---------|------|
| 1 | **Data Schema & ERD** | Physical PostgreSQL schema (DDL, keys, indexes, pgvector, constraints) + ERD | [`data-schema.md`](./data-schema.md) |
| 2 | **Interface / Port Signatures** | Method signatures for the six infrastructure ports (ADR 0003) | [`interfaces.md`](./interfaces.md) |
| 3 | **API Contract Skeleton** | `/api/v1` endpoints, request/response shapes, error envelope | [`api-contract.md`](./api-contract.md) |
| 4 | **Sequence Diagrams** | Call-level flows for ingestion (Dagster) and RAG (LangGraph) | [`sequence-diagrams.md`](./sequence-diagrams.md) |

## Relationship to the rest of the docs
- **HLD source of truth:** [`../../architecture.md`](../../architecture.md) and its [shards](../index.md). The entity-level data model and component tables live there; this LLD makes them physical.
- **Decisions:** the ADRs in [`../../adr/`](../../adr/README.md) (esp. 0001 pgvector, 0003 ports & adapters, 0004 hybrid retrieval, 0007 LLM client).
- **Requirements:** FR/NFR in [`../../prd.md`](../../prd.md); each artifact notes the stories it unblocks.

> These contracts become real code during implementation: the DB schema → Alembic migrations; the API shapes → generated OpenAPI (Story 4.1); the port signatures → `packages/common`. Treat this folder as the agreed contract, and let the generated/implemented versions supersede it where they diverge.
