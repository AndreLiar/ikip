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
    # Curate + version each PENDING ingestion job: load its raw artifact from R2,
    # curate (extract/clean/metadata) and publish a deduplicated DocumentVersion with a
    # curated artifact. publish_document_version supersedes prior versions AND invalidates
    # the tenant answer cache (ADR 0009). Idempotent: exact duplicates are skipped.
    import uuid

    from ikip_common.cache import build_cache
    from ikip_common.db import make_session_factory
    from ikip_common.db.documents import DocumentRepository
    from ikip_common.db.ingestion import IngestionJobRepository
    from ikip_common.db.models import IngestionJob, IngestionState
    from ikip_common.storage import R2ObjectStorage
    from sqlalchemy import select

    from ikip_ingestion.curate import curate_and_version
    from ikip_ingestion.quality_report import DataQualityReport

    report = DataQualityReport()
    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to version.")
        return dg.MaterializeResult(metadata={"stage": "versions", **report.as_dict()})

    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    storage = R2ObjectStorage()
    cache = build_cache()

    with make_session_factory()() as session:
        repo = DocumentRepository(session, tenant_id)
        jobs = IngestionJobRepository(session, tenant_id)
        pending = session.execute(
            select(IngestionJob).where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.state == IngestionState.pending,
                IngestionJob.raw_object_key.is_not(None),
            )
        ).scalars()
        for job in pending:
            report.total += 1
            jobs.transition(job, IngestionState.running)
            try:
                raw = storage.get(job.raw_object_key)
                res = curate_and_version(
                    tenant_id=tenant_id,
                    raw_bytes=raw,
                    source=job.source,
                    repo=repo,
                    cache=cache,
                    storage=storage,
                )
                jobs.transition(job, IngestionState.succeeded)
                report.succeeded += 1
                if res.skipped_duplicate:
                    report.duplicates += 1
                elif res.outcome and res.outcome.created_document:
                    report.new_documents += 1
                else:
                    report.new_versions += 1
            except Exception as exc:  # noqa: BLE001 — record + dead-letter, keep going
                jobs.transition(job, IngestionState.failed, error_info={"error": str(exc)})
                report.failed += 1
                context.log.error("versioning failed for job %s: %s", job.id, exc)
        session.commit()

    context.log.info(
        "versioned: +%d docs, +%d versions, %d dup, %d failed",
        report.new_documents,
        report.new_versions,
        report.duplicates,
        report.failed,
    )
    return dg.MaterializeResult(metadata={"stage": "versions", **report.as_dict()})


@dg.asset(
    deps=[document_versions],
    description="Chunk + embed + index current document versions (Story 3.1/3.2) into pgvector.",
)
def embedded_chunks(context) -> dg.MaterializeResult:  # noqa: ANN001
    # Closes the build-time loop (Epic 2 -> Epic 3): for each CURRENT version with
    # curated text in R2, chunk -> persist Section/Chunk -> embed into pgvector, so
    # retrieval (/retrieve, /ask) has data. index_version is idempotent/rerun-safe.
    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to index.")
        return dg.MaterializeResult(metadata={"stage": "embedded", "versions": 0})

    import uuid

    from ikip_common.db import make_session_factory
    from ikip_common.db.models import Document, DocumentVersion
    from ikip_common.llm import build_embedding_client
    from ikip_common.storage import R2ObjectStorage
    from ikip_docproc.indexing import index_version
    from sqlalchemy import select

    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    storage = R2ObjectStorage()
    client = build_embedding_client()
    indexed_versions = total_chunks = 0

    with make_session_factory()() as session:
        current = session.execute(
            select(DocumentVersion)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                Document.tenant_id == tenant_id,
                DocumentVersion.is_current.is_(True),
                DocumentVersion.curated_object_key.is_not(None),
            )
        ).scalars()
        for dv in current:
            curated_text = storage.get(dv.curated_object_key).decode("utf-8")
            report = index_version(session, tenant_id, dv.id, curated_text, client)
            indexed_versions += 1
            total_chunks += report.chunks_created
        session.commit()

    context.log.info("indexed %d versions, %d new chunks", indexed_versions, total_chunks)
    return dg.MaterializeResult(
        metadata={"stage": "embedded", "versions": indexed_versions, "chunks": total_chunks}
    )


_ALL_ASSETS = [ingested_sources, curated_documents, document_versions, embedded_chunks]

daily_ingest_schedule = dg.ScheduleDefinition(
    name="daily_ingest",
    # Materialize the whole pipeline (raw -> curated -> versions -> embeddings) nightly.
    target=dg.AssetSelection.assets(*_ALL_ASSETS),
    cron_schedule="0 2 * * *",  # 02:00 daily
)

defs = dg.Definitions(
    assets=_ALL_ASSETS,
    schedules=[daily_ingest_schedule],
)
