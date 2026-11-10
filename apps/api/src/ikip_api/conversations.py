"""Conversation history & feedback (Epic 4, Story 4.6).

Per-user, per-tenant Q&A history and answer feedback:
  - POST /conversations                      start a conversation
  - GET  /conversations                      list my conversations
  - GET  /conversations/{id}/messages        my thread (user + assistant turns + citations)
  - POST /conversations/{id}/messages        append a turn (persists the answer payload)
  - POST /messages/{id}/feedback             rate / flag an assistant answer
  - GET  /feedback                           flagged/low-rated feedback for failure analysis

Everything is tenant-scoped AND owner-scoped: a user only sees their own conversations
(FR21/NFR10). History retention is governed by `created_at` + the tenant policy (Epic 6);
no hard delete here. Heavy deps lazy-imported; tests inject a fake service.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ikip_api.auth import CurrentPrincipal

router = APIRouter(tags=["conversations"])


# --- schemas ---------------------------------------------------------------


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str
    answer_payload: dict = Field(default_factory=dict)


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    answer_payload: dict
    created_at: datetime


class FeedbackCreate(BaseModel):
    rating: int = Field(default=0, ge=-1, le=1)
    flagged: bool = False
    reason: str | None = None


class FeedbackOut(BaseModel):
    id: str
    message_id: str
    user_id: str
    rating: int
    flagged: bool
    reason: str | None
    created_at: datetime


# --- service port (DI; overridden in tests) --------------------------------


class NotFoundError(Exception):
    """A conversation/message not owned by the caller's tenant+user."""


class ConversationService(Protocol):
    def create(self, *, tenant_id, user_id, title) -> ConversationOut: ...  # noqa: ANN001
    def list(self, *, tenant_id, user_id) -> list[ConversationOut]: ...  # noqa: ANN001
    def messages(self, *, tenant_id, user_id, conversation_id) -> list[MessageOut]: ...  # noqa: ANN001
    def add_message(
        self,
        *,
        tenant_id,
        user_id,
        conversation_id,
        role,
        content,
        answer_payload,  # noqa: ANN001
    ) -> MessageOut: ...
    def feedback(
        self,
        *,
        tenant_id,
        user_id,
        message_id,
        rating,
        flagged,
        reason,  # noqa: ANN001
    ) -> FeedbackOut: ...
    def list_feedback(self, *, tenant_id, flagged_only, limit) -> list[FeedbackOut]: ...  # noqa: ANN001


