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
from ikip_api.conversations import (
    ConversationService,
    NotFoundError,
    get_conversation_service,
)
from ikip_api.governance import GovernanceService, get_governance_service
from ikip_api.observability import (
    TraceRecorder,
    get_metrics,
    get_telemetry,
    get_trace_recorder,
)

router = APIRouter()


# --- wire schemas ----------------------------------------------------------


class CitationRegion(BaseModel):
    page: int
    bbox: tuple[float, float, float, float]


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
    regions: list[CitationRegion] = Field(default_factory=list)


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
    # Optional: append to an existing conversation; a new one is created when omitted
    # and persistence is enabled (Story 4.6).
    conversation_id: uuid.UUID | None = None


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
    # Set when the turn was persisted (Story 4.6): the conversation it belongs to and
    # the assistant message id — the web FeedbackBar uses message_id to rate/flag it.
    conversation_id: str | None = None
    message_id: str | None = None


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
        conversation_id: uuid.UUID | None = None,
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
        regions=meta.get("regions", []),
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
        regions=hit.regions,
    )


def get_retrieve_service() -> RetrieveService:
    """Default (production) retrieval service — keyword (lexical), semantic (vector) or
    hybrid (RRF), per the request `mode` (Story 4.4 AC1). Tenant-scoped, one DB session
    per request; heavy stack lazy-imported."""

    def service(  # noqa: ANN001
        *, tenant_id, query, k, mode, current_only, document_type, equipment_id, user_id
    ) -> RetrieveResponse:
        from ikip_common.cache import CachingEmbeddingClient, build_cache
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

            # Query-embedding cache (Story 3.7/5.6): a repeated query skips the Azure embed;
            # best-effort (a cache outage degrades to a direct embed). Hits feed the dashboard.
            client = CachingEmbeddingClient(
                build_embedding_client(), build_cache(), metrics=get_metrics()
            )
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


_HISTORY_MAX_TURNS = 4  # bounded thread window for contextualization (ADR 0032 layer 1)


def _load_history(session, *, tenant_id, user_id, conversation_id):  # noqa: ANN001, ANN202
    """Last ≤4 (user, assistant) turns of an **owned** conversation (NFR10: tenant+user scoped);
    [] if the conversation isn't the caller's. Feeds query contextualization only — never the
    answer (ADR 0032)."""
    from sqlalchemy import select

    from ikip_common.db.models import Conversation, ConversationMessage

    owned = session.execute(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
        )
    ).first()
    if owned is None:
        return []
    rows = session.execute(
        select(ConversationMessage.role, ConversationMessage.content)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    ).all()
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for role, content in rows:
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            pairs.append((pending_user, content))
            pending_user = None
    return pairs[-_HISTORY_MAX_TURNS:]


def _memory_filters(session, *, tenant_id, user_id):  # noqa: ANN001, ANN202
    """Long-term memory → RetrievalFilters (ADR 0032 layer 2). Preferences bias retrieval; the
    base keeps the per-user ACL filter. Returns filters only — never answer content."""
    from ikip_common.db.retrieval import RetrievalFilters
    from ikip_common.user_memory import get_memory, memory_retrieval_filters

    entries = get_memory(session, tenant_id=tenant_id, user_id=user_id)
    return memory_retrieval_filters(entries, base=RetrievalFilters(user_id=user_id))


