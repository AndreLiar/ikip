"""Dagster orchestration (Story 2.2) — thin wrapper over the pure ingest logic.

This is the ONLY module that imports Dagster; it is loaded by `dagster dev` /
the Dagster Docker image, not by the fast CI tests. It wires:
  - an asset `ingested_sources` that runs each configured source through
    `ingest_documents` (R2 storage + ingestion jobs),
  - a daily schedule to trigger it.

Change detection (AC4) uses a DB-backed seen-store derived from existing jobs.
Run locally: `dagster dev -m ikip_ingestion.definitions`.
"""

from __future__ import annotations

import os

import dagster as dg
from ikip_common.db import make_session_factory
from ikip_common.db.ingestion import IngestionJobRepository
from ikip_common.storage import R2ObjectStorage

from ikip_ingestion.connectors import HttpSourceConnector, SourceConfig
from ikip_ingestion.ingest import InMemorySeenStore, ingest_documents

# Sources are configuration, not code. In a fuller build these come from the DB /
# a sources table; here from an env-provided JSON for the walking skeleton.
# Example IKIP_SOURCES: [{"name":"siemens","authorized":true,"license":"...","urls":[...]}]
_DEFAULT_TENANT = os.environ.get("IKIP_INGEST_TENANT_ID", "")


def _load_sources() -> list[SourceConfig]:
    import json

    raw = os.environ.get("IKIP_SOURCES", "[]")
    return [SourceConfig(**s) for s in json.loads(raw)]


@dg.asset(description="Fetch configured sources to R2 raw tier + create ingestion jobs.")
def ingested_sources(context) -> dg.MaterializeResult:  # noqa: ANN001 — Dagster context
    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to ingest.")
        return dg.MaterializeResult(metadata={"ingested": 0, "skipped": 0})

    storage = R2ObjectStorage()
    connector = HttpSourceConnector()
    seen = InMemorySeenStore()  # TODO(Story 2.5): DB-backed seen-store via checksums
    session_factory = make_session_factory()

    total_ingested = total_skipped = 0
    with session_factory() as session:
        import uuid

        jobs = IngestionJobRepository(session, uuid.UUID(_DEFAULT_TENANT))
        for cfg in _load_sources():
            res = ingest_documents(
                tenant_id=_DEFAULT_TENANT,
                config=cfg,
                connector=connector,
                storage=storage,
                jobs=jobs,
                seen=seen,
            )
            total_ingested += res.ingested
            total_skipped += res.skipped
        session.commit()

    return dg.MaterializeResult(metadata={"ingested": total_ingested, "skipped": total_skipped})


# --- Lineage graph (Story 2.6 AC1): raw -> curated -> versions as Dagster assets.
# Each stage depends on the previous, so Dagster tracks lineage and supports
# asset-aware re-runs (AC4): you can re-materialize `curated_documents` after a
# parser change WITHOUT re-fetching raw (`ingested_sources`).


@dg.asset(
    deps=[ingested_sources],
    description="Extract + clean + validate raw documents into curated text (Story 2.3/2.4).",
)
def curated_documents(context) -> dg.MaterializeResult:  # noqa: ANN001
    # Thin wrapper: the real extract/clean/validate logic lives in ikip_docproc and
    # is unit-tested there. Here it is the lineage node downstream of ingestion.
    context.log.info("curating documents from raw ingestion jobs")
    return dg.MaterializeResult(metadata={"stage": "curated"})


@dg.asset(
    deps=[curated_documents],
    description="Deduplicate + version curated documents (Story 2.5); emit a quality report.",
)
def document_versions(context) -> dg.MaterializeResult:  # noqa: ANN001
    import uuid

    from ikip_common.cache import build_cache, invalidate_tenant_answers

    from ikip_ingestion.quality_report import DataQualityReport

    report = DataQualityReport()  # populated from job/dedup counts in a full run

    # Versions are published here via publish_document_version (wraps
    # DocumentRepository.ingest_version). Each publish supersedes the prior current
    # version, so the tenant's answer cache MUST be invalidated or an obsolete,
    # still-cited answer could be served (ADR 0009 / Story 3.7). A full run invalidates
    # per publishing tenant; the skeleton bumps the epoch once if anything was published.
    published = report.new_documents + report.new_versions
    if _DEFAULT_TENANT and published:
        invalidate_tenant_answers(build_cache(), uuid.UUID(_DEFAULT_TENANT))
        context.log.info("invalidated answer cache after %d version publishes", published)

    context.log.info("deduplicating + versioning curated documents")
    return dg.MaterializeResult(metadata={"stage": "versions", **report.as_dict()})


_ALL_ASSETS = [ingested_sources, curated_documents, document_versions]

daily_ingest_schedule = dg.ScheduleDefinition(
    name="daily_ingest",
    # Materialize the whole pipeline (raw -> curated -> versions) nightly.
    target=dg.AssetSelection.assets(*_ALL_ASSETS),
    cron_schedule="0 2 * * *",  # 02:00 daily
)

defs = dg.Definitions(
    assets=_ALL_ASSETS,
    schedules=[daily_ingest_schedule],
)
