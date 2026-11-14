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
    description="Extract + clean + validate (PyMuPDF/OCR) each PENDING raw artifact into a "
    "curated artifact in R2 (Story 2.3/2.4). The heavy extraction lives HERE.",
)
def curated_documents(context) -> dg.MaterializeResult:  # noqa: ANN001
    # The real extract/clean/validate stage (Story 2.6 faithful lineage): for each PENDING
    # job not yet curated, pull its raw artifact from R2, run curate_to_storage (PyMuPDF →
    # OCR → clean → layout), write the curated+layout artifacts, and record their keys on the
    # job. NO versioning here — so versioning can re-run WITHOUT re-OCR. The heavy extraction
    # runs OUTSIDE any DB transaction (it can take minutes under hybrid/OCR); the DB is touched
    # only in two short per-doc transactions (read inputs, write keys) → resumable and immune to
    # Neon's idle-in-transaction timeout.
    import uuid

    from ikip_common.db import make_session_factory
    from ikip_common.db.models import IngestionJob, IngestionState
    from ikip_common.storage import R2ObjectStorage
    from sqlalchemy import select

    from ikip_ingestion.curate import curate_to_storage

    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to curate.")
        return dg.MaterializeResult(metadata={"stage": "curated", "curated": 0})

    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    storage = R2ObjectStorage()
    curated = failed = 0
    session_factory = make_session_factory()

    with session_factory() as session:
        job_ids = list(
            session.execute(
                select(IngestionJob.id).where(
                    IngestionJob.tenant_id == tenant_id,
                    IngestionJob.state == IngestionState.pending,
                    IngestionJob.raw_object_key.is_not(None),
                    IngestionJob.curated_object_key.is_(None),  # not yet curated
                )
            ).scalars()
        )

    for job_id in job_ids:
        # 1) SHORT read tx, then release the connection. The extraction below can take MINUTES
        #    (hybrid/OCR/Docling); running it inside an open transaction lets Neon kill the
        #    connection (idle-in-transaction timeout) before the UPDATE commits.
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            raw_key, source, content_type = job.raw_object_key, job.source, job.content_type

        # 2) Heavy extract OUTSIDE any transaction. On failure the job stays pending → retried.
        try:
            raw = storage.get(raw_key)
            key, layout_key = curate_to_storage(
                tenant_id=tenant_id,
                raw_bytes=raw,
                source=source,
                storage=storage,
                content_type=content_type,
            )
        except Exception as exc:  # noqa: BLE001 — record + keep going
            failed += 1
            context.log.error("curation failed for job %s: %s", job_id, exc)
            continue

        # 3) SHORT write tx: persist the curated keys (milliseconds).
        with session_factory() as session:
            job = session.get(IngestionJob, job_id)
            job.curated_object_key = key
            job.layout_object_key = layout_key
            session.commit()
        curated += 1

    context.log.info("curated %d documents (%d failed)", curated, failed)
    return dg.MaterializeResult(metadata={"stage": "curated", "curated": curated, "failed": failed})


