# MISSION-007 — Reproduction tutorial

Add source connectors + a Dagster-orchestrated ingestion asset.

## Prerequisites
- MISSIONs 001–006; `.env` (R2 + Neon dev branch); `uv`; Docker (to run Dagster).

## Steps

1. **Package** `services/ingestion/pyproject.toml` — `name = ikip-ingestion`, deps `[ikip-common, httpx]`, and `[project.optional-dependencies] dagster = ["dagster>=1.9,<1.12", "dagster-webserver>=1.9,<1.12"]`. Register in root `[tool.uv.workspace].members`, `dev` group, `[tool.uv.sources]`; add a root `dagster` dependency-group; add `services` to `testpaths` and CI `pytest apps packages services`.

2. **Connectors** `connectors.py` — `SourceConfig(name, authorized, license, urls)` with `ensure_allowed()` (raise `UnauthorizedSourceError` unless authorized+licensed); `SourceDocument(source_uri, content, content_type)`; `SourceConnector` Protocol; `HttpSourceConnector` with an injectable `Fetcher` (`HttpFetcher` uses httpx).

3. **Ingest** `ingest.py` — `ingest_documents(*, tenant_id, config, connector, storage, jobs, seen, docs=None)`: for each doc → sha256 checksum → skip if `seen.seen_checksum(uri)==checksum` → store raw (`tier_key(raw, tenant, hash, checksum.bin)`) → `jobs.create(...)` → `seen.mark(...)`. Injected collaborators (no Dagster, no live services).

4. **Dagster wiring** `definitions.py` — `@dg.asset def ingested_sources(context): ...` (leave `context` unannotated!), a `dg.ScheduleDefinition(cron="0 2 * * *")`, and `dg.Definitions(assets=[...], schedules=[...])`. This is the only file importing `dagster`.

5. **Tests**
   ```bash
   uv run pytest apps packages services -q        # connectors+ingest run; dagster test skips
   uv run --group dagster pytest services/ingestion/tests/test_definitions.py -q   # 1 passed
   ```
   The dagster test does `dg.materialize([ingested_sources])` in-process (no daemon).

6. **Run Dagster** (UI at :3000)
   ```bash
   docker build -f services/ingestion/Dockerfile.dagster -t ikip-dagster .
   docker run --rm -p 3000:3000 --env-file .env ikip-dagster
   # or: uv run --group dagster dagster dev -m ikip_ingestion.definitions
   ```

## Common mistakes
- **Dagster rejects the `context` annotation** → remove `from __future__ import annotations` effect on it; leave `context` unannotated.
- **CI got slow / pulls Dagster** → keep Dagster an optional group/extra; core logic must not import it.
- **Overwriting raw on re-run** → put the checksum in the raw key; skip unchanged via the seen-store.
- **Crawling an uncleared source** → gate with `SourceConfig.ensure_allowed()`.
- **Secrets in the image** → pass `.env` at `docker run`.

## Recovery
Additive; revert branch/commit. No data touched.
