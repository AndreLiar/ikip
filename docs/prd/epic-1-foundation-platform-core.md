# Epic 1 — Foundation & Platform Core

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Stand up a deployable walking skeleton: a monorepo with CI, a Dockerized local environment, a FastAPI backend talking to PostgreSQL, authentication, and the multi-tenant data foundation — so every later epic builds on a secure, tested base and can be run end-to-end from day one.

**Related requirements:** FR19, FR20, FR21, FR27 · NFR10, NFR12, NFR13, NFR14, NFR16, NFR17

---

## Story 1.1 Monorepo & Repository Conventions
As a developer, I want a monorepo scaffold with documented conventions, so that all services share source and contributors follow one structure.
**Acceptance Criteria:**
1. Monorepo created with `apps/`, `services/`, `packages/`, `infrastructure/`, `tests/`, `datasets/`, `docs/`.
2. README documents structure, setup, and contribution/branching conventions.
3. Linting/formatting configured for Python and TypeScript.
4. Architecture Decision Record (ADR) location and template exist.

## Story 1.2 Local Docker Development Environment
As a developer, I want `docker compose` to run the core dependencies locally, so that I can develop without cloud resources.
**Acceptance Criteria:**
1. Compose stack starts PostgreSQL (+pgvector), MinIO and Redis.
2. A single documented command brings the environment up/down.
3. Service configuration is read from environment variables / `.env` (no hard-coded secrets).
4. Health of each dependency is verifiable locally.

## Story 1.3 FastAPI Backend Skeleton with Health Check
As a developer, I want a FastAPI service with a versioned health endpoint, so that we have a deployable backend baseline.
**Acceptance Criteria:**
1. FastAPI app exposes `GET /api/v1/health` returning service + dependency status.
2. Pydantic settings load configuration from environment.
3. Structured logging is configured.
4. A unit test and an integration test for the health endpoint pass in CI.

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
