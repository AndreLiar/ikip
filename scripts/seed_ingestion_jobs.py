"""Seed PENDING IngestionJob rows from the fetched corpus manifest (feeds the Dagster DAG).

The real `ingested_sources` asset creates ingestion jobs from configured HTTP sources; the
NTRS corpus was fetched to R2 by scripts/fetch_public_domain_corpus.py (custom public-domain
API), so this bridges it into the SAME pipeline by creating the jobs via the pipeline's own
`IngestionJobRepository`. The Story-6.5 licensing gate is enforced as a PRECONDITION: only
`is_license_allowed(rights)` documents become jobs. Idempotent: a raw_object_key already
jobbed is skipped.

    uv run --group doctor python scripts/seed_ingestion_jobs.py --limit 20     # validation
    uv run --group doctor python scripts/seed_ingestion_jobs.py                 # the rest (500)

Prints the tenant UUID to export as IKIP_INGEST_TENANT_ID for the Dagster run.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

# Stable dedicated tenant for the NTRS public-domain corpus (tenant #1). A second corpus
# (different sector) goes to its OWN tenant — pass --tenant/--tenant-name/--manifest. This is
# exactly how multi-tenancy is exercised: each corpus is isolated by tenant_id (NFR10).
CORPUS_TENANT = uuid.UUID("c0f90000-0000-4000-8000-0000000000a1")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="eval-results/corpus_manifest.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = all entries")
    ap.add_argument("--tenant", default=str(CORPUS_TENANT))
    ap.add_argument("--tenant-name", default="corpus-ntrs", help="name for a NEW tenant row")
    args = ap.parse_args()

    from ikip_common.db import make_session_factory
    from ikip_common.db.ingestion import IngestionJobRepository
    from ikip_common.db.models import IngestionJob, Tenant
    from ikip_common.db.retention import is_license_allowed
    from sqlalchemy import select

    tenant_id = uuid.UUID(args.tenant)
    entries = json.loads(Path(args.manifest).read_text())
    if args.limit:
        entries = entries[: args.limit]

    created = skipped_exist = skipped_license = 0
    with make_session_factory()() as session:
        if session.get(Tenant, tenant_id) is None:
            session.add(Tenant(id=tenant_id, name=args.tenant_name))
            session.flush()
        existing = set(
            session.execute(
                select(IngestionJob.raw_object_key).where(IngestionJob.tenant_id == tenant_id)
            ).scalars()
        )
        jobs = IngestionJobRepository(session, tenant_id)
        for e in entries:
            if not is_license_allowed(e.get("rights")):  # 6.5 gate as ingestion precondition
                skipped_license += 1
                continue
            if e["r2_key"] in existing:
                skipped_exist += 1
                continue
            # content_type drives extraction routing (PDF→PyMuPDF/hybrid, Office→Docling); a
            # mixed-format manifest carries it per entry, defaulting to PDF.
            jobs.create(
                source=e["source"],
                raw_object_key=e["r2_key"],
                content_type=e.get("content_type", "application/pdf"),
            )
            created += 1
        session.commit()

    print(f"tenant {tenant_id}")
    print(
        f"created={created} PENDING jobs; skipped(already-jobbed)={skipped_exist}; "
        f"skipped(license-gate)={skipped_license}"
    )
    print(f"\nexport IKIP_INGEST_TENANT_ID={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
