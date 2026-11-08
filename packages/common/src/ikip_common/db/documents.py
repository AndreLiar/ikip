"""Document dedup + versioning repository (Story 2.5).

Tenant-scoped. Encapsulates the rules:
  - exact duplicate: a DocumentVersion with the same checksum already exists -> skip.
  - near duplicate: an existing Document whose content_fingerprint is within the
    SimHash Hamming threshold -> treat the incoming as a NEW VERSION of it.
  - version supersession: adding a version flips the previous current version's
    `is_current=False` but never deletes it (NFR15).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from ikip_common.db.models import Document, DocumentVersion
from ikip_common.db.repository import TenantScopedRepository
from ikip_common.db.similarity import NEAR_DUP_MAX_DISTANCE, hamming_distance


class DuplicateDocumentError(Exception):
    """Raised when the incoming content is an exact duplicate (same checksum)."""


@dataclass
class IngestOutcome:
    document: Document
    version: DocumentVersion
    created_document: bool  # True = new doc; False = new version of an existing doc


class DocumentRepository(TenantScopedRepository[Document]):
    model = Document

    # --- lookups -------------------------------------------------------

    def find_by_checksum(self, checksum: str) -> DocumentVersion | None:
        """Exact-duplicate check: any version (within tenant) with this checksum."""
        stmt = (
            select(DocumentVersion)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Document.tenant_id == self.tenant_id, DocumentVersion.checksum == checksum)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def find_near_duplicate(
        self, fingerprint: str, *, max_distance: int = NEAR_DUP_MAX_DISTANCE
    ) -> Document | None:
        """Near-duplicate check: a tenant document whose fingerprint is close."""
        for doc in self.list():
            if (
                doc.content_fingerprint
                and hamming_distance(doc.content_fingerprint, fingerprint) <= max_distance
            ):
                return doc
        return None

    def current_version(self, document_id: uuid.UUID) -> DocumentVersion | None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id, DocumentVersion.is_current.is_(True)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    # --- ingest with dedup + versioning --------------------------------

    def ingest_version(
        self,
        *,
        title: str,
        checksum: str,
        fingerprint: str,
        revision: str,
        curated_object_key: str | None = None,
        source_object_key: str | None = None,
        publication_date: date | None = None,
        effective_date: date | None = None,
        source: str | None = None,
        rights: str | None = None,
    ) -> IngestOutcome:
        """Create a document/version applying exact- and near-dup rules."""
        if self.find_by_checksum(checksum) is not None:
            raise DuplicateDocumentError(f"exact duplicate (checksum={checksum[:12]}…)")

        existing = self.find_near_duplicate(fingerprint)
        if existing is not None:
            version = self._add_version(
                existing,
                checksum,
                revision,
                curated_object_key,
                source_object_key,
                publication_date,
                effective_date,
            )
            existing.content_fingerprint = fingerprint  # track latest
            return IngestOutcome(document=existing, version=version, created_document=False)

        doc = Document(title=title, source=source, rights=rights, content_fingerprint=fingerprint)
        self.add(doc)  # stamps tenant_id
        self.session.flush()
        version = self._add_version(
            doc,
            checksum,
            revision,
            curated_object_key,
            source_object_key,
            publication_date,
            effective_date,
        )
        return IngestOutcome(document=doc, version=version, created_document=True)

    def _add_version(
        self,
        document: Document,
        checksum: str,
        revision: str,
        curated_object_key: str | None,
        source_object_key: str | None,
        publication_date: date | None,
        effective_date: date | None,
    ) -> DocumentVersion:
        # Supersede the previous current version (do not delete it — NFR15).
        prev = self.current_version(document.id)
        if prev is not None:
            prev.is_current = False
        version = DocumentVersion(
            document_id=document.id,
            revision=revision,
            checksum=checksum,
            curated_object_key=curated_object_key,
            source_object_key=source_object_key,
            publication_date=publication_date,
            effective_date=effective_date,
            is_current=True,
        )
        self.session.add(version)
        self.session.flush()
        return version
