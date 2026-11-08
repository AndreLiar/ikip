"""Document management (Epic 4, Story 4.2).

Tenant-scoped library surface for the knowledge manager:
  - GET  /documents                      list documents (title/type/current revision)
  - GET  /documents/{id}/versions        version history (supersession preserved, NFR15)
  - POST /documents/upload               upload a file → raw storage + a PENDING ingestion
                                         job (async ingestion, Epic 2); status is visible
  - GET  /ingestion-jobs                 recent jobs + state (upload status)

Reads require an authenticated principal (any role); upload requires manager+ (write).
All access is tenant-scoped (FR21/NFR10). Heavy deps (DB, R2) are lazy-imported inside
the DI service providers, so create_app() stays light and tests inject fakes.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from ikip_common.auth import Principal
from ikip_common.db.models import UserRole
from pydantic import BaseModel

from ikip_api.auth import CurrentPrincipal, require_role

router = APIRouter()


# --- schemas ---------------------------------------------------------------


class DocumentSummary(BaseModel):
    id: str
    title: str
    type: str | None
    current_revision: str | None
    version_count: int
    created_at: datetime


class VersionInfo(BaseModel):
    id: str
    revision: str
    is_current: bool
    checksum: str
    publication_date: date | None
    effective_date: date | None
    created_at: datetime


class UploadResponse(BaseModel):
    job_id: str
    state: str
    source: str


class DocumentUpdate(BaseModel):
    type: str | None


class JobInfo(BaseModel):
    id: str
    source: str
    state: str
    attempts: int
    created_at: datetime


# --- service ports (DI; overridden in tests) -------------------------------


class DocumentNotFoundError(Exception):
    """Document doesn't exist for this tenant."""


