# MISSION-004 — Decisions

## D1 — Neon branching for destructive DB tests (not a container, not the dev DB)
- **Problem:** migration + isolation tests create/drop tables and insert data. Where do they run without polluting the shared Neon `dev` DB?
- **Choice:** an **ephemeral Neon branch** per test run (CI), created and deleted automatically. Locally, verified against the `dev` branch using **flush + rollback** (data never commits) and create/drop schema (transient).
- **Why here:** 100% Neon (no container, no local Docker), real Postgres parity, instant branch. Keeps the dev DB clean.
- **Alternative:** a GitHub Actions Postgres **service container** (hermetic, no Neon secret) — the container runs on the GitHub runner, never the laptop.
- **Trade-off:** Neon branching needs a **Neon API token** in CI secrets; the service container needs none. We chose Neon for parity/consistency.
- **Switch when:** CI Neon-branch overhead/latency hurts → fall back to the service container.

## D2 — Neon environment branches (dev / prod) + ephemeral test branches
- **Choice:** `production` (Neon's default branch) = prod; a persistent **`dev`** branch = daily dev (`.env` points here); **`test/*`** ephemeral branches (auto-delete) for CI.
- **Why here:** Neon branches model environments like git branches for the DB — cheap, isolated, instant. Fits dev/staging/prod from the architecture without 3 separate servers.
- **Trade-off:** free-tier branch/compute limits; real prod isolation may later want a **separate Neon project**, not just a branch.
- Amends [ADR 0015](../../../adr/0015-neon-serverless-postgres.md).

## D3 — Tenant isolation at the repository layer (RLS later)
- **Choice:** `TenantScopedRepository` injects `WHERE tenant_id` on reads and stamps it on writes; nobody writes raw tenant queries.
- **Why here:** makes isolation **structural** (can't be forgotten), matches the ports/coding-standards. Simple, testable.
- **Alternative:** Postgres **Row-Level Security (RLS)** — DB-level enforcement.
- **Trade-off:** repo scoping is app-layer only; a raw SQL bug could bypass it. → RLS is the planned **defense-in-depth** backstop (Epic 6, Story 6.2), not instead of repo scoping.

## D4 — Reversible migrations incl. enum TYPE drops
- **Choice:** the initial migration's `downgrade()` drops the `user_role` / `account_status` enum **types**, not just the tables.
- **Why here:** in Postgres, `DROP TABLE` leaves the `CREATE TYPE` behind → a re-`upgrade` fails "type already exists". Dropping them keeps migrations truly reversible (NFR13).
- **Lesson:** Alembic `--autogenerate` is a draft ("please adjust!") — review it; it misses enum drops and data migrations.