@dg.asset(
    deps=[curated_documents],
    description="Deduplicate + version curated documents into DocumentVersions (Story 2.5); "
    "no extraction — reads the curated artifact. Emits a quality report.",
)
def document_versions(context) -> dg.MaterializeResult:  # noqa: ANN001
    # Versioning-only stage (Story 2.6): for each job that has a curated artifact but isn't
    # yet versioned, publish a deduplicated DocumentVersion FROM the curated artifact (no
    # OCR). Supersedes prior versions + invalidates the answer cache (ADR 0009). Idempotent;
    # commits PER DOCUMENT (resumable, survives serverless connection recycling).
    import uuid

    from ikip_common.cache import build_cache
    from ikip_common.db import make_session_factory
    from ikip_common.db.documents import DocumentRepository
    from ikip_common.db.ingestion import IngestionJobRepository
    from ikip_common.db.models import IngestionJob, IngestionState
    from ikip_common.storage import R2ObjectStorage
    from sqlalchemy import select

    from ikip_ingestion.curate import version_from_curated
    from ikip_ingestion.quality_report import DataQualityReport

    report = DataQualityReport()
    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to version.")
        return dg.MaterializeResult(metadata={"stage": "versions", **report.as_dict()})

    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    storage = R2ObjectStorage()
    cache = build_cache()
    session_factory = make_session_factory()

    with session_factory() as session:
        job_ids = list(
            session.execute(
                select(IngestionJob.id).where(
                    IngestionJob.tenant_id == tenant_id,
                    IngestionJob.state == IngestionState.pending,
                    IngestionJob.curated_object_key.is_not(None),  # curated, awaiting versioning
                )
            ).scalars()
        )

    for job_id in job_ids:  # per-doc transaction
        with session_factory() as session:
            repo = DocumentRepository(session, tenant_id)
            jobs = IngestionJobRepository(session, tenant_id)
            job = session.get(IngestionJob, job_id)
            report.total += 1
            jobs.transition(job, IngestionState.running)
            try:
                res = version_from_curated(
                    tenant_id=tenant_id,
                    repo=repo,
                    cache=cache,
                    storage=storage,
                    curated_object_key=job.curated_object_key,
                    layout_object_key=job.layout_object_key,
                    source=job.source,
                    source_object_key=job.raw_object_key,
                )
                jobs.transition(job, IngestionState.succeeded)
                session.commit()
                report.succeeded += 1
                if res.skipped_duplicate:
                    report.duplicates += 1
                elif res.outcome and res.outcome.created_document:
                    report.new_documents += 1
                else:
                    report.new_versions += 1
            except Exception as exc:  # noqa: BLE001 — dead-letter, keep going
                session.rollback()
                with session_factory() as s2:  # record failure in its own tx
                    IngestionJobRepository(s2, tenant_id).transition(
                        s2.get(IngestionJob, job_id),
                        IngestionState.failed,
                        error_info={"error": str(exc)},
                    )
                    s2.commit()
                report.failed += 1
                context.log.error("versioning failed for job %s: %s", job_id, exc)

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
    # Closes the build-time loop (Epic 2 -> Epic 3): for each CURRENT version with curated
    # text in R2, chunk -> persist Section/Chunk -> embed into pgvector. index_version is
    # idempotent/rerun-safe. Commits PER VERSION so a long run survives serverless
    # connection recycling (a single 19-min transaction gets its connection dropped by Neon)
    # and is resumable — the scale fix.
    if not _DEFAULT_TENANT:
        context.log.warning("IKIP_INGEST_TENANT_ID not set — nothing to index.")
        return dg.MaterializeResult(metadata={"stage": "embedded", "versions": 0})

    import json
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
    indexed_versions = total_chunks = failed = 0
    session_factory = make_session_factory()

    with session_factory() as session:
        version_ids = list(
            session.execute(
                select(DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    Document.tenant_id == tenant_id,
                    DocumentVersion.is_current.is_(True),
                    DocumentVersion.curated_object_key.is_not(None),
                )
            ).scalars()
        )

    for dv_id in version_ids:  # one short transaction per version
        with session_factory() as session:
            dv = session.get(DocumentVersion, dv_id)
            try:
                curated_text = storage.get(dv.curated_object_key).decode("utf-8")
                layout_regions = (
                    json.loads(storage.get(dv.layout_object_key).decode("utf-8"))
                    if dv.layout_object_key
                    else None
                )
                report = index_version(
                    session, tenant_id, dv.id, curated_text, client, layout_regions=layout_regions
                )
                session.commit()
                indexed_versions += 1
                total_chunks += report.chunks_created
            except Exception as exc:  # noqa: BLE001 — isolate per-version failures
                session.rollback()
                failed += 1
                context.log.error("indexing failed for version %s: %s", dv_id, exc)

    context.log.info(
        "indexed %d versions, %d new chunks (%d failed)", indexed_versions, total_chunks, failed
    )
    return dg.MaterializeResult(
        metadata={
            "stage": "embedded",
            "versions": indexed_versions,
            "chunks": total_chunks,
            "failed": failed,
        }
    )


# --- Data-quality asset checks (Story 2.6 / RAG best-practice): fail BEFORE bad vectors
# pollute retrieval. These caught the real class of bug we hit (embedding dim mismatch).


@dg.asset_check(
    asset=embedded_chunks,
    description="Every embedding's dimension matches the pgvector schema (EMBEDDING_DIM).",
)
def embedding_dimension_matches_schema() -> dg.AssetCheckResult:  # noqa: ANN201
    import uuid

    from ikip_common.db import make_session_factory
    from ikip_common.db.models import EMBEDDING_DIM, Embedding
    from sqlalchemy import func, select

    if not _DEFAULT_TENANT:
        return dg.AssetCheckResult(passed=True, metadata={"skipped": "no tenant"})
    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    with make_session_factory()() as session:
        total = session.execute(
            select(func.count()).select_from(Embedding).where(Embedding.tenant_id == tenant_id)
        ).scalar_one()
        wrong = session.execute(
            select(func.count())
            .select_from(Embedding)
            .where(
                Embedding.tenant_id == tenant_id,
                func.vector_dims(Embedding.vector) != EMBEDDING_DIM,
            )
        ).scalar_one()
    return dg.AssetCheckResult(
        passed=wrong == 0,
        severity=dg.AssetCheckSeverity.ERROR,
        metadata={"expected_dim": EMBEDDING_DIM, "embeddings": total, "wrong_dim": wrong},
    )


