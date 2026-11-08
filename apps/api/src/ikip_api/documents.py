"""Document source access (Epic 4, Story 4.5 — partial).

`GET /api/v1/documents/{version_id}/source-url` authorizes the caller's tenant for a
document version, THEN issues a short-lived R2 presigned URL to its stored artifact
(ADR 0014) — authorize-before-serve (Story 4.5 AC3, FR21/NFR10). The browser opens it
to confirm the evidence behind a citation.

Scope now: serves the artifact we store (`curated_object_key`). Opening the original
**PDF at the exact cited page + highlight** (full AC1/AC2) is deferred — it needs a PDF
corpus and the source PDF key threaded onto the version. The endpoint shape is stable;
only the key it resolves changes when that lands.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ikip_api.auth import CurrentPrincipal

router = APIRouter()

DEFAULT_EXPIRES_S = 300


class SourceUrlResponse(BaseModel):
    url: str
    expires_s: int
    content_type: str | None = None


class SourceNotFoundError(Exception):
    """The version doesn't exist for this tenant, or has no stored artifact."""


class SourceUrlService(Protocol):
    def __call__(
        self, *, tenant_id: uuid.UUID, version_id: uuid.UUID, expires_s: int
    ) -> SourceUrlResponse: ...


def get_source_url_service() -> SourceUrlService:
    """Default service: authorize version∈tenant, then presign its artifact. Heavy deps
    (DB, R2) lazy-imported so create_app() stays light in the fast CI job."""

    def service(*, tenant_id, version_id, expires_s) -> SourceUrlResponse:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from ikip_common.storage import R2ObjectStorage
        from sqlalchemy import select

        with make_session_factory()() as session:
            # Authorize-before-serve: the version must belong to the caller's tenant.
            key = session.execute(
                select(DocumentVersion.curated_object_key)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(DocumentVersion.id == version_id, Document.tenant_id == tenant_id)
            ).scalar_one_or_none()
            if not key:
                raise SourceNotFoundError(str(version_id))
            url = R2ObjectStorage().presigned_url(key, expires_s=expires_s)
        return SourceUrlResponse(url=url, expires_s=expires_s)

    return service


@router.get(
    "/documents/{version_id}/source-url",
    response_model=SourceUrlResponse,
    tags=["documents"],
)
def source_url(
    version_id: uuid.UUID,
    principal: CurrentPrincipal,
    service: Annotated[SourceUrlService, Depends(get_source_url_service)],
) -> SourceUrlResponse:
    try:
        return service(
            tenant_id=principal.tenant_id, version_id=version_id, expires_s=DEFAULT_EXPIRES_S
        )
    except SourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found") from e
