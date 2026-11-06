# MISSION-001 — Reproduction tutorial

Reproduce the monorepo scaffold from an empty repo, without an AI agent.

## Prerequisites
- git; Python 3.12+; Node ≥ 20; (optional) `uv`, `pnpm`.
- A repo with `docs/` and a protected `main` (branch → PR workflow).

## Steps

1. **Branch off main**
   ```bash
   git checkout -b feat/epic-1-story-1.1-monorepo
   ```

2. **Create the directory skeleton** (git ignores empty dirs, so add `.gitkeep`)
   ```bash
   for d in apps/web apps/api \
            services/{ingestion,document-processing,indexing,retrieval,evaluation} \
            packages/{common,ai-clients} \
            infrastructure/docker infrastructure/terraform/{modules,environments/{dev,staging,prod}} \
            tests/{unit,integration,retrieval,security,performance} \
            datasets/evaluation ; do
     mkdir -p "$d" && touch "$d/.gitkeep"
   done
   ```

3. **Python tooling** — create `pyproject.toml` with a `[tool.ruff]` block (lint rules + `line-length`), `extend-exclude = ["docs"]`, and a `[tool.pytest.ini_options]` block. See the committed file for the exact content.

4. **JS/TS tooling** — create `package.json` (pnpm workspaces + format/lint scripts), `pnpm-workspace.yaml` (`apps/*`, `packages/*`), `.prettierrc.json`, `.prettierignore`, `tsconfig.base.json`, `eslint.config.mjs` (flat config).

5. **Verify lint/format locally** (expected: both green)
   ```bash
   python3 -m venv /tmp/rv && /tmp/rv/bin/pip install -q ruff
   /tmp/rv/bin/ruff check .          # -> All checks passed!
   /tmp/rv/bin/ruff format --check . # -> formatted
   rm -rf /tmp/rv
   ```

6. **Wire CI** — in `.github/workflows/ci.yml`, add before existing steps:
   ```yaml
   - run: pip install --quiet ruff
   - run: ruff check .
   - run: ruff format --check .
   ```

7. **Document conventions** — add Repository structure, Development setup, Contribution & branching sections to `README.md`.

8. **Open a PR, wait for CI green, squash-merge**
   ```bash
   git add -A && git commit -m "feat(epic-1): monorepo scaffold, tooling & conventions (Story 1.1)"
   git push -u origin HEAD
   gh pr create --fill
   gh pr checks --watch
   gh pr merge --squash --delete-branch
   ```

## Common mistakes & troubleshooting
- **Empty dirs vanish** → you forgot `.gitkeep`. Git doesn't track empty directories.
- **CI red on ruff** → run `ruff check .` / `ruff format .` locally first; `ruff format .` (no `--check`) auto-fixes.
- **Ruff lints your docs/diagram scripts** → ensure `extend-exclude = ["docs"]` in `pyproject.toml` (decision D2).
- **`gh pr merge` blocked** → the `validate` check must be green (branch protection); wait for CI.

## Recovery
Additive change only — no data touched. To undo: `git checkout main && git branch -D <branch>` (before merge) or revert the squash commit (after).
