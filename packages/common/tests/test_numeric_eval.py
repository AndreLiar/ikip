"""Numeric-accuracy eval + gate tests (Epic 8, Story 8.3, ADR 0030).

Gate is pure. The eval is DB-backed (seed the gold's facts → evaluate) → gated on TEST_DATABASE_URL.
Deterministic + free (no LLM)."""

import os
from decimal import Decimal

import pytest
from ikip_common.eval.numeric_eval import (
    NumericEvalReport,
    evaluate_figures,
    load_figure_gold,
    numeric_accuracy_gate,
)

_GOLD = "packages/common/tests/fixtures/eval/figure_gold_mini.json"


# --- pure: gate ---------------------------------------------------------------
def test_gate_passes_at_floor_and_fails_below() -> None:
    perfect = NumericEvalReport("v1", 4, 1.0, 1.0, 1.0)
    assert numeric_accuracy_gate(perfect) == []
    wrong_value = NumericEvalReport("v1", 4, 1.0, 0.75, 1.0)  # a value regressed
    breaches = numeric_accuracy_gate(wrong_value)
    assert [b.metric for b in breaches] == ["exact_match_rate"]


def test_gold_loads_facts_and_cases() -> None:
    version, facts, cases = load_figure_gold(_GOLD)
    assert version == "finance-sec-numeric-v1"
    assert len(facts) == 4 and len(cases) == 4
    assert any(c.expected_behavior == "abstained" for c in cases)  # negative case present


# --- DB-backed: evaluate against the seeded fact store ------------------------
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


def _seed(session, tenant, facts):  # noqa: ANN001, ANN202
    from datetime import date

    from ikip_common.db.models import FinancialFact

    for f in facts:
        session.add(
            FinancialFact(
                tenant_id=tenant,
                entity_cik=f["entity_cik"],
                entity_name=f["entity_name"],
                taxonomy=f["taxonomy"],
                concept=f["concept"],
                value_numeric=Decimal(f["value"]),
                unit=f["unit"],
                period_start=date.fromisoformat(f["period_start"]) if f["period_start"] else None,
                period_end=date.fromisoformat(f["period_end"]),
                dimensions=f["dimensions"],
                fiscal_year=f["fiscal_year"],
                fiscal_period=f["fiscal_period"],
                form=f["form"],
                filed_date=date.fromisoformat(f["filed_date"]),
                accession=f["accession"],
            )
        )
    session.flush()


def _tenant(session):  # noqa: ANN001, ANN202
    from ikip_common.db.models import Tenant

    t = Tenant(name="Finance")
    session.add(t)
    session.flush()
    return t.id


@dbtest
def test_eval_scores_perfect_on_correct_store_and_gate_passes(session) -> None:  # noqa: ANN001
    t = _tenant(session)
    version, facts, cases = load_figure_gold(_GOLD)
    _seed(session, t, facts)
    report = evaluate_figures(session, t, cases, gold_set_version=version)
    assert report.exact_match_rate == 1.0  # every known figure returned exactly
    assert report.citation_accuracy == 1.0  # every citation (accession + period) correct
    assert report.behavior_conformity == 1.0  # incl. correct abstention on the 2099 case
    assert numeric_accuracy_gate(report) == []  # gate passes


@dbtest
def test_gate_catches_a_wrong_value_in_the_store(session) -> None:  # noqa: ANN001
    # Corrupt one seeded value -> exact_match_rate drops -> the gate FAILS (the whole point).
    t = _tenant(session)
    version, facts, cases = load_figure_gold(_GOLD)
    facts[0]["value"] = "999999999999"  # tamper with Apple FY2023 revenue
    _seed(session, t, facts)
    report = evaluate_figures(session, t, cases, gold_set_version=version)
    assert report.exact_match_rate < 1.0
    breaches = numeric_accuracy_gate(report)
    assert any(b.metric == "exact_match_rate" for b in breaches)
