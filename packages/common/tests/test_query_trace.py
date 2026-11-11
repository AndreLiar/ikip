"""query_trace persistence, isolation and queryability (Story 5.4) — DB-gated."""

from __future__ import annotations

import os
import uuid

import pytest
from ikip_common.db.base import Base
from ikip_common.db.models import Tenant
from ikip_common.db.traces import QueryTraceRepository, hash_query
from sqlalchemy import create_engine
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


def _tenant(session: Session, name: str = "A") -> Tenant:
    t = Tenant(name=name)
    session.add(t)
    session.flush()
    return t


def test_record_stores_hash_not_raw_query(session: Session) -> None:
    t = _tenant(session)
    repo = QueryTraceRepository(session, t.id)
    row = repo.record(
        operation="ask",
        query="What is fault E42?",
        status="answered",
        retrieved_chunk_ids=["c1", "c2"],
        latency_ms=12.5,
        cost_usd=0.0009,
        trace_id="lf-trace-1",
    )
    session.flush()
    # AC4: the raw query is never persisted — only its sha256 hash.
    assert row.query_hash == hash_query("What is fault E42?")
    assert "E42" not in row.query_hash
    assert row.retrieved_chunk_ids == ["c1", "c2"]
    assert row.trace_id == "lf-trace-1"
    assert row.status == "answered"


def test_for_query_correlates_by_hash(session: Session) -> None:
    t = _tenant(session)
    repo = QueryTraceRepository(session, t.id)
    repo.record(operation="ask", query="Reset pump?", status="answered")
    repo.record(operation="ask", query="  reset PUMP?  ", status="answered")  # normalized-equal
    repo.record(operation="ask", query="unrelated", status="abstained")
    session.flush()
    # AC3: the same question (normalized) is queryable across traces by hash.
    hits = repo.for_query("Reset pump?")
    assert len(hits) == 2
    assert {h.status for h in hits} == {"answered"}


def test_tenant_isolation(session: Session) -> None:
    a, b = _tenant(session, "A"), _tenant(session, "B")
    QueryTraceRepository(session, a.id).record(operation="ask", query="a-q", status="answered")
    session.flush()
    # a repo bound to tenant B must not see tenant A's traces (NFR10).
    assert QueryTraceRepository(session, b.id).recent() == []
    assert len(QueryTraceRepository(session, a.id).recent()) == 1


def test_for_conversation_is_ordered_and_scoped(session: Session) -> None:
    t = _tenant(session)
    conv = uuid.uuid4()
    repo = QueryTraceRepository(session, t.id)
    repo.record(operation="ask", query="q1", status="answered", conversation_id=conv)
    repo.record(operation="ask", query="q2", status="answered", conversation_id=conv)
    repo.record(operation="ask", query="other", status="answered")  # no conversation
    session.flush()
    rows = repo.for_conversation(conv)
    assert [r.query_hash for r in rows] == [hash_query("q1"), hash_query("q2")]
