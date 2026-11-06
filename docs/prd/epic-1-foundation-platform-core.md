# Epic 1 — Foundation & Platform Core

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Stand up a deployable walking skeleton: a monorepo with CI, a managed-services-first dev setup (app local; Neon/R2/Redis Cloud/Langfuse via `.env`, with optional local Docker backends for offline work), a FastAPI backend talking to Postgres, authentication, and the multi-tenant data foundation — so every later epic builds on a secure, tested base and can be run end-to-end from day one.

**Related requirements:** FR19, FR20, FR21, FR27 · NFR10, NFR12, NFR13, NFR14, NFR16, NFR17

> **Infra context (decided after this epic was first drafted):** the default dev backends are **managed** — Neon (Postgres+pgvector, [ADR 0015](../adr/0015-neon-serverless-postgres.md)), Cloudflare R2 (object storage, [ADR 0014](../adr/0014-cloudflare-r2-object-storage.md)), Redis Cloud/Docker ([ADR 0009](../adr/0009-caching-strategy.md)), Langfuse Cloud ([ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)). Local Docker Postgres/MinIO/Redis remain an **optional offline** path (NFR17). All access goes through the ports ([ADR 0003](../adr/0003-local-first-ports-and-adapters.md)).

---

## Story 1.1 Monorepo & Repository Conventions
As a developer, I want a monorepo scaffold with documented conventions, so that all services share source and contributors follow one structure.
**Acceptance Criteria:**
1. Monorepo created with `apps/`, `services/`, `packages/`, `infrastructure/`, `tests/`, `datasets/`, `docs/`.
2. README documents structure, setup, and contribution/branching conventions.
3. Linting/formatting configured for Python and TypeScript.
4. Architecture Decision Record (ADR) location and template exist. _(Already in place: `docs/adr/` with README + template — verify, don't recreate.)_

## Story 1.2 Dev Environment (managed-first, optional offline Docker)
As a developer, I want a reproducible dev environment that connects to managed services by default and can fall back to local Docker backends, so that I develop cheaply and can also work fully offline.
**Acceptance Criteria:**
1. The app reads all backend connections from environment via `.env` (copied from the committed `.env.example`); no hard-coded secrets. Default dev points at **managed services** (Neon / R2 / Redis Cloud / Langfuse).
2. A Docker Compose file provides an **optional offline** stack (local Postgres+pgvector, MinIO, Redis) selectable by pointing `.env` at localhost — same ports/interfaces, no code change.
3. A single documented command brings the optional offline stack up/down.
4. Connectivity to each configured backend (managed or local) is verifiable via a documented check.

## Story 1.3 FastAPI Backend Skeleton with Health Check
As a developer, I want a FastAPI service with a versioned health endpoint, so that we have a deployable backend baseline.
**Acceptance Criteria:**
1. FastAPI app exposes `GET /api/v1/health` returning service status plus the status of each **configured** dependency (Neon/Postgres, R2/object storage, Redis) — whichever the `.env` points at (managed or local).
2. Pydantic settings load configuration from environment (`.env`); invalid/missing required config fails fast with a clear error.
3. Structured logging is configured (no secrets in logs).
4. A unit test and an integration test for the health endpoint pass in CI (dependency checks mockable so CI needs no live managed services).

## Story 1.4 CI Pipeline & Baseline Testing
As a developer, I want GitHub Actions CI running lint and tests on every push, so that quality is enforced from the start.
**Acceptance Criteria:**
1. CI runs lint + unit/integration tests for backend (and frontend once present).
2. CI fails the build on lint or test failure.
3. Test coverage is reported.
4. CI status is required before merge.

## Story 1.5 Multi-Tenant Data Foundation
As an architect, I want the core tenant/user schema and tenant-scoping mechanism, so that isolation is built in from the first data model.
**Acceptance Criteria:**
1. Migrations create `tenant` and `user` tables with the fields in the data model.
2. Every tenant-owned table carries a tenant identifier and queries are tenant-scoped by default.
3. A migration tool (safe, reversible) is configured.
4. Tests prove a query in tenant A cannot read tenant B rows.

## Story 1.6 Authentication & Role-Based Authorization
As a user, I want to authenticate and receive a role, so that access is controlled from the foundation up.
**Acceptance Criteria:**
1. Authentication issues a session/token carrying tenant + role (local dev accounts/OIDC; Entra ID in prod).
2. Roles (e.g., admin, manager, technician) are defined and enforced by a reusable authorization dependency.
3. Protected endpoints reject unauthenticated/unauthorized requests.
4. Unit + security tests cover role enforcement and tenant binding.
