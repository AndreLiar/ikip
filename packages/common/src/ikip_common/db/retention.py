"""Data retention, deletion & provenance (Story 6.5, FR33, NFR16).

Governance owner workflows:
- **Provenance** per source + version (`provenance`) and a **licensing gate** (`is_license_allowed`)
  enforcing the `data-sources.md` rule — provenance recorded in `document.rights`.
- **Consistent deletion** (`delete_document`) across ALL stores: the DB cascade removes
  versions → sections → chunks → embeddings, and we explicitly delete the object-storage
  artifacts (raw/curated/layout/source keys) that FKs don't cascade.
- **Per-tenant retention** (`retention_sweep`) driven by `tenant.policies["retention_days"]`.
- Every deletion/retention action is **audit-logged** (`AuditEvent`).

Tenant-scoped: a deletion only ever touches the caller's tenant (NFR10).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ikip_common.db.models import (
    AuditEvent,
    Chunk,
    Document,
    DocumentVersion,
    Section,
    Tenant,
)
from ikip_common.storage.base import ObjectStorage

# Licensing gate (data-sources.md, Story 6.5): only ingest/keep documents whose recorded
# rights are on the allowed list. Conservative: an unknown/empty license is NOT allowed.
ALLOWED_LICENSES: frozenset[str] = frozenset(
    {
        "public-domain",
        "cc0",
        "cc-by",
        "cc-by-sa",
        "mit",
        "apache-2.0",
        "manufacturer-authorized",  # explicit OEM permission recorded during onboarding
        # Licence Ouverte 2.0 (Etalab) — France's open-government license (data.gouv.fr / DILA
        # Légifrance/jurisprudence); permissive, CC-BY-4.0-compatible. FR public corpora are
        # tagged rights="licence-ouverte".
        "licence-ouverte",
    }
)


def is_license_allowed(rights: str | None) -> bool:
    """True if `document.rights` denotes a license cleared for ingestion/retention."""
    return bool(rights) and rights.strip().lower() in ALLOWED_LICENSES


def provenance(document: Document, versions: Sequence[DocumentVersion]) -> dict:
    """Licensing/provenance per source (document) AND per version (AC1)."""
    return {
        "document_id": str(document.id),
        "source": document.source,
        "license": document.rights,
        "license_allowed": is_license_allowed(document.rights),
        "content_fingerprint": document.content_fingerprint,
        "versions": [
            {
                "revision": v.revision,
                "checksum": v.checksum,
                "is_current": v.is_current,
                "source_object_key": v.source_object_key,
            }
            for v in versions
        ],
    }


@dataclass
class DeletionReport:
    document_id: str
    versions: int
    chunks: int
    embeddings: int
    object_keys_deleted: list[str] = field(default_factory=list)
    object_keys_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _version_object_keys(versions: Sequence[DocumentVersion]) -> list[str]:
    keys: list[str] = []
    for v in versions:
        keys += [k for k in (v.curated_object_key, v.layout_object_key, v.source_object_key) if k]
    return keys


def delete_document(
    session: Session,
    storage: ObjectStorage,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    reason: str = "manual",
) -> DeletionReport:
    """Delete a document consistently across raw/curated/index/embedding stores (AC3) and
    audit-log it (AC4). Tenant-scoped: a document of another tenant is not found → no-op raise.
    Caller commits."""
    document = session.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if document is None:
        raise ValueError(f"document {document_id} not found for tenant {tenant_id}")

    versions = list(
        session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        ).scalars()
    )
    version_ids = [v.id for v in versions]
    chunks = _count_chunks(session, version_ids)
    embeddings = _count_embeddings(session, version_ids)

    report = DeletionReport(
        document_id=str(document_id), versions=len(versions), chunks=chunks, embeddings=embeddings
    )
    # object storage first (FKs don't cascade to R2); best-effort per key
    for key in _version_object_keys(versions):
        try:
            storage.delete(key)
            report.object_keys_deleted.append(key)
        except Exception:  # noqa: BLE001 — collect failures, don't abort the DB deletion
            report.object_keys_failed.append(key)

    session.delete(document)  # cascade: versions → sections → chunks → embeddings
    session.flush()

    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            operation="data.delete",
            resource_type="document",
            resource_id=document_id,
            event_metadata={"reason": reason, **report.to_dict()},
        )
    )
    session.flush()
    return report


def _count_chunks(session: Session, version_ids: Sequence[uuid.UUID]) -> int:
    if not version_ids:
        return 0
    stmt = (
        select(func.count())
        .select_from(Chunk)
        .join(Section, Chunk.section_id == Section.id)
        .where(Section.document_version_id.in_(version_ids))
    )
    return int(session.execute(stmt).scalar_one())


def _count_embeddings(session: Session, version_ids: Sequence[uuid.UUID]) -> int:
    from ikip_common.db.models import Embedding

    if not version_ids:
        return 0
    stmt = (
        select(func.count())
        .select_from(Embedding)
        .join(Chunk, Embedding.chunk_id == Chunk.id)
        .join(Section, Chunk.section_id == Section.id)
        .where(Section.document_version_id.in_(version_ids))
    )
    return int(session.execute(stmt).scalar_one())


def get_retention_days(tenant: Tenant) -> int | None:
    """Per-tenant retention window from `tenant.policies['retention_days']` (None = keep)."""
    days = (tenant.policies or {}).get("retention_days")
    return int(days) if days else None


def retention_sweep(
    session: Session,
    storage: ObjectStorage,
    tenant_id: uuid.UUID,
    *,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[DeletionReport]:
    """Delete documents older than the tenant's retention window (by `document.created_at`),
    each via `delete_document` (so all stores + audit stay consistent). No policy → no-op.
    Caller commits."""
    tenant = session.get(Tenant, tenant_id)
    days = get_retention_days(tenant) if tenant else None
    if not days:
        return []
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    stale = list(
        session.execute(
            select(Document.id).where(Document.tenant_id == tenant_id, Document.created_at < cutoff)
        ).scalars()
    )
    reports = [
        delete_document(
            session, storage, tenant_id, doc_id, actor_user_id=actor_user_id, reason="retention"
        )
        for doc_id in stale
    ]
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            operation="data.retention_sweep",
            resource_type="tenant",
            resource_id=tenant_id,
            event_metadata={"retention_days": days, "documents_deleted": len(reports)},
        )
    )
    session.flush()
    return reports
