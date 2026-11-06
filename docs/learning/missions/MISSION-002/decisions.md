# MISSION-002 — Decisions

## D1 — No Docker Compose; Story 1.2 = config + connectivity
- **Problem:** with Neon/R2/Redis Cloud/Langfuse managed, is a local Docker Compose still needed?
- **Choice:** drop it. The app connects to managed services via `.env`; Docker's real value (hermetic test DBs) is deferred to a **CI Postgres service container** (Story 1.3/1.5).
- **Why here:** everything managed already works; a local Compose would duplicate it and add a redundant MinIO (R2 is free). Simpler, honest.
- **Alternative:** minimal Compose (Postgres+Redis) for local tests / offline.
- **Trade-off:** no out-of-the-box offline mode; integration tests need the CI service container (or a one-off `docker run postgres`) rather than a committed Compose.
- **Switch when:** frequent offline work, or local integration testing against a persistent local DB becomes routine → add a Compose (the ports make it a config switch).

## D2 — Pydantic `BaseSettings` for config
- **Choice:** `pydantic-settings.BaseSettings` loading from env/`.env`, in `packages/common`.
- **Why here:** typed + validated config, fail-fast on missing required, one shared module for api + services; `SecretStr` keeps secrets out of logs/repr.
- **Alternative:** raw `os.environ` / `python-dotenv` only.
- **Trade-off:** a dependency + a class vs. ad-hoc dict access — worth it for validation and type safety.
- **Switch when:** never, at this scale — this is the standard.

## D3 — Doctor deps as a `doctor` dependency-group, lazy-imported
- **Choice:** boto3/psycopg/redis/httpx live in a root `doctor` group; `doctor.py` imports them lazily and reports SKIPPED if absent.
- **Why here:** importing config must stay light (no heavy clients pulled in for a settings read); the doctor is a dev/ops convenience, not core.
- **Alternative:** put them in `ikip-common` core deps.
- **Trade-off:** must pass `--group doctor` to run the doctor; core stays lean.
- **Switch when:** a backend client becomes a core runtime dependency (then it moves to the owning package's deps, e.g. psycopg in the DB adapter).

## D4 — CI on uv; run hermetic pytest; harden the secret guard
- **Choice:** CI uses `astral-sh/setup-uv`, `uv sync`, `uv run ruff`, `uv run pytest packages`. Secret guard rewritten to match `KEY=value` assignments + PEM blocks, not identifiers.
- **Why here:** one toolchain (uv) locally and in CI; the old guard would false-positive on `alias="AZURE_OPENAI_API_KEY"` in `config.py`.
- **Alternative:** keep pip + a looser grep.
- **Trade-off:** a secret-looking value assigned in code still trips the guard (intended).
- **Switch when:** adopt a dedicated secret scanner (gitleaks) in Story 6.4.

## D5 — Node pinned to 22 LTS
- **Choice:** `engines.node >=22`, `.nvmrc = 22`.
- **Why here:** Node 22 is the current LTS ("Jod"); Node 20 is deprecated (Oct 2026). Pinning avoids "works on my machine".
- **Alternative:** `>=20`.
- **Trade-off:** contributors need Node 22+.
- **Switch when:** Node 24 becomes the stable LTS target for this project.
