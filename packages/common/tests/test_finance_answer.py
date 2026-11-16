"""Figure-answer tests (Epic 8, Story 8.2, ADR 0030).

Pure: amount parsing + the numeric guard (the safety crux). DB-backed: the full
route→retrieve→narrate→guard path with a scripted fake ChatClient (no network)."""

import os
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest
from ikip_common.finance_answer import (
    FigureNarration,
    RoutedFigureQuery,
    answer_figure_question,
    answer_states_value,
    parse_amounts,
    resolve_entity,
)
from ikip_common.llm.base import ChatMessage


# --- pure ---------------------------------------------------------------------
def test_parse_amounts_handles_scale_and_symbols() -> None:
    amts = parse_amounts("Revenue was $383.3 billion, up from 394,328,000,000.")
    assert Decimal("383300000000") in amts
    assert Decimal("394328000000") in amts


def test_guard_accepts_rounded_and_rejects_wrong_figure() -> None:
    v = Decimal("383285000000")
    assert answer_states_value("Apple's revenue was $383.3 billion.", v)  # rounded → ok
    assert answer_states_value("Revenue was 383,285,000,000 USD.", v)  # exact → ok
    assert not answer_states_value("Revenue was about $390 billion.", v)  # wrong → rejected
    assert not answer_states_value("Revenue grew during the year.", v)  # no number → rejected


def test_resolve_entity_is_case_insensitive() -> None:
    entities = {"Apple Inc.": "0000320193"}
    assert resolve_entity("apple inc.", entities) == "0000320193"
    assert resolve_entity("Unknown Co", entities) is None


# --- DB-backed: full answer path ----------------------------------------------
_URL = os.environ.get("TEST_DATABASE_URL")
dbtest = pytest.mark.skipif(not _URL, reason="TEST_DATABASE_URL not set")


class _FakeChat:
    """Returns a scripted route + narration by schema type (no network)."""

    def __init__(self, route: RoutedFigureQuery, narration: str = "") -> None:
        self._route = route
        self._narration = narration

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages: Sequence[ChatMessage], schema: type):  # noqa: ANN201
        if schema is RoutedFigureQuery:
            return self._route
        if schema is FigureNarration:
            return FigureNarration(answer=self._narration)
        raise AssertionError(schema)


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


def _seed_apple_revenue(session, tenant):  # noqa: ANN001, ANN202
    from ikip_common.db.models import FinancialFact

    session.add(
        FinancialFact(
            tenant_id=tenant,
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


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    return t.id


_ENTITIES = {"Apple Inc.": "0000320193"}
_ROUTE = RoutedFigureQuery(
    is_figure_query=True,
    entity_name="Apple Inc.",
    concept="Revenues",
    fiscal_year=2023,
    fiscal_period="FY",
)


@dbtest
def test_answers_when_narration_matches_fact(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    _seed_apple_revenue(session, t)
    chat = _FakeChat(_ROUTE, narration="Apple's FY2023 revenue was $383.3 billion.")
    ans = answer_figure_question("What was Apple revenue in FY2023?", session, t, chat, _ENTITIES)
    assert ans.status == "answered"
    assert ans.figure.value == Decimal("383285000000")
    assert ans.figure.citation.accession == "0000320193-23-000106"


@dbtest
def test_abstains_when_llm_invents_a_wrong_number(session) -> None:  # noqa: ANN001
    # The safety crux: the fact is 383.285B but the LLM says 500B -> guard fails -> abstain.
    t = _tenant(session)
    _seed_apple_revenue(session, t)
    chat = _FakeChat(_ROUTE, narration="Apple's FY2023 revenue was about $500 billion.")
    ans = answer_figure_question("What was Apple revenue in FY2023?", session, t, chat, _ENTITIES)
    assert ans.status == "abstained"
    assert "did not match" in ans.abstention_reason


@dbtest
def test_abstains_when_figure_unavailable(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    _seed_apple_revenue(session, t)
    route = RoutedFigureQuery(
        is_figure_query=True, entity_name="Apple Inc.", concept="Revenues", fiscal_year=2099
    )
    chat = _FakeChat(route, narration="(should not be used)")
    ans = answer_figure_question("Apple revenue in 2099?", session, t, chat, _ENTITIES)
    assert ans.status == "abstained" and "unavailable" in ans.abstention_reason


@dbtest
def test_not_a_figure_query_defers(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    chat = _FakeChat(RoutedFigureQuery(is_figure_query=False))
    ans = answer_figure_question("How does Apple describe its risks?", session, t, chat, _ENTITIES)
    assert ans.status == "not_a_figure_query"


@dbtest
def test_abstains_on_unknown_entity(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    route = RoutedFigureQuery(
        is_figure_query=True, entity_name="Nonexistent Co", concept="Revenues", fiscal_year=2023
    )
    ans = answer_figure_question(
        "Revenue of Nonexistent Co?", session, t, _FakeChat(route), _ENTITIES
    )
    assert ans.status == "abstained" and "unknown entity" in ans.abstention_reason
