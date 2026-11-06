# MISSION-001 — Monorepo scaffold & conventions (Epic 1, Story 1.1)

**Mode:** Autonome (low-risk dev scaffold) + knowledge transfer.
**Objective:** stand up the IKIP monorepo skeleton, shared lint/format tooling, documented conventions, and verify the ADR home — the base every later story builds on.
**Maps to:** Epic 1 / Story 1.1 (`docs/prd/epic-1-foundation-platform-core.md`).

## Acceptance criteria (Story 1.1)
1. Monorepo with `apps/`, `services/`, `packages/`, `infrastructure/`, `tests/`, `datasets/`, `docs/`. — **[verified]**
2. README documents structure, setup, contribution/branching conventions. — **[verified]**
3. Linting/formatting configured for Python and TypeScript. — **[verified]** (ruff green in CI; prettier/eslint configured)
4. ADR location and template exist. — **[verified]** (`docs/adr/` already present; not recreated)

## Deliverables & where they live
- Skeleton: `apps/ services/ packages/ infrastructure/ tests/ datasets/` (with `.gitkeep`).
- Python tooling: `pyproject.toml` (ruff lint+format, pytest config).
- JS/TS tooling: `package.json` (pnpm workspaces), `pnpm-workspace.yaml`, `.prettierrc.json`, `.prettierignore`, `tsconfig.base.json`, `eslint.config.mjs`.
- CI: `.github/workflows/ci.yml` now runs `ruff check` + `ruff format --check`.
- Conventions: `README.md` (structure, setup, branching).
- Decisions: [`decisions.md`](./decisions.md) · Execution log: [`execution.md`](./execution.md) · Reproduction: [`tutorial.md`](./tutorial.md).

## Related decisions (existing ADRs, not duplicated)
Monorepo [ADR 0006](../../../adr/0006-monorepo.md) · ports & adapters [ADR 0003](../../../adr/0003-local-first-ports-and-adapters.md) · managed-first dev [ADR 0012](../../../adr/0012-local-first-dev-cloud-models-only.md).
