"""Conversation/message/feedback persistence + isolation (Story 4.6) — DB-gated."""

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.models import (
    AnswerFeedback,
    AppUser,
    Conversation,
    ConversationMessage,
    Tenant,
)
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():
    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def _user(session: Session, tenant: Tenant) -> AppUser:
    u = AppUser(tenant_id=tenant.id, email=f"{uuid.uuid4()}@x")
    session.add(u)
    session.flush()
    return u


def test_conversation_thread_keeps_answer_payload(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    u = _user(session, t)
    conv = Conversation(tenant_id=t.id, user_id=u.id, title="Pumps")
    session.add(conv)
    session.flush()
    session.add(
        ConversationMessage(
            tenant_id=t.id,
            conversation_id=conv.id,
            role="assistant",
            content="E42 = overheat [E1]",
            answer_payload={"status": "answered", "claims": [{"text": "E42 = overheat"}]},
        )
    )
    session.flush()
    msg = session.execute(select(ConversationMessage)).scalar_one()
    assert msg.answer_payload["status"] == "answered"
    assert msg.answer_payload["claims"][0]["text"] == "E42 = overheat"


def test_feedback_unique_per_message_user(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    u = _user(session, t)
    conv = Conversation(tenant_id=t.id, user_id=u.id)
    session.add(conv)
    session.flush()
    m = ConversationMessage(tenant_id=t.id, conversation_id=conv.id, role="assistant", content="x")
    session.add(m)
    session.flush()
    session.add(AnswerFeedback(tenant_id=t.id, message_id=m.id, user_id=u.id, rating=1))
    session.flush()
    session.add(AnswerFeedback(tenant_id=t.id, message_id=m.id, user_id=u.id, rating=-1))
    with pytest.raises(IntegrityError):
        session.flush()


def test_conversation_is_tenant_and_user_scoped(session: Session) -> None:
    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    ua, ub = _user(session, a), _user(session, b)
    session.add(Conversation(tenant_id=a.id, user_id=ua.id, title="A-conv"))
    session.flush()
    # tenant B / user B sees nothing of tenant A
    seen = (
        session.execute(
            select(Conversation).where(
                Conversation.tenant_id == b.id, Conversation.user_id == ub.id
            )
        )
        .scalars()
        .all()
    )
    assert seen == []
