"""Numeric figure retrieval + comparison tests (Epic 8, Story 8.2, ADR 0030).

Comparison is pure (no DB). Retrieval is DB-backed → gated on TEST_DATABASE_URL."""

import os
from datetime import date
from decimal import Decimal

import pytest
from ikip_common.finance import (
    FigureQuery,
    FigureResult,
    compare_figures,
    retrieve_figure,
)


# --- pure: compare_figures -----------------------------------------------------
def _resolved(value: str, unit: str = "USD") -> FigureResult:
    return FigureResult(
        status="resolved",
        concept="Revenues",
        entity_cik="0000320193",
        value=Decimal(value),
        unit=unit,
        period_end=date(2023, 9, 30),
    )


def test_compare_computes_delta_and_pct_deterministically() -> None:
    c = compare_figures(_resolved("383285000000"), _resolved("394328000000"))
    assert c.status == "computed"
    assert c.delta == Decimal("-11043000000")  # exact, code-computed (not the LLM)
    assert abs(c.pct_change - Decimal("-2.8004")) < Decimal("0.001")  # ~ -2.80%


def test_compare_abstains_on_unit_mismatch() -> None:
    c = compare_figures(_resolved("100", "USD"), _resolved("5", "USD/shares"))
    assert c.status == "abstained" and "unit mismatch" in c.abstention_reason


def test_compare_abstains_if_a_figure_unresolved() -> None:
    unresolved = FigureResult(status="abstained", concept="Revenues", entity_cik="x")
    assert compare_figures(_resolved("100"), unresolved).status == "abstained"


# --- DB-backed: retrieve_figure ------------------------------------------------
_URL = os.environ.get("TEST_DATABASE_URL")
dbtest = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def engine():  # noqa: ANN201
    from ikip_common.db.base import Base
    from sqlalchemy import create_engine

    url = _URL.replace("postgresql://", "postgresql+psycopg://", 1) if _URL else _URL
    eng = create_engine(url)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def session(engine):  # noqa: ANN001, ANN201
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        yield s
        s.rollback()


def _seed(session, tenant, **kw):  # noqa: ANN001, ANN202
    from ikip_common.db.models import FinancialFact

    base = {
        "tenant_id": tenant,
        "entity_cik": "0000320193",
        "entity_name": "Apple Inc.",
        "taxonomy": "us-gaap",
        "concept": "Revenues",
        "value_numeric": Decimal("383285000000"),
        "unit": "USD",
        "period_start": date(2022, 9, 25),
        "period_end": date(2023, 9, 30),
        "dimensions": {},
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "form": "10-K",
        "filed_date": date(2023, 11, 3),
        "frame": None,
        "accession": "0000320193-23-000106",
    }
    base.update(kw)
    f = FinancialFact(**base)
    session.add(f)
    session.flush()
    return f


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    return t.id


@dbtest
def test_resolves_exact_figure_with_citation(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    _seed(session, t)
    r = retrieve_figure(
        session,
        t,
        FigureQuery(
            entity_cik="0000320193", concept="Revenues", fiscal_year=2023, fiscal_period="FY"
        ),
    )
    assert r.status == "resolved"
    assert r.value == Decimal("383285000000") and r.unit == "USD"
    assert r.citation.accession == "0000320193-23-000106"  # exact source
    assert r.citation.period_end == date(2023, 9, 30)  # + period (FR16)


@dbtest
def test_abstains_when_figure_unavailable(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    _seed(session, t)
    r = retrieve_figure(
        session, t, FigureQuery(entity_cik="0000320193", concept="Revenues", fiscal_year=2099)
    )
    assert r.status == "abstained" and "unavailable" in r.abstention_reason


@dbtest
def test_restatement_keeps_latest_filed_value(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    # original filing, then a RESTATEMENT (later filed, different value, different accession)
    _seed(
        session,
        t,
        value_numeric=Decimal("380000000000"),
        filed_date=date(2023, 11, 3),
        accession="0000320193-23-000106",
    )
    _seed(
        session,
        t,
        value_numeric=Decimal("383285000000"),
        filed_date=date(2024, 11, 1),
        accession="0000320193-24-000100",
    )
    r = retrieve_figure(
        session,
        t,
        FigureQuery(
            entity_cik="0000320193", concept="Revenues", fiscal_year=2023, fiscal_period="FY"
        ),
    )
    assert r.status == "resolved"
    assert r.value == Decimal("383285000000")  # latest-filed (restated) value
    assert r.citation.accession == "0000320193-24-000100"


@dbtest
def test_abstains_when_ambiguous_same_filing(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    # two different values, SAME filed_date, different dimensions -> ambiguous
    _seed(
        session,
        t,
        value_numeric=Decimal("200000000000"),
        dimensions={"segment": "Americas"},
        accession="A",
    )
    _seed(
        session,
        t,
        value_numeric=Decimal("100000000000"),
        dimensions={"segment": "Europe"},
        accession="B",
    )
    r = retrieve_figure(
        session,
        t,
        FigureQuery(
            entity_cik="0000320193", concept="Revenues", fiscal_year=2023, fiscal_period="FY"
        ),
    )
    assert r.status == "abstained" and "ambiguous" in r.abstention_reason


@dbtest
def test_retrieval_is_tenant_scoped(session) -> None:  # noqa: ANN001
    a, b = _tenant(session), _tenant(session)
    _seed(session, a)
    r = retrieve_figure(
        session,
        b,
        FigureQuery(
            entity_cik="0000320193", concept="Revenues", fiscal_year=2023, fiscal_period="FY"
        ),
    )
    assert r.status == "abstained"  # tenant b can't see tenant a's facts