class LibraryService(Protocol):
    def list_documents(
        self, *, tenant_id: uuid.UUID, query: str | None, document_type: str | None
    ) -> list[DocumentSummary]: ...
    def list_versions(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[VersionInfo]: ...
    def update_document_type(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, document_type: str | None
    ) -> DocumentSummary: ...
    def upload(
        self,
        *,
        tenant_id: uuid.UUID,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> UploadResponse: ...
    def list_jobs(self, *, tenant_id: uuid.UUID, limit: int) -> list[JobInfo]: ...


def _raw_key(tenant_id: uuid.UUID, filename: str, checksum: str) -> str:
    from ikip_common.storage import ArtifactTier, tier_key

    safe = hashlib.sha256(filename.encode()).hexdigest()[:16]
    return tier_key(ArtifactTier.raw, str(tenant_id), safe, f"{checksum}.bin")


class _DbLibraryService:
    """Default service backed by the DB + R2 (lazy-imported)."""

    def list_documents(
        self, *, tenant_id: uuid.UUID, query: str | None, document_type: str | None
    ) -> list[DocumentSummary]:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from sqlalchemy import func, select

        with make_session_factory()() as session:
            vc = (
                select(
                    DocumentVersion.document_id.label("did"),
                    func.count().label("n"),
                )
                .group_by(DocumentVersion.document_id)
                .subquery()
            )
            cur = (
                select(DocumentVersion.document_id.label("did"), DocumentVersion.revision)
                .where(DocumentVersion.is_current.is_(True))
                .subquery()
            )
            statement = (
                select(Document, func.coalesce(vc.c.n, 0), cur.c.revision)
                .outerjoin(vc, vc.c.did == Document.id)
                .outerjoin(cur, cur.c.did == Document.id)
                .where(Document.tenant_id == tenant_id)
                .order_by(Document.created_at.desc())
            )
            if query:
                statement = statement.where(Document.title.ilike(f"%{query}%"))
            if document_type:
                statement = statement.where(Document.type == document_type)
            rows = session.execute(statement).all()
            return [
                DocumentSummary(
                    id=str(doc.id),
                    title=doc.title,
                    type=doc.type,
                    current_revision=rev,
                    version_count=int(n),
                    created_at=doc.created_at,
                )
                for doc, n, rev in rows
            ]

    def list_versions(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> list[VersionInfo]:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from sqlalchemy import select

        with make_session_factory()() as session:
            owned = session.execute(
                select(Document.id).where(
                    Document.id == document_id, Document.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            if owned is None:
                raise DocumentNotFoundError(str(document_id))
            versions = session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.created_at.desc())
            ).scalars()
            return [
                VersionInfo(
                    id=str(v.id),
                    revision=v.revision,
                    is_current=v.is_current,
                    checksum=v.checksum,
                    publication_date=v.publication_date,
                    effective_date=v.effective_date,
                    created_at=v.created_at,
                )
                for v in versions
            ]

    def update_document_type(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, document_type: str | None
    ) -> DocumentSummary:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from sqlalchemy import func, select

        with make_session_factory()() as session:
            document = session.execute(
                select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
            ).scalar_one_or_none()
            if document is None:
                raise DocumentNotFoundError(str(document_id))
            document.type = document_type
            version_count = session.execute(
                select(func.count(DocumentVersion.id)).where(
                    DocumentVersion.document_id == document_id
                )
            ).scalar_one()
            current_revision = session.execute(
                select(DocumentVersion.revision).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.is_current.is_(True),
                )
            ).scalar_one_or_none()
            session.commit()
            return DocumentSummary(
                id=str(document.id),
                title=document.title,
                type=document.type,
                current_revision=current_revision,
                version_count=version_count,
                created_at=document.created_at,
            )

    def upload(
        self,
        *,
        tenant_id: uuid.UUID,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> UploadResponse:
        from ikip_common.db import make_session_factory
        from ikip_common.db.ingestion import IngestionJobRepository
        from ikip_common.storage import R2ObjectStorage

        checksum = hashlib.sha256(content).hexdigest()
        key = _raw_key(tenant_id, filename, checksum)
        R2ObjectStorage().put(key, content, content_type=content_type)
        with make_session_factory()() as session:
            job = IngestionJobRepository(session, tenant_id).create(
                source=f"upload://{filename}", raw_object_key=key, content_type=content_type
            )
            session.commit()
            return UploadResponse(job_id=str(job.id), state=job.state.value, source=job.source)

    def list_jobs(self, *, tenant_id: uuid.UUID, limit: int) -> list[JobInfo]:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import IngestionJob
        from sqlalchemy import select

        with make_session_factory()() as session:
            jobs = session.execute(
                select(IngestionJob)
                .where(IngestionJob.tenant_id == tenant_id)
                .order_by(IngestionJob.created_at.desc())
                .limit(limit)
            ).scalars()
            return [
                JobInfo(
                    id=str(j.id),
                    source=j.source,
                    state=j.state.value,
                    attempts=j.attempts,
                    created_at=j.created_at,
                )
                for j in jobs
            ]


def get_library_service() -> LibraryService:
    return _DbLibraryService()


# --- endpoints -------------------------------------------------------------


@router.get("/documents", response_model=list[DocumentSummary], tags=["library"])
def list_documents(
    principal: CurrentPrincipal,
    service: Annotated[LibraryService, Depends(get_library_service)],
    query: Annotated[str | None, Query(max_length=200)] = None,
    document_type: Annotated[str | None, Query(alias="type", max_length=64)] = None,
) -> list[DocumentSummary]:
    return service.list_documents(
        tenant_id=principal.tenant_id,
        query=query.strip() if query else None,
        document_type=document_type,
    )


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[VersionInfo],
    tags=["library"],
)
def list_versions(
    document_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[LibraryService, Depends(get_library_service)],
) -> list[VersionInfo]:
    try:
        return service.list_versions(tenant_id=principal.tenant_id, document_id=document_id)
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
        ) from e


@router.patch("/documents/{document_id}", response_model=DocumentSummary, tags=["library"])
def update_document(
    document_id: uuid.UUID,
    update: DocumentUpdate,
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[LibraryService, Depends(get_library_service)],
) -> DocumentSummary:
    document_type = update.type.strip() if update.type else None
    if document_type is not None and len(document_type) > 64:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="type too long"
        )
    try:
        return service.update_document_type(
            tenant_id=principal.tenant_id,
            document_id=document_id,
            document_type=document_type,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="document not found"
        ) from e


@router.post(
    "/documents/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["library"],
)
async def upload_document(
    # Upload is a write — knowledge manager+ (RBAC, Story 1.6); reads need any role.
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[LibraryService, Depends(get_library_service)],
    file: UploadFile,
) -> UploadResponse:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file is empty")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="file exceeds the 25 MiB upload limit",
        )
    return service.upload(
        tenant_id=principal.tenant_id,
        filename=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type,
    )


@router.get("/ingestion-jobs", response_model=list[JobInfo], tags=["library"])
def list_jobs(
    principal: Annotated[Principal, Depends(require_role(UserRole.manager))],
    service: Annotated[LibraryService, Depends(get_library_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[JobInfo]:
    return service.list_jobs(tenant_id=principal.tenant_id, limit=limit)
