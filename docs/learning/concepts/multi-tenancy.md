# Concept — Multi-tenancy & tenant isolation

_Write-once concept note. First used by [MISSION-004](../missions/MISSION-004/mission.md). Reused by every table/query that touches tenant data._

## What "multi-tenant" means here
One deployment serves many customer organizations (**tenants**); each tenant's data must be **invisible and inaccessible** to every other tenant. A cross-tenant leak is the worst failure mode for a B2B platform — NFR10 makes "zero cross-tenant disclosure" a release gate (Story 6.2).

## The three common isolation models
| Model | How | Trade-off |
|---|---|---|
| **Separate databases** per tenant | one DB per customer | strongest isolation, heaviest ops/cost; hard at scale |
| **Separate schemas** per tenant | one Postgres schema per customer | medium isolation, schema sprawl |
| **Shared tables + `tenant_id`** (IKIP) | every row carries `tenant_id`; queries filter by it | simplest to operate/scale; isolation depends on **always** filtering |

IKIP uses the **shared-table + `tenant_id`** model — standard for SaaS at this scale. Its risk is obvious: *one forgotten `WHERE tenant_id = …` leaks data.* So isolation must be **structural**, not left to each query author.

## IKIP's structural enforcement: the repository layer
Every tenant-owned table carries `tenant_id` (the `TenantScoped` mixin). All access goes through a **`TenantScopedRepository` bound to one tenant**, which:
- injects `WHERE tenant_id = :tenant_id` into **every** read (`list`, `get`),
- **stamps** `tenant_id` on every write (ignoring any caller-supplied value).

So a repository for tenant A *cannot* return or write tenant B's rows — the filter isn't optional, it's in the base class. Code authors can't forget it because they never write the raw query.

```python
class UserRepo(TenantScopedRepository[AppUser]):
    model = AppUser

UserRepo(session, tenant_a_id).list()   # only tenant A's users, always
```

## Defense in depth (planned)
Repository scoping is **application-layer** defense. A second, database-layer defense is **PostgreSQL Row-Level Security (RLS)**: policies that filter by a session variable so even a raw SQL query can't cross tenants. Planned as Epic 6 hardening (Story 6.2) — belt *and* braces. (Neon supports RLS.)

## How we prove it
Isolation is not assumed — it's **tested** (Story 1.5 AC4): seed tenant A + B rows, then assert a tenant-A repository returns only A's rows and cannot `get()` a B row by id, and that `add()` overrides a foreign `tenant_id`. These run against an **ephemeral DB** (a Neon branch), never the shared dev DB.

## Rules to remember
1. Every tenant-owned table gets `tenant_id` (+ an index leading with it).
2. Never write a raw tenant-table query outside the repository; the repo owns the filter.
3. Prove isolation with a test for every new tenant-owned entity.
4. RLS is the DB-level backstop (Epic 6), not a replacement for repo scoping.

## Related
- [ADR 0017](../../adr/0017-sqlalchemy-alembic.md) (SQLAlchemy/Alembic) · [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md) (repository/ports) · [ADR 0001](../../adr/0001-vector-store-pgvector.md) (single-store hybrid, tenant-scoped).
- Data model: `docs/architecture/lld/data-schema.md`.
