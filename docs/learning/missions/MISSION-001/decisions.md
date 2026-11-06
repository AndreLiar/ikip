# MISSION-001 — Decisions (dev tooling)

These are **dev-tooling** conventions (lighter than architecture ADRs, which stay in `docs/adr/`). Each: problem → choice → why here → alternative → trade-off → when to switch.

## D1 — Python lint+format: `ruff`
- **Problem:** consistent Python style + lint across many services, enforced in CI.
- **Choice:** `ruff` (single tool for lint + format), config in root `pyproject.toml`.
- **Why here:** one fast Rust tool replaces black + isort + flake8; less config, faster CI; shared rules across the monorepo.
- **Alternative:** black + flake8 + isort (the long-standing combo).
- **Trade-off:** ruff's format is newer/less battle-worn than black (though black-compatible); rules evolve.
- **Switch when:** a needed lint/format behaviour isn't supported by ruff.

## D2 — Lint/format scope excludes `docs/`
- **Problem:** ruff flagged the diagram-as-code generators (`docs/architecture/diagrams/*.py`) and illustrative code blocks.
- **Choice:** `extend-exclude = ["docs"]` — lint/format **application code** (apps/services/packages/tests) only.
- **Why here:** diagram scripts use an intentionally loose DSL (`a >> b`) and long label strings; LLD markdown has deliberately compact pseudo-code. They are documentation artifacts, not source.
- **Alternative:** reformat everything to satisfy ruff.
- **Trade-off:** diagram scripts aren't style-checked (acceptable — they're generators, verified by rendering).
- **Switch when:** diagram scripts graduate into maintained tooling worth linting (give them their own ruff scope).

## D3 — Python env/deps: `uv`
- **Choice:** `uv` (declared as the manager; full workspace wiring lands with the first service code, Story 1.3).
- **Why here:** fast installs, lockfile, workspace support — fits a Python monorepo.
- **Alternative:** Poetry / pip-tools.
- **Trade-off:** uv is newer; smaller (but fast-growing) ecosystem of docs vs Poetry.
- **Switch when:** a dependency/workflow needs a Poetry-only feature.

## D4 — JS package manager: `pnpm` workspaces
- **Choice:** `pnpm` with `pnpm-workspace.yaml` (`apps/*`, `packages/*`).
- **Why here:** efficient disk usage (content-addressed store), strong monorepo workspaces, good Next.js support.
- **Alternative:** npm workspaces / yarn / Turborepo.
- **Trade-off:** contributors must have pnpm; stricter peer-dep resolution than npm.
- **Switch when:** CI build times justify a monorepo build system (Turborepo) on top.

## D5 — CI enforces ruff now; TS lint later
- **Choice:** CI runs `ruff check` + `ruff format --check` (no install/lockfile needed via `pip install ruff`); TS lint/test wait until there is TS code + a pnpm install step (Story 1.3/1.4).
- **Why here:** keep CI fast and meaningful for the code that exists; avoid a pnpm install step that lints nothing yet.
- **Trade-off:** TS config present but not yet CI-enforced.
- **Switch when:** `apps/web` or `packages/*` ship TS (add a pnpm job — Story 1.4).
