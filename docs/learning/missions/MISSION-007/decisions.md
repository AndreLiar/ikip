# MISSION-007 — Decisions

## D1 — Thin Dagster wrapper over pure logic (keep CI fast)
- **Choice:** connectors + `ingest_documents` are Dagster-free, injected collaborators; `definitions.py` is the only file importing Dagster.
- **Why here:** core logic unit-tests in the fast `validate` job without installing Dagster or running a daemon; Dagster stays an optional dep (`dagster` group / package extra), installed only in the image.
- **Alternative:** put the work inside `@asset`.
- **Trade-off:** one extra indirection; worth it for test speed + swappable orchestration.

## D2 — Connector fetches bytes only; parsing deferred to Story 2.3
- **Choice:** a connector yields `SourceDocument(source_uri, content, content_type)`; no PDF/CSV parsing here.
- **Why here:** at ingestion, every format is just bytes; separating fetch from parse keeps each story focused and the raw tier format-agnostic.

## D3 — Authorization + licensing gate in `SourceConfig`
- **Choice:** `ensure_allowed()` raises unless `authorized and license` — called before any fetch.
- **Why here:** enforces the data-sources licensing gate (AC3, Story 6.5) structurally; you can't crawl a source you didn't clear.

## D4 — Checksum-based change detection; raw never overwritten
- **Choice:** sha256 of content; skip if the same `(source_uri → checksum)` was seen; the raw key includes the checksum, so a changed doc becomes a new object.
- **Why here:** idempotent re-runs (AC4); preserves original evidence (NFR15). The seen-store is in-memory for now; Story 2.5 makes it DB-backed via document versions.

## D5 — `@asset` context left unannotated
- **Lesson:** `from __future__ import annotations` stringizes the `context` annotation and Dagster's validator rejects it. Leaving `context` unannotated (or not using future-annotations in that file) fixes it. Found via the in-process materialize smoke test.

## D6 — Dagster runs via Docker image in dev; prod deferred
- Per [ADR 0002](../../../adr/0002-dual-orchestration-dagster-langgraph.md): dev = `Dockerfile.dagster` (webserver+daemon); prod hosting (Container Apps self-host vs Prefect Cloud vs lighter) decided later. The always-on daemon is the prod cost.