def _context_fingerprint(history, filters):  # noqa: ANN001, ANN202
    """Stable hash of the memory/history signals that changed retrieval, or None when neither is
    active (so the cache key is byte-identical to the pre-memory key). Partitions the answer cache
    so a memory-influenced answer can't collide with another user's answer to the same question."""
    memory_active = (filters.document_type, filters.equipment_id, filters.metadata) != (
        None,
        None,
        None,
    )
    if not history and not memory_active:
        return None
    import hashlib
    import json

    payload = {
        "history": [list(t) for t in history],
        "document_type": filters.document_type,
        "equipment_id": str(filters.equipment_id) if filters.equipment_id else None,
        "metadata": filters.metadata,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_ask_service() -> AskService:
    """Default (production) grounded-answer service with caching (Stories 3.5 + 3.7) and
    memory (ADR 0032): conversational history contextualizes the retrieval query, long-term
    memory biases the retrieval filters. Memory shapes *what is retrieved*, never the answer —
    the grounding/citation guarantee is untouched (generation still answers over retrieved,
    cited evidence); and the answer cache is partitioned by a context fingerprint so a
    memory-influenced answer never collides with another user's."""

    def service(  # noqa: ANN001
        *, tenant_id, query, equipment_model, revision, user_id, conversation_id=None
    ) -> AskResponse:
        from ikip_common.cache import CachingEmbeddingClient, build_cache
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Document, DocumentVersion
        from ikip_common.llm import build_chat_client, build_embedding_client
        from ikip_common.llm.answer import make_hybrid_retrieve
        from ikip_common.llm.answer_cache import cached_grounded_answer
        from sqlalchemy import select

        from ikip_api.observability import get_metrics

        metrics = get_metrics()
        cache = build_cache()
        chat_client = build_chat_client()

        with make_session_factory()() as session:
            current_ids = [
                str(v)
                for v in session.execute(
                    select(DocumentVersion.id)
                    .join(Document, DocumentVersion.document_id == Document.id)
                    .where(Document.tenant_id == tenant_id, DocumentVersion.is_current.is_(True))
                ).scalars()
            ]
            # ADR 0032 layer 2: long-term memory → retrieval filters (user prefs bias retrieval).
            filters = _memory_filters(session, tenant_id=tenant_id, user_id=user_id)
            # ADR 0032 layer 1: conversational history → standalone-query contextualization.
            history = (
                _load_history(
                    session, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
                )
                if conversation_id is not None
                else []
            )
            retrieve = make_hybrid_retrieve(
                session,
                tenant_id,
                CachingEmbeddingClient(build_embedding_client(), cache, metrics=metrics),
                filters=filters,
                history=history or None,
                contextualize_client=chat_client if history else None,
            )
            result, hit = cached_grounded_answer(
                query,
                cache=cache,
                tenant_id=tenant_id,
                current_version_ids=current_ids,
                retrieve=retrieve,
                chat_client=chat_client,
                equipment_model=equipment_model,
                revision=revision,
                context_fingerprint=_context_fingerprint(history, filters),
            )
        # Answer-cache hit rate → dashboard (Story 5.6). An answer-cache hit also skips
        # retrieval + embedding entirely (the biggest win).
        metrics.record_cache(cache="answer", hit=hit)
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
    conversations: Annotated[ConversationService, Depends(get_conversation_service)],
    telemetry: Annotated[object, Depends(get_telemetry)],
    trace_recorder: Annotated[TraceRecorder, Depends(get_trace_recorder)],
    metrics: Annotated[object, Depends(get_metrics)],
) -> AskResponse:
    import time

    from ikip_common.eval.metrics import estimate_cost_usd
    from ikip_common.llm.prompts import active_prompt_config

    governance.authorize(principal, "assistant.ask")
    # Attribution (Story 5.5 ↔ 5.4): stamp the trace with the deployment + the ACTIVE prompt
    # config version, so a quality shift is traceable to the exact prompt/model that produced it.
    _cfg = active_prompt_config()
    model_version = f"{_cfg.model.chat_deployment}+prompt:{_cfg.version}"
    # Trace the generation end-to-end (OTel→Langfuse, Story 5.4). The span carries only
    # IDs + metadata — never the raw prompt/content (AC4).
    start = time.perf_counter()
    with telemetry.span(  # type: ignore[attr-defined]
        "assistant.ask", tenant_id=str(principal.tenant_id), operation="ask"
    ) as span:
        result = service(
            tenant_id=principal.tenant_id,
            query=req.query,
            equipment_model=req.equipment_model,
            revision=req.revision,
            user_id=principal.user_id,
            conversation_id=req.conversation_id,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        cost_usd = estimate_cost_usd(req.query, result.answer or "")
        span.set_metadata(status=result.status, cache_hit=result.cache_hit)
        span.set_cost(cost_usd=cost_usd)
        trace_id = span.trace_id

    # Operational metrics → Grafana Cloud (Story 5.6): latency histogram + request/cost
    # counters, labelled by status. No-op unless an OTLP endpoint is configured.
    metrics.record_request(operation="ask", latency_ms=latency_ms, status=result.status)  # type: ignore[attr-defined]
    metrics.record_cost(cost_usd=cost_usd)  # type: ignore[attr-defined]

    governance.record(
        principal,
        "assistant.ask",
        resource_type="query",
        metadata={"status": result.status},
    )
    # Persist the turn (Story 4.6): record the user question + the assistant answer so
    # history is reproducible and the UI can attach feedback to this message.
    _persist_turn(conversations, principal, req, result)

    # Durable, queryable trace (Story 5.4 AC1/AC3): IDs + metrics, correlatable via trace_id.
    chunk_ids = [
        c.chunk_id for claim in result.claims for c in claim.citations if c.chunk_id is not None
    ]
    trace_recorder.record(
        tenant_id=principal.tenant_id,
        operation="ask",
        query=req.query,
        status=result.status,
        actor_user_id=principal.user_id,
        conversation_id=uuid.UUID(result.conversation_id)
        if result.conversation_id and _is_uuid(result.conversation_id)
        else None,
        message_id=uuid.UUID(result.message_id)
        if result.message_id and _is_uuid(result.message_id)
        else None,
        model_version=model_version,
        retrieved_chunk_ids=chunk_ids,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        trace_id=trace_id or None,
    )
    return result


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _persist_turn(
    conversations: ConversationService,
    principal: object,  # Principal; avoid heavy import
    req: AskRequest,
    result: AskResponse,
) -> None:
    tenant_id = principal.tenant_id  # type: ignore[attr-defined]
    user_id = principal.user_id  # type: ignore[attr-defined]
    try:
        conv_id = (
            str(req.conversation_id)
            if req.conversation_id is not None
            else conversations.create(tenant_id=tenant_id, user_id=user_id, title=req.query[:80]).id
        )
        conversations.add_message(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conv_id,
            role="user",
            content=req.query,
            answer_payload={},
        )
        assistant = conversations.add_message(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conv_id,
            role="assistant",
            content=result.answer or (result.abstention_reason or ""),
            answer_payload=result.model_dump(),
        )
        result.conversation_id = conv_id
        result.message_id = assistant.id
    except NotFoundError:
        # A conversation_id that isn't the caller's — don't persist; the answer still returns.
        return