@dg.asset_check(asset=embedded_chunks, description="No empty/whitespace-only chunks were indexed.")
def chunks_non_empty() -> dg.AssetCheckResult:  # noqa: ANN201
    import uuid

    from ikip_common.db import make_session_factory
    from ikip_common.db.models import Chunk
    from sqlalchemy import func, select

    if not _DEFAULT_TENANT:
        return dg.AssetCheckResult(passed=True, metadata={"skipped": "no tenant"})
    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    with make_session_factory()() as session:
        empty = session.execute(
            select(func.count())
            .select_from(Chunk)
            .where(Chunk.tenant_id == tenant_id, func.length(func.trim(Chunk.content)) == 0)
        ).scalar_one()
    return dg.AssetCheckResult(
        passed=empty == 0, severity=dg.AssetCheckSeverity.WARN, metadata={"empty_chunks": empty}
    )


_ALL_ASSETS = [ingested_sources, curated_documents, document_versions, embedded_chunks]

daily_ingest_schedule = dg.ScheduleDefinition(
    name="daily_ingest",
    # Materialize the whole pipeline (raw -> curated -> versions -> embeddings) nightly.
    target=dg.AssetSelection.assets(*_ALL_ASSETS),
    cron_schedule="0 2 * * *",  # 02:00 daily
)

# Processing pipeline (curate -> version -> embed) as a job the sensor can request. Excludes
# `ingested_sources` (HTTP-connector acquisition) — the sensor reacts to jobs already queued.
ingest_processing_job = dg.define_asset_job(
    "ingest_processing",
    selection=dg.AssetSelection.assets(curated_documents, document_versions, embedded_chunks),
    description="Curate → version → embed the pending ingestion jobs.",
)


def _watermark_decision(latest, cursor: str | None):  # noqa: ANN001, ANN201
    """Pure trigger decision (DB-free, unit-testable): given the latest pending-job timestamp
    and the sensor's cursor, return (RunRequest | SkipReason, new_cursor). Fires once per new
    batch — a newer `created_at` than the cursor = new work; the same = a run already requested."""
    if latest is None:
        return dg.SkipReason("no pending, not-yet-curated jobs"), cursor
    watermark = latest.isoformat()
    if cursor == watermark:
        return dg.SkipReason("run already requested for this backlog"), cursor
    return dg.RunRequest(run_key=watermark), watermark


@dg.sensor(
    job=ingest_processing_job,
    minimum_interval_seconds=30,
    default_status=dg.DefaultSensorStatus.STOPPED,  # opt-in; enable in the UI (ADR 0025)
    description="Near-real-time ingestion: request a pipeline run when new PENDING, not-yet-"
    "curated jobs appear — event-shaped trigger without a message queue (ADR 0025).",
)
def pending_jobs_sensor(context):  # noqa: ANN001, ANN201 — Dagster introspects the context
    # Watch the ingestion_job table (the real async queue); the latest pending job's created_at
    # is the watermark. The decision itself is pure (`_watermark_decision`) → testable DB-free.
    import uuid

    from ikip_common.db import make_session_factory
    from ikip_common.db.models import IngestionJob, IngestionState
    from sqlalchemy import func, select

    if not _DEFAULT_TENANT:
        return dg.SkipReason("IKIP_INGEST_TENANT_ID not set")

    tenant_id = uuid.UUID(_DEFAULT_TENANT)
    with make_session_factory()() as session:
        latest = session.execute(
            select(func.max(IngestionJob.created_at)).where(
                IngestionJob.tenant_id == tenant_id,
                IngestionJob.state == IngestionState.pending,
                IngestionJob.curated_object_key.is_(None),
            )
        ).scalar()

    decision, new_cursor = _watermark_decision(latest, context.cursor)
    if isinstance(decision, dg.RunRequest):
        context.update_cursor(new_cursor)
    return decision


defs = dg.Definitions(
    assets=_ALL_ASSETS,
    asset_checks=[embedding_dimension_matches_schema, chunks_non_empty],
    schedules=[daily_ingest_schedule],
    jobs=[ingest_processing_job],
    sensors=[pending_jobs_sensor],
)
