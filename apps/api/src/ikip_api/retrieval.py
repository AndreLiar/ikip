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
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ikip_api.auth import CurrentPrincipal
from ikip_api.governance import GovernanceService, get_governance_service

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
    # keyword (lexical tsvector) | semantic (vector) | hybrid (RRF fusion) — Story 4.4 AC1.
    mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    current_only: bool = True
    document_type: str | None = None
    equipment_id: uuid.UUID | None = None


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
        mode: str,
        current_only: bool,
        document_type: str | None,
        equipment_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> RetrieveResponse: ...


class AskService(Protocol):
    def __call__(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        equipment_model: str | None,
        revision: str | None,
        user_id: uuid.UUID,
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


def _citation_from_hit(hit) -> Citation:  # noqa: ANN001  (SearchHit; avoid heavy import)
    return Citation(
        chunk_id=str(hit.chunk_id),
        document_id=str(hit.document_id),
        document_version_id=str(hit.document_version_id),
        revision=hit.revision,
        is_current=hit.is_current,
        section_id=str(hit.section_id),
        heading=hit.heading,
        hierarchy_path=hit.hierarchy_path,
        page_start=hit.page_start,
        page_end=hit.page_end,
        score=hit.score,
    )


def get_retrieve_service() -> RetrieveService:
    """Default (production) retrieval service — keyword (lexical), semantic (vector) or
    hybrid (RRF), per the request `mode` (Story 4.4 AC1). Tenant-scoped, one DB session
    per request; heavy stack lazy-imported."""

    def service(  # noqa: ANN001
        *, tenant_id, query, k, mode, current_only, document_type, equipment_id, user_id
    ) -> RetrieveResponse:
        from ikip_common.db import make_session_factory
        from ikip_common.db.retrieval import (
            RetrievalFilters,
            lexical_search,
            vector_search,
        )
        from ikip_common.llm import build_embedding_client
        from ikip_common.llm.hybrid import hybrid_retrieve

        filters = RetrievalFilters(
            current_only=current_only,
            document_type=document_type,
            equipment_id=equipment_id,
            user_id=user_id,
        )
        with make_session_factory()() as session:
            if mode == "lexical":
                hits = lexical_search(session, tenant_id, query, limit=k, filters=filters)
                results = [
                    RetrievedChunk(content=h.content, citation=_citation_from_hit(h)) for h in hits
                ]
                return RetrieveResponse(abstained=not results, results=results)

            client = build_embedding_client()
            if mode == "vector":
                [qvec] = client.embed([query])
                hits = vector_search(
                    session,
                    tenant_id,
                    qvec,
                    model_version=client.model_version,
                    limit=k,
                    filters=filters,
                )
                results = [
                    RetrievedChunk(content=h.content, citation=_citation_from_hit(h)) for h in hits
                ]
                return RetrieveResponse(abstained=not results, results=results)

            outcome = hybrid_retrieve(session, tenant_id, query, client, filters=filters, limit=k)
            results = [
                RetrievedChunk(content=d.page_content, citation=_citation_from_metadata(d.metadata))
                for d in outcome.documents
            ]
            return RetrieveResponse(abstained=outcome.abstained, results=results)

    return service


def get_ask_service() -> AskService:
    """Default (production) grounded-answer service with caching (Stories 3.5 + 3.7)."""

    def service(  # noqa: ANN001
        *, tenant_id, query, equipment_model, revision, user_id
    ) -> AskResponse:
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
            from ikip_common.db.retrieval import RetrievalFilters

            retrieve = make_hybrid_retrieve(
                session,
                tenant_id,
                build_embedding_client(),
                filters=RetrievalFilters(user_id=user_id),
            )
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
    governance: Annotated[GovernanceService, Depends(get_governance_service)],
) -> RetrieveResponse:
    governance.authorize(principal, "retrieval.search")
    result = service(
        tenant_id=principal.tenant_id,
        query=req.query,
        k=req.k,
        mode=req.mode,
        current_only=req.current_only,
        document_type=req.document_type,
        equipment_id=req.equipment_id,
        user_id=principal.user_id,
    )
    governance.record(
        principal,
        "retrieval.search",
        resource_type="query",
        metadata={"mode": req.mode, "results": len(result.results)},
    )
    return result


@router.post("/ask", response_model=AskResponse, tags=["retrieval"])
def ask(
    req: AskRequest,
    principal: CurrentPrincipal,
    service: Annotated[AskService, Depends(get_ask_service)],
    governance: Annotated[GovernanceService, Depends(get_governance_service)],
) -> AskResponse:
    governance.authorize(principal, "assistant.ask")
    result = service(
        tenant_id=principal.tenant_id,
        query=req.query,
        equipment_model=req.equipment_model,
        revision=req.revision,
        user_id=principal.user_id,
    )
    governance.record(
        principal,
        "assistant.ask",
        resource_type="query",
        metadata={"status": result.status},
    )
    return result
