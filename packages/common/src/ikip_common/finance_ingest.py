"""Link financial facts to their source filings (Epic 8, Story 8.1 wiring, ADR 0030).

The fact store carries an `accession` (the SEC filing), but a figure's citation chain (FR16) is
only complete when it resolves `fact → document_version → document → page`. This wires it: each
**entity** becomes a `Document` ("<Entity> — SEC filings"), each unique **accession** a
`DocumentVersion` (revision = accession, publication_date = filed_date), and every fact is
persisted with `document_version_id` set. So a retrieved figure cites the actual filing, not just
a string.

Takes already-parsed fact records (the extractor lives in `ikip_docproc`; keeping the direction
clean — `ikip_common` never imports the service). Tenant-scoped, idempotent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select

from ikip_common.db.financial import persist_facts
from ikip_common.db.models import Document, DocumentVersion


def link_and_persist_facts(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    specs: Sequence[Any],
) -> dict:
    """Create the Document/DocumentVersion rows for the filings in `specs`, then persist the facts
    linked to their filing's version. Idempotent (reuses existing doc/version/facts). Returns
    counts. Caller commits."""
    if not specs:
        return {"documents": 0, "versions": 0, "facts": 0}

    docs_created = versions_created = facts_persisted = 0

    # One Document per entity (by CIK). Reuse if present.
    by_entity: dict[str, list[Any]] = {}
    for s in specs:
        by_entity.setdefault(s.entity_cik, []).append(s)

    for cik, entity_specs in by_entity.items():
        name = next((s.entity_name for s in entity_specs if s.entity_name), cik)
        doc = session.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.source == "SEC EDGAR",
                Document.title == f"{name} — SEC filings",
            )
        ).scalar_one_or_none()
        if doc is None:
            doc = Document(
                tenant_id=tenant_id,
                title=f"{name} — SEC filings",
                source="SEC EDGAR",
                type="financial-filings",
                rights="public-domain",  # US-government data (licensing gate, Story 6.5)
            )
            session.add(doc)
            session.flush()
            docs_created += 1

        # One DocumentVersion per accession (the specific filing).
        accns: dict[str, Any] = {}
        for s in entity_specs:
            accns.setdefault(s.accession, s)
        ver_by_accn: dict[str, uuid.UUID] = {}
        for accn, sample in accns.items():
            ver = session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == doc.id,
                    DocumentVersion.revision == accn,
                )
            ).scalar_one_or_none()
            if ver is None:
                ver = DocumentVersion(
                    document_id=doc.id,
                    revision=accn,
                    checksum=accn,  # accession uniquely identifies the filing
                    publication_date=sample.filed_date,
                    is_current=False,  # SEC filings are distinct periods, none "current"
                )
                session.add(ver)
                session.flush()
                versions_created += 1
            ver_by_accn[accn] = ver.id

        # Persist facts grouped by accession so each links to its filing's version.
        for accn, version_id in ver_by_accn.items():
            group = [s for s in entity_specs if s.accession == accn]
            facts_persisted += persist_facts(
                session, tenant_id, group, document_version_id=version_id
            )

    return {
        "documents": docs_created,
        "versions": versions_created,
        "facts": facts_persisted,
    }
