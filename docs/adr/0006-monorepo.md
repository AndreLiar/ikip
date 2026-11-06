# 0006. Single monorepo for all apps, services and infrastructure

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** NFR12, NFR14 · Stories 1.1, 1.4 · `../architecture.md` (Source Tree, Tech Stack) · relates to [ADR 0003](./0003-local-first-ports-and-adapters.md)

## Context
IKIP spans a Next.js frontend, a FastAPI backend, several Python services (ingestion, document-processing, indexing, retrieval, evaluation), shared packages (`common` interfaces, `ai-clients`), infrastructure (Docker, Terraform), tests and datasets. The local and Azure deployments must share the **same** source so that moving to the cloud is an infra exercise, not a rewrite ([ADR 0003](./0003-local-first-ports-and-adapters.md)). Code could live in one repository or be split across many per-service repositories.

## Decision
Use a **single monorepo** with the structure defined in `../architecture.md` (Source Tree): `apps/`, `services/`, `packages/`, `infrastructure/`, `tests/`, `datasets/`, `docs/`. Shared contracts (the ports/interfaces and models in `packages/common`) are consumed directly by all services. One CI pipeline governs the whole tree (Story 1.4).

## Consequences
**Positive**
- Shared interfaces/models have a single source of truth; a contract change and all its consumers move in one atomic commit — critical for the ports-and-adapters design.
- One `docker compose` brings the whole stack up locally (NFR17); one CI pipeline enforces quality/security gates across everything (NFR14).
- Cross-cutting changes (e.g., a new `VectorStore` adapter) are visible and reviewable in one PR; no cross-repo version-skew of shared packages.
- Simplifies a solo/small-team project: one clone, one issue tracker, one history.

**Negative / risks**
- CI must scope/cache work to changed paths to stay fast as the tree grows (mitigated with path filters/affected-only builds).
- No hard repository boundary between services; discipline (and the interface layer) must prevent inappropriate coupling.
- A single repo means coarser-grained access control than per-service repos.

**Neutral**
- Mixed languages (Python + TypeScript) coexist; tooling is configured per subtree.

## Alternatives Considered
- **Polyrepo (one repo per service):** stronger isolation and independent release cadence, but shared-contract changes become multi-repo, multi-PR, version-pinned coordination — high friction for an interface-heavy, small-team project. Rejected.
- **Monorepo with a heavyweight build system (Nx/Bazel/Turborepo) from day one:** useful at scale, but premature; start with simple path-scoped CI and introduce tooling only if build times demand it. Deferred.

## Revisit When
- CI times or build complexity grow enough to need a dedicated monorepo build system (adopt tooling, not a split), **or**
- Independent teams/release cadences or access-control boundaries per service become a real requirement (consider extracting that service to its own repo).
