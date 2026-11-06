# Concept — Dev tooling (lint, format, tests, monorepo)

_Write-once concept note. Referenced by missions that touch tooling (first: [MISSION-001](../missions/MISSION-001/mission.md)). Decisions for IKIP's specific choices: [MISSION-001/decisions.md](../missions/MISSION-001/decisions.md)._

## Why tooling at all
In a monorepo mixing Python and TypeScript, tooling **automates cosmetic decisions and catches errors early**, so reviews discuss logic — not whitespace. Wired into **CI** (the `validate` check), it is a *guarantee*, not a good intention. Two rules to remember:
- **Formatter = automatic consistency** (no debates about quotes/indentation).
- **Linter = safety net** (dead variables, undefined names, real-bug patterns caught in seconds).

## The key distinction: linter ≠ formatter
| | Formatter | Linter |
|---|---|---|
| Question | "Is it **tidy/consistent**?" | "Is it **correct/safe**?" |
| Acts on | spacing, indentation, line length, quotes | unused imports, undefined vars, bug patterns, import order |
| Fails the build for | style drift | likely bugs |

They are complementary: run the formatter to normalize, the linter to find problems.

---

## Python toolchain

### `pyproject.toml` — the central config
Standardized by PEP 518/621. One file for project metadata, required Python version, and **tool config** (`[tool.ruff]`, `[tool.pytest]`). Replaces the old scatter of `.flake8` / `setup.cfg` / `.isort.cfg` — one source of truth.

### `ruff` — lint **and** format in one tool
Ruff does both jobs (Rust, 10–100× faster than the old stack):
- `ruff format` — the formatter (replaces **black**).
- `ruff check` — the linter (replaces **flake8 + isort + pyupgrade + …**).

Rule families are chosen via `select` in `[tool.ruff.lint]`: `F` real errors (pyflakes), `E/W` style (pycodestyle), `I` import sorting (isort), `B` common traps (bugbear), `C4` comprehensions, `UP` modernize syntax (pyupgrade), `N` naming.

Why over black+flake8+isort: three separate tools that could disagree, now one fast tool, one config.

### `pytest` — the test framework
`[tool.pytest.ini_options]` points tests at `tests/` with `test_*.py` naming. Necessary because quality requirements (Recall@K, tenant isolation, safety abstention) become pytest tests that **gate releases** — "it works" becomes a proof, not a claim.

### `uv` — env & dependency manager
Fast installs + lockfile + workspace support for a Python monorepo. (Alternative: Poetry / pip-tools.)

---

## JavaScript / TypeScript toolchain

### `package.json` — the Node equivalent of `pyproject.toml`
Metadata + dependencies + scripts (`pnpm format`, `pnpm lint`). Workspace membership is the monorepo key.

### `pnpm` workspaces — shared deps, one install
`pnpm-workspace.yaml` declares members (`apps/*`, `packages/*`) as one workspace: a single install, dependencies **shared** via a content-addressed store (each package version stored **once** on disk, symlinked). Lets `apps/web` import `packages/common` directly — the point of a monorepo ([ADR 0006](../../adr/0006-monorepo.md)). (Alternative: npm/yarn workspaces, Turborepo on top.)

### `prettier` — the JS/TS formatter (= `ruff format`)
On the TS side, formatter and linter are **separate tools** (unlike ruff). `.prettierrc.json` fixes quotes/commas/width → everyone formats identically, automatically.

### `eslint` 9 flat config — the JS/TS linter (= `ruff check`)
Catches errors TypeScript's type-checker doesn't (unused vars, missing `await`, bad React hooks deps). **Flat config** (`eslint.config.mjs`) is ESLint 9's new format — a composable JS array (`js.configs.recommended`, then `tseslint.configs.recommended`) replacing the old cascading `.eslintrc`.

### `tsconfig.base.json` — shared compiler contract
Each app `extends` it. Key options:
- `"strict": true` — non-negotiable; forces handling `null`/`undefined`, bans implicit `any`. ~80% of TypeScript's value.
- `"noUncheckedIndexedAccess": true` — `array[i]` is typed `T | undefined`, forcing a check before use.

Without `strict`, TypeScript is "JavaScript with decorative annotations."

---

## Why two toolchains (Python + TS)
IKIP is **polyglot by design**: backend/services in Python (FastAPI, Dagster, RAG), frontend in TypeScript (Next.js). Each ecosystem has native tools; the monorepo makes them coexist — `pyproject.toml` governs Python, `package.json` governs TS, and **CI runs both**. The cost of "best tool per language" instead of one language.

## Who does what (summary)
| Need | Python | TypeScript |
|---|---|---|
| Central config | `pyproject.toml` | `package.json` |
| Format (cosmetic) | `ruff format` | `prettier` |
| Lint (correctness) | `ruff check` | `eslint` |
| Tests | `pytest` | (later, e.g. vitest) |
| Deps / monorepo | `uv` | `pnpm` workspaces |
| Compiler / types | (Pydantic at boundaries) | `tsconfig.base.json` |

## Gotcha seen in IKIP
Ruff initially linted the **diagram-as-code generators** and illustrative LLD code blocks under `docs/`. Fix: `extend-exclude = ["docs"]` — lint **application code**, not documentation artifacts (generators verified by rendering, not by style). See [MISSION-001/decisions.md](../missions/MISSION-001/decisions.md) D2.

## See also
- [MISSION-001](../missions/MISSION-001/mission.md) — where this tooling was set up.
- [ADR 0006](../../adr/0006-monorepo.md) (monorepo) · [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md) (ports shared via `packages/common`).
