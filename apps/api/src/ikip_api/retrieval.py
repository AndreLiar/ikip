"""Retrieval + grounded-answer endpoints (Epic 3 wiring).

Exposes the hybrid retrieval (Story 3.4) and the grounded-answer service (Story 3.5,
cached per Story 3.7) over HTTP, **tenant-scoped by the authenticated Principal**
(authorize-before-retrieve, FR21/NFR10). Citations ride in the response (FR16); an
insufficient-evidence result is surfaced as an explicit abstention, never invented.

Heavy deps (langchain/langgraph, Azure clients) are imported LAZILY inside the service
providers so `create_app()` still imports in the fast CI `validate` job (no `embeddings`
group). The providers are FastAPI dependencies, so tests override them with fakes —
no network, no DB.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ikip_api.auth import CurrentPrincipal

router = APIRouter()


# --- wire schemas ----------------------------------------------------------


class Citation(BaseModel):
    chunk_id: str | None = None
    document_id: str | None = None
    document_version_id: str | None = None
    revision: str | None = None
    is_current: bool | None = None
    section_id: str | None = None
    heading: str | None = None
    hierarchy_path: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    score: float | None = None


class RetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    current_only: bool = True
    document_type: str | None = None


class RetrievedChunk(BaseModel):
    content: str
    citation: Citation


class RetrieveResponse(BaseModel):
    abstained: bool
    results: list[RetrievedChunk]


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    equipment_model: str | None = None
    revision: str | None = None


class AnsweredClaimOut(BaseModel):
    text: str
    safety_critical: bool
    citations: list[Citation]


class AskResponse(BaseModel):
    status: str
    answer: str | None
    claims: list[AnsweredClaimOut]
    warnings: list[str]
    abstention_reason: str | None
    not_certified_notice: str
    cache_hit: bool


# --- service ports (dependency-injected; overridden in tests) --------------


class RetrieveService(Protocol):
    def __call__(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        k: int,
        current_only: bool,
        document_type: str | None,
    ) -> RetrieveResponse: ...


class AskService(Protocol):
    def __call__(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        equipment_model: str | None,
        revision: str | None,
    ) -> AskResponse: ...


def _citation_from_metadata(meta: dict, *, score: float | None = None) -> Citation:
    return Citation(
        chunk_id=meta.get("chunk_id"),
        document_id=meta.get("document_id"),
        document_version_id=meta.get("document_version_id"),
        revision=meta.get("revision"),
        is_current=meta.get("is_current"),
        section_id=meta.get("section_id"),
        heading=meta.get("heading"),
        hierarchy_path=meta.get("hierarchy_path"),
        page_start=meta.get("page_start"),
        page_end=meta.get("page_end"),
        score=score if score is not None else meta.get("rrf_score"),
    )


def get_retrieve_service() -> RetrieveService:
    """Default (production) hybrid-retrieval service. Lazy-imports the heavy stack and
    runs a tenant-scoped hybrid_retrieve per request over a fresh DB session."""

    def service(*, tenant_id, query, k, current_only, document_type) -> RetrieveResponse:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.retrieval import RetrievalFilters
        from ikip_common.llm import build_embedding_client
        from ikip_common.llm.hybrid import hybrid_retrieve

        client = build_embedding_client()
        with make_session_factory()() as session:
            outcome = hybrid_retrieve(
                session,
                tenant_id,
                query,
                client,
                filters=RetrievalFilters(current_only=current_only, document_type=document_type),
                limit=k,
            )
            results = [
                RetrievedChunk(content=d.page_content, citation=_citation_from_metadata(d.metadata))
                for d in outcome.documents
            ]
        return RetrieveResponse(abstained=outcome.abstained, results=results)

    return service


def get_ask_service() -> AskService:
    """Default (production) grounded-answer service with caching (Stories 3.5 + 3.7)."""

    def service(*, tenant_id, query, equipment_model, revision) -> AskResponse:  # noqa: ANN001
        from ikip_common.cache import build_cache
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from ikip_common.llm import build_chat_client, build_embedding_client
        from ikip_common.llm.answer import make_hybrid_retrieve
        from ikip_common.llm.answer_cache import cached_grounded_answer
        from sqlalchemy import select

        with make_session_factory()() as session:
            current_ids = [
                str(v)
                for v in session.execute(
                    select(DocumentVersion.id)
                    .join(Document, DocumentVersion.document_id == Document.id)
                    .where(Document.tenant_id == tenant_id, DocumentVersion.is_current.is_(True))
                ).scalars()
            ]
            retrieve = make_hybrid_retrieve(session, tenant_id, build_embedding_client())
            result, hit = cached_grounded_answer(
                query,
                cache=build_cache(),
                tenant_id=tenant_id,
                current_version_ids=current_ids,
                retrieve=retrieve,
                chat_client=build_chat_client(),
                equipment_model=equipment_model,
                revision=revision,
            )
        return _ask_response(result, hit)

    return service


def _ask_response(result, hit: bool) -> AskResponse:  # noqa: ANN001  (AnswerResult, avoid heavy import)
    return AskResponse(
        status=result.status,
        answer=result.answer,
        claims=[
            AnsweredClaimOut(
                text=c.text,
                safety_critical=c.safety_critical,
                citations=[_citation_from_metadata(vars(cit)) for cit in c.citations],
            )
            for c in result.claims
        ],
        warnings=result.warnings,
        abstention_reason=result.abstention_reason,
        not_certified_notice=result.not_certified_notice,
        cache_hit=hit,
    )


@router.post("/retrieve", response_model=RetrieveResponse, tags=["retrieval"])
def retrieve(
    req: RetrieveRequest,
    principal: CurrentPrincipal,
    service: Annotated[RetrieveService, Depends(get_retrieve_service)],
) -> RetrieveResponse:
    return service(
        tenant_id=principal.tenant_id,
        query=req.query,
        k=req.k,
        current_only=req.current_only,
        document_type=req.document_type,
    )


@router.post("/ask", response_model=AskResponse, tags=["retrieval"])
def ask(
    req: AskRequest,
    principal: CurrentPrincipal,
    service: Annotated[AskService, Depends(get_ask_service)],
) -> AskResponse:
    return service(
        tenant_id=principal.tenant_id,
        query=req.query,
        equipment_model=req.equipment_model,
        revision=req.revision,
    )
