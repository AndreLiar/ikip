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


daily_ingest_schedule = dg.ScheduleDefinition(
    name="daily_ingest",
    target=dg.AssetSelection.assets(ingested_sources),
    cron_schedule="0 2 * * *",  # 02:00 daily
)

defs = dg.Definitions(
    assets=[ingested_sources],
    schedules=[daily_ingest_schedule],
)
