# Database Schema (notes)

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

- PostgreSQL 16; `pgvector` extension for `embedding.vector` with an appropriate index (e.g., HNSW/IVFFlat) chosen during Story 3.2/3.3.
- Full-text search via `tsvector`/GIN on curated content for the lexical path.
- Every tenant-owned table: `tenant_id` column + composite indexes beginning with `tenant_id`.
- Soft-delete/version supersession preserves original evidence (NFR15); hard deletion only via the retention/deletion workflow (Story 6.5).

> Store/engine rationale: [ADR 0001](../adr/0001-vector-store-pgvector.md) (vector store) and [ADR 0004](../adr/0004-hybrid-retrieval-on-postgres.md) (hybrid retrieval in Postgres).
>
> **Physical schema (DDL + ERD):** these notes are HLD; the full low-level schema is in [`lld/data-schema.md`](./lld/data-schema.md).
