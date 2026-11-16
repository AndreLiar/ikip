"""FinancialFact persistence tests (Epic 8, Story 8.1, ADR 0030). DB-backed → gated on
TEST_DATABASE_URL (throwaway pg locally; ephemeral Neon branch in CI). flush+rollback."""

import os
from datetime import date
from decimal import Decimal

import pytest
from ikip_common.db.base import Base
from ikip_common.db.financial import persist_facts
from ikip_common.db.models import FinancialFact, Tenant
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _Spec:
    """DB-free fact record (duck-types the extractor's FactSpec)."""

    def __init__(self, **kw):  # noqa: ANN003
        d = {
            "entity_cik": "0000320193",
            "entity_name": "Apple Inc.",
            "taxonomy": "us-gaap",
            "concept": "Assets",
            "value": Decimal("352583000000"),
            "unit": "USD",
            "period_end": date(2023, 9, 30),
            "period_start": None,
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "form": "10-K",
            "filed_date": date(2023, 11, 3),
            "frame": None,
            "accession": "0000320193-23-000106",
            "dimensions": {},
        }
        d.update(kw)
        self.__dict__.update(d)


@pytest.fixture(scope="module")
def engine():  # noqa: ANN201
    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):  # noqa: ANN001, ANN201
    with Session(engine) as s:
        yield s
        s.rollback()


def _tenant(session: Session):  # noqa: ANN202
    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    return t.id


def test_persist_keeps_value_exact_and_period_semantics(session: Session) -> None:
    tid = _tenant(session)
    n = persist_facts(session, tid, [_Spec()])
    session.flush()
    assert n == 1
    fact = session.execute(select(FinancialFact)).scalar_one()
    # exact NUMERIC round-trip — no float drift
    assert fact.value_numeric == Decimal("352583000000")
    assert fact.period_start is None and fact.period_end == date(2023, 9, 30)  # instant
    assert fact.accession == "0000320193-23-000106"  # provenance


def test_persist_is_idempotent_on_identity(session: Session) -> None:
    tid = _tenant(session)
    specs = [_Spec(), _Spec()]  # same identity twice
    first = persist_facts(session, tid, specs)
    session.flush()
    second = persist_facts(session, tid, [_Spec()])  # re-ingest the filing
    session.flush()
    assert first == 1  # the duplicate within the batch is collapsed
    assert second == 0  # re-ingest adds nothing
    assert session.execute(select(FinancialFact)).scalars().all().__len__() == 1


def test_facts_are_tenant_scoped(session: Session) -> None:
    a, b = _tenant(session), _tenant(session)
    persist_facts(session, a, [_Spec()])
    persist_facts(session, b, [_Spec()])  # same fact, different tenant = NOT a duplicate
    session.flush()
    rows = session.execute(select(FinancialFact)).scalars().all()
    assert {r.tenant_id for r in rows} == {a, b} and len(rows) == 2