class _DbConversationService:
    def create(self, *, tenant_id, user_id, title) -> ConversationOut:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Conversation

        with make_session_factory()() as session:
            conv = Conversation(tenant_id=tenant_id, user_id=user_id, title=title)
            session.add(conv)
            session.commit()
            return ConversationOut(id=str(conv.id), title=conv.title, created_at=conv.created_at)

    def list(self, *, tenant_id, user_id) -> list[ConversationOut]:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import Conversation
        from sqlalchemy import select

        with make_session_factory()() as session:
            rows = session.execute(
                select(Conversation)
                .where(Conversation.tenant_id == tenant_id, Conversation.user_id == user_id)
                .order_by(Conversation.created_at.desc())
            ).scalars()
            return [
                ConversationOut(id=str(c.id), title=c.title, created_at=c.created_at) for c in rows
            ]

    def _owned_conversation(self, session, *, tenant_id, user_id, conversation_id):  # noqa: ANN001
        from ikip_common.db.models import Conversation
        from sqlalchemy import select

        owned = session.execute(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if owned is None:
            raise NotFoundError(str(conversation_id))

    def messages(self, *, tenant_id, user_id, conversation_id) -> list[MessageOut]:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import ConversationMessage
        from sqlalchemy import select

        with make_session_factory()() as session:
            self._owned_conversation(
                session, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
            rows = session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.created_at.asc())
            ).scalars()
            return [
                MessageOut(
                    id=str(m.id),
                    role=m.role,
                    content=m.content,
                    answer_payload=m.answer_payload,
                    created_at=m.created_at,
                )
                for m in rows
            ]

    def add_message(
        self,
        *,
        tenant_id,
        user_id,
        conversation_id,
        role,
        content,
        answer_payload,  # noqa: ANN001
    ) -> MessageOut:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import ConversationMessage

        with make_session_factory()() as session:
            self._owned_conversation(
                session, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id
            )
            msg = ConversationMessage(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                answer_payload=answer_payload or {},
            )
            session.add(msg)
            session.commit()
            return MessageOut(
                id=str(msg.id),
                role=msg.role,
                content=msg.content,
                answer_payload=msg.answer_payload,
                created_at=msg.created_at,
            )

    def feedback(
        self,
        *,
        tenant_id,
        user_id,
        message_id,
        rating,
        flagged,
        reason,  # noqa: ANN001
    ) -> FeedbackOut:
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import AnswerFeedback, ConversationMessage
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        with make_session_factory()() as session:
            owned = session.execute(
                select(ConversationMessage.id).where(
                    ConversationMessage.id == message_id,
                    ConversationMessage.tenant_id == tenant_id,
                )
            ).scalar_one_or_none()
            if owned is None:
                raise NotFoundError(str(message_id))
            # one feedback per (message, user): upsert-ish
            existing = session.execute(
                select(AnswerFeedback).where(
                    AnswerFeedback.message_id == message_id,
                    AnswerFeedback.user_id == user_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.rating = rating
                existing.flagged = flagged
                existing.reason = reason
                fb = existing
            else:
                fb = AnswerFeedback(
                    tenant_id=tenant_id,
                    message_id=message_id,
                    user_id=user_id,
                    rating=rating,
                    flagged=flagged,
                    reason=reason,
                )
                session.add(fb)
            try:
                session.commit()
            except IntegrityError as e:  # concurrent insert of the same (message,user)
                raise NotFoundError(str(message_id)) from e
            return FeedbackOut(
                id=str(fb.id),
                message_id=str(fb.message_id),
                user_id=str(fb.user_id),
                rating=fb.rating,
                flagged=fb.flagged,
                reason=fb.reason,
                created_at=fb.created_at,
            )

    def list_feedback(self, *, tenant_id, flagged_only, limit) -> list[FeedbackOut]:  # noqa: ANN001
        from ikip_common.db import make_session_factory
        from ikip_common.db.models import AnswerFeedback
        from sqlalchemy import select

        with make_session_factory()() as session:
            stmt = select(AnswerFeedback).where(AnswerFeedback.tenant_id == tenant_id)
            if flagged_only:
                stmt = stmt.where(AnswerFeedback.flagged.is_(True))
            rows = session.execute(
                stmt.order_by(AnswerFeedback.created_at.desc()).limit(limit)
            ).scalars()
            return [
                FeedbackOut(
                    id=str(f.id),
                    message_id=str(f.message_id),
                    user_id=str(f.user_id),
                    rating=f.rating,
                    flagged=f.flagged,
                    reason=f.reason,
                    created_at=f.created_at,
                )
                for f in rows
            ]


def get_conversation_service() -> ConversationService:
    return _DbConversationService()


# --- endpoints -------------------------------------------------------------


Service = Annotated[ConversationService, Depends(get_conversation_service)]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    body: ConversationCreate, principal: CurrentPrincipal, service: Service
) -> ConversationOut:
    return service.create(
        tenant_id=principal.tenant_id, user_id=principal.user_id, title=body.title
    )


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(principal: CurrentPrincipal, service: Service) -> list[ConversationOut]:
    return service.list(tenant_id=principal.tenant_id, user_id=principal.user_id)


def _handle_not_found(fn, *args, **kwargs):  # noqa: ANN001
    try:
        return fn(*args, **kwargs)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from e


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID, principal: CurrentPrincipal, service: Service
) -> list[MessageOut]:
    return _handle_not_found(
        service.messages,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        conversation_id=conversation_id,
    )


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201
)
def add_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    principal: CurrentPrincipal,
    service: Service,
) -> MessageOut:
    return _handle_not_found(
        service.add_message,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        conversation_id=conversation_id,
        role=body.role,
        content=body.content,
        answer_payload=body.answer_payload,
    )


@router.post("/messages/{message_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(
    message_id: uuid.UUID,
    body: FeedbackCreate,
    principal: CurrentPrincipal,
    service: Service,
) -> FeedbackOut:
    return _handle_not_found(
        service.feedback,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        message_id=message_id,
        rating=body.rating,
        flagged=body.flagged,
        reason=body.reason,
    )


@router.get("/feedback", response_model=list[FeedbackOut])
def list_feedback(
    principal: CurrentPrincipal,
    service: Service,
    flagged_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[FeedbackOut]:
    return service.list_feedback(
        tenant_id=principal.tenant_id, flagged_only=flagged_only, limit=limit
    )
