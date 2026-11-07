# IKIP — Learning log (execution-as-teaching)

Mission notes record how each non-trivial implementation was built **and** how to reproduce it without an agent. Architecture decisions live in [`../adr/`](../adr/README.md); reproduction/runbooks in [`../runbooks/`](../runbooks); these notes cross-link them.

## Missions
| Mission | Scope | Story |
|---------|-------|-------|
| [MISSION-001](./missions/MISSION-001/mission.md) | Monorepo scaffold, tooling & conventions | Epic 1 / Story 1.1 |
| [MISSION-002](./missions/MISSION-002/mission.md) | Configuration layer & connectivity doctor | Epic 1 / Story 1.2 |
| [MISSION-003](./missions/MISSION-003/mission.md) | FastAPI skeleton & health endpoint | Epic 1 / Story 1.3 |
| [MISSION-004](./missions/MISSION-004/mission.md) | Multi-tenant data foundation (models, migrations, repo) | Epic 1 / Story 1.5 |

## Concepts (write-once, reused across missions)
| Concept | Covers |
|---------|--------|
| [dev-tooling](./concepts/dev-tooling.md) | lint vs format, ruff, pytest, pnpm workspaces, prettier, eslint flat, tsconfig |
| [config-12-factor](./concepts/config-12-factor.md) | env-based config, Pydantic Settings, SecretStr, fail-fast, hermetic tests |
| [health-checks](./concepts/health-checks.md) | liveness vs readiness, dependency probes, 503-on-degraded, mockability |
| [multi-tenancy](./concepts/multi-tenancy.md) | isolation models, `tenant_id` + repository scoping, RLS backstop, proving isolation |
