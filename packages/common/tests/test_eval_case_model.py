"""EvaluationCase persistence + tenant isolation (Story 3.6 AC1) — DB-gated."""

import os

import pytest
from ikip_common.db.base import Base
from ikip_common.db.models import EvaluationCase, ExpectedBehavior, Tenant
from ikip_common.db.repository import TenantScopedRepository
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _CaseRepo(TenantScopedRepository[EvaluationCase]):
    model = EvaluationCase


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


def _case(tenant: Tenant, key: str = "k1") -> EvaluationCase:
    return EvaluationCase(
        tenant_id=tenant.id,
        case_key=key,
        gold_set_version="v1",
        question="What is E42?",
        expected_behavior=ExpectedBehavior.answered.value,
        relevant_chunk_ids=["c1", "c2"],
    )


def test_persist_and_read_back(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    session.add(_case(t))
    session.flush()
    row = _CaseRepo(session, t.id).list()[0]
    assert row.gold_set_version == "v1"
    assert row.expected_behavior == "answered"
    assert row.relevant_chunk_ids == ["c1", "c2"]


def test_case_key_unique_per_goldset_tenant(session: Session) -> None:
    t = Tenant(name="A")
    session.add(t)
    session.flush()
    session.add(_case(t, "dup"))
    session.flush()
    session.add(_case(t, "dup"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_tenant_isolation(session: Session) -> None:
    a, b = Tenant(name="A"), Tenant(name="B")
    session.add_all([a, b])
    session.flush()
    session.add(_case(a))
    session.flush()
    assert len(_CaseRepo(session, a.id).list()) == 1
    assert _CaseRepo(session, b.id).list() == []  # NFR10
