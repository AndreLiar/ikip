"""SEC filing → Document/DocumentVersion linking tests (Epic 8, Story 8.1 wiring, ADR 0030).

DB-backed → gated on TEST_DATABASE_URL."""

import os
from datetime import date
from decimal import Decimal

import pytest
from ikip_common.finance_ingest import link_and_persist_facts

_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _Spec:
    def __init__(self, **kw):  # noqa: ANN003
        d = {
            "entity_cik": "0000320193",
            "entity_name": "Apple Inc.",
            "taxonomy": "us-gaap",
            "concept": "Revenues",
            "value": Decimal("383285000000"),
            "unit": "USD",
            "period_start": date(2022, 9, 25),
            "period_end": date(2023, 9, 30),
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


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    return t.id


def test_links_facts_to_document_version_citation_chain(session) -> None:
    from ikip_common.db.models import Document, DocumentVersion, FinancialFact
    from sqlalchemy import select

    t = _tenant(session)
    specs = [
        _Spec(),  # FY2023 revenue, 10-K accession ...106
        _Spec(concept="Assets", value=Decimal("352583000000"), period_start=None),  # same filing
        _Spec(  # a DIFFERENT filing (FY2022 10-K)
            concept="Revenues",
            value=Decimal("394328000000"),
            fiscal_year=2022,
            period_start=date(2021, 9, 26),
            period_end=date(2022, 9, 24),
            filed_date=date(2022, 10, 28),
            accession="0000320193-22-000108",
        ),
    ]
    counts = link_and_persist_facts(session, t, specs)
    session.flush()
    assert counts == {"documents": 1, "versions": 2, "facts": 3}  # 1 entity, 2 filings, 3 facts

    # one Document per entity, one DocumentVersion per accession
    doc = session.execute(select(Document).where(Document.tenant_id == t)).scalar_one()
    assert doc.title == "Apple Inc. — SEC filings" and doc.rights == "public-domain"
    vers = (
        session.execute(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))
        .scalars()
        .all()
    )
    assert {v.revision for v in vers} == {"0000320193-23-000106", "0000320193-22-000108"}

    # every fact links to the version of ITS filing (the citation chain, FR16)
    facts = (
        session.execute(select(FinancialFact).where(FinancialFact.tenant_id == t)).scalars().all()
    )
    ver_by_accn = {v.revision: v.id for v in vers}
    assert all(f.document_version_id == ver_by_accn[f.accession] for f in facts)


def test_linking_is_idempotent(session) -> None:
    from ikip_common.db.models import Document, DocumentVersion, FinancialFact
    from sqlalchemy import func, select

    t = _tenant(session)
    link_and_persist_facts(session, t, [_Spec()])
    session.flush()
    second = link_and_persist_facts(session, t, [_Spec()])  # re-ingest same filing
    session.flush()
    assert second == {"documents": 0, "versions": 0, "facts": 0}  # nothing new
    assert session.execute(select(func.count()).select_from(Document)).scalar() == 1
    assert session.execute(select(func.count()).select_from(DocumentVersion)).scalar() == 1
    assert session.execute(select(func.count()).select_from(FinancialFact)).scalar() == 1
