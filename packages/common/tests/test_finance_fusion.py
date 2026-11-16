"""Hybrid figure+narrative fusion tests (Epic 8, Story 8.2 AC1, ADR 0030).

`fuse_answer` is testable without a DB (figure built in-memory). `answer_financial_question` is
DB-backed. Scripted fake ChatClient — no network."""

import os
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest
from ikip_common.finance import FigureCitation, FigureResult
from ikip_common.finance_answer import FigureNarration, RoutedFigureQuery
from ikip_common.finance_fusion import (
    DocEvidence,
    answer_financial_question,
    documents_to_doc_evidence,
    fuse_answer,
)
from ikip_common.llm.base import ChatMessage


class _FakeDoc:
    """Duck-types a LangChain Document (page_content + metadata)."""

    def __init__(self, text: str, **meta) -> None:  # noqa: ANN003
        self.page_content = text
        self.metadata = meta


def test_documents_to_doc_evidence_maps_text_and_citation_metadata() -> None:
    docs = [
        _FakeDoc("iPhone revenue fell.", chunk_id="c1", document_id="d1", page_start=12),
        _FakeDoc("Services grew.", chunk_id="c2"),
    ]
    ev = documents_to_doc_evidence(docs)
    assert [e.marker for e in ev] == ["D1", "D2"]  # stable markers
    assert (
        ev[0].chunk_id == "c1" and ev[0].page_start == 12 and ev[0].text == "iPhone revenue fell."
    )
    assert ev[1].chunk_id == "c2"


class _FakeChat:
    def __init__(self, narration: str = "", route: RoutedFigureQuery | None = None) -> None:
        self._narration = narration
        self._route = route

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages: Sequence[ChatMessage], schema: type):  # noqa: ANN201
        if schema is RoutedFigureQuery:
            return self._route
        if schema is FigureNarration:
            return FigureNarration(answer=self._narration)
        raise AssertionError(schema)


def _figure() -> FigureResult:
    return FigureResult(
        status="resolved",
        concept="Revenues",
        entity_cik="0000320193",
        value=Decimal("383285000000"),
        unit="USD",
        period_start=date(2022, 9, 25),
        period_end=date(2023, 9, 30),
        fiscal_year=2023,
        fiscal_period="FY",
        citation=FigureCitation(
            accession="0000320193-23-000106",
            form="10-K",
            filed_date=date(2023, 11, 3),
            period_start=date(2022, 9, 25),
            period_end=date(2023, 9, 30),
            document_version_id=None,
        ),
    )


_DOCS = [
    DocEvidence(marker="D1", text="iPhone revenue declined on weaker China demand.", chunk_id="c1"),
    DocEvidence(marker="D2", text="Services reached an all-time high.", chunk_id="c2"),
]


# --- pure: fuse_answer ---------------------------------------------------------
def test_fuses_figure_with_narrative_and_both_citations() -> None:
    chat = _FakeChat(
        "Apple's FY2023 revenue was $383.3 billion; iPhone softness offset by services [D1][D2]."
    )
    out = fuse_answer("Apple FY2023 revenue and why?", _figure(), _DOCS, chat)
    assert out.status == "answered"
    assert out.figure_citation.accession == "0000320193-23-000106"  # figure cited to filing
    assert {d.chunk_id for d in out.doc_citations} == {"c1", "c2"}  # narrative cited to chunks


def test_only_referenced_doc_markers_are_cited() -> None:
    chat = _FakeChat("Revenue was $383.3 billion; services were strong [D2].")
    out = fuse_answer("...", _figure(), _DOCS, chat)
    assert [d.chunk_id for d in out.doc_citations] == ["c2"]  # D1 not referenced -> not cited


def test_guard_abstains_even_with_doc_evidence_present() -> None:
    # The figure guard holds regardless of narrative: wrong number -> abstain.
    chat = _FakeChat("Apple's revenue was about $500 billion, driven by services [D2].")
    out = fuse_answer("...", _figure(), _DOCS, chat)
    assert out.status == "abstained" and "did not match" in out.abstention_reason


def test_fuse_abstains_if_figure_unresolved() -> None:
    unresolved = FigureResult(
        status="abstained",
        concept="Revenues",
        entity_cik="x",
        abstention_reason="figure unavailable",
    )
    out = fuse_answer("...", unresolved, _DOCS, _FakeChat("whatever"))
    assert out.status == "abstained"


# --- DB-backed: answer_financial_question orchestrator -------------------------
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


@dbtest
def test_orchestrator_routes_retrieves_and_fuses(session) -> None:  # noqa: ANN001
    from ikip_common.db.models import FinancialFact, Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    session.add(
        FinancialFact(
            tenant_id=t.id,
            entity_cik="0000320193",
            entity_name="Apple Inc.",
            taxonomy="us-gaap",
            concept="Revenues",
            value_numeric=Decimal("383285000000"),
            unit="USD",
            period_start=date(2022, 9, 25),
            period_end=date(2023, 9, 30),
            dimensions={},
            fiscal_year=2023,
            fiscal_period="FY",
            form="10-K",
            filed_date=date(2023, 11, 3),
            accession="0000320193-23-000106",
        )
    )
    session.flush()
    route = RoutedFigureQuery(
        is_figure_query=True,
        entity_name="Apple Inc.",
        concept="Revenues",
        fiscal_year=2023,
        fiscal_period="FY",
    )
    chat = _FakeChat("Revenue was $383.3 billion; services grew [D1].", route=route)
    out = answer_financial_question(
        "Apple FY2023 revenue and why?",
        session,
        t.id,
        chat,
        {"Apple Inc.": "0000320193"},
        retrieve_docs=lambda _q: _DOCS,
    )
    assert out.status == "answered"
    assert out.figure.value == Decimal("383285000000")
    assert [d.chunk_id for d in out.doc_citations] == ["c1"]


@dbtest
def test_orchestrator_defers_non_figure(session) -> None:  # noqa: ANN001
    from ikip_common.db.models import Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    chat = _FakeChat(route=RoutedFigureQuery(is_figure_query=False))
    out = answer_financial_question(
        "How does Apple describe its risks?", session, t.id, chat, {}, retrieve_docs=lambda _q: []
    )
    assert out.status == "not_a_figure_query"
