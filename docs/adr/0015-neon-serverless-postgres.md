# 0015. Neon serverless Postgres (+ pgvector) as the database, replacing Azure Flexible Server / local Docker default

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR9–FR14 · NFR1, NFR15, NFR17 · Story 1.2, 1.5, 3.x · builds on [ADR 0001](./0001-vector-store-pgvector.md), [ADR 0004](./0004-hybrid-retrieval-on-postgres.md); relates to [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0012](./0012-local-first-dev-cloud-models-only.md), [ADR 0014](./0014-cloudflare-r2-object-storage.md)

## Context
The database hosts metadata, full-text search and pgvector embeddings ([ADR 0001](./0001-vector-store-pgvector.md), [ADR 0004](./0004-hybrid-retrieval-on-postgres.md)). The plan used **local Docker Postgres** (dev) and **Azure PostgreSQL Flexible Server** (prod). Flexible Server is **always-on** (~$12–15/mo minimum, B1ms) — the single largest standing cloud cost. **Neon** is serverless Postgres that **supports pgvector**, **scales compute to zero** when idle, has a **free tier**, and offers **database branching** and **Azure regions**.

Because Neon is just Postgres, the hybrid-retrieval architecture is **unchanged** — same `tsvector`/GIN + pgvector, same SQL, same Alembic migrations, same connection string.

## Decision
Use **Neon serverless Postgres as the database for all environments** (dev, staging, prod), with the `pgvector` extension enabled. This replaces Azure PostgreSQL Flexible Server in prod and local Docker Postgres as the default dev database.

- **Local Docker Postgres + pgvector is retained as an optional offline backend** (same Postgres, just a different connection string) — preserving a fully-offline/fast inner loop and hermetic CI, so NFR17 stays satisfiable.
- Neon is **co-located in an Azure region** near Container Apps to avoid cross-provider latency.
- Connection via standard Postgres driver (pooled connection string) from `DATABASE_URL`; no `VectorStore` adapter change (it is still Postgres+pgvector — [ADR 0001](./0001-vector-store-pgvector.md)).
- Use **Neon branching** to give feature branches / PRs isolated databases where useful.

## Consequences
**Positive**
- **Removes the always-on Postgres cost** in prod/staging: Neon scales compute to zero → ~$0 when idle (free tier covers early usage). This is the biggest standing-cost reduction in the stack.
- **No architecture change:** pgvector + full-text + Alembic all work; ADR 0001/0004 intact.
- **Branching** gives per-PR/per-feature isolated DBs — great fit for the branch→PR workflow.
- No database server to operate (serverless); dev↔prod parity on the same Neon service.

**Negative / risks**
- **Cold-start latency vs NFR1 (p95 < 1.5 s):** after idle, the first query pays a compute wake-up (sub-second to seconds). Mitigation: a minimum-compute/warm setting or a keep-warm ping on the hot path; accept cold start only on the very first idle query.
- **Free-tier storage vs vector volume:** ~400k × 1536-dim float32 vectors ≈ ~2.4 GB + HNSW overhead, which can exceed Neon's free storage. Mitigation: smaller embedding dimensions (256–512 via `text-embedding-3-small`), `halfvec` (pgvector ≥ 0.7, ~½ size), or Neon's modest paid tier (still scale-to-zero). **Verify current Neon free-tier limits before relying on them.**
- **DB becomes remote in dev** (like R2/LLM) — network dependency, per-query latency. Mitigation: the retained local Docker Postgres option for offline/fast work.
- **Multi-vendor** (Azure compute + Neon DB + R2 storage): mitigated by Azure-region co-location.
- **Data residency** (EU) — same consideration as R2; a revisit trigger.

**Neutral**
- Secrets: `DATABASE_URL` carries the Neon credential → `SecretsProvider`/Key Vault, never committed.

## Alternatives Considered
- **Azure PostgreSQL Flexible Server (prod) + local Docker (dev), as planned:** native Azure integration, managed identity, VNet; but always-on cost and no scale-to-zero/branching. Rejected on cost/ergonomics; remains the fallback if data residency or Azure-native networking demands it.
- **Local Docker Postgres everywhere (self-managed in prod):** free software but you operate HA/backups/durability. Rejected — serverless removes that burden.
- **A dedicated vector DB (Qdrant) instead:** rejected earlier ([ADR 0001](./0001-vector-store-pgvector.md)); Neon keeps the single-store hybrid-relational design.

## Revisit When
- **Cold-start latency** can't meet NFR1 even with warm/min-compute → pin a minimum compute or move to Flexible Server.
- **Data residency / Azure-native networking (VNet, managed identity)** becomes a hard requirement → Azure PostgreSQL Flexible Server (France Central). The connection string makes this a config change.
- Vector volume / usage outgrows Neon's economics at scale.
