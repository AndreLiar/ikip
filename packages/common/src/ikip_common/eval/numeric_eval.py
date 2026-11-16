"""Numeric-accuracy evaluation for financial figures (Epic 8, Story 8.3, ADR 0030).

Measures what the figure path must get right: **the exact value** and **the exact citation**
(source filing + period) for known figures, and **correct abstention** where a figure is
unavailable/ambiguous. Deterministic + free (no LLM, no cost — just `retrieve_figure` vs a gold
value), so unlike the faithfulness gate this can gate **every push** once a finance tenant exists.

A gold case carries its structured `FigureQuery` (the NL→query step is evaluated separately), the
known value + unit, and the expected citation (accession + period). The gate asserts exact-match /
citation / behaviour floors.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from ikip_common.finance import FigureQuery, retrieve_figure


@dataclass
class FigureGoldCase:
    case_key: str
    question: str
    query: FigureQuery
    expected_behavior: str  # "resolved" | "abstained"
    expected_value: Decimal | None = None
    expected_unit: str | None = None
    expected_accession: str | None = None
    expected_period_end: date | None = None


def _date(v: object) -> date | None:
    return date.fromisoformat(str(v)) if v else None


def load_figure_gold(path: str | Path) -> tuple[str, list[dict], list[FigureGoldCase]]:
    """Load a self-contained figure gold: (version, facts-to-seed, cases)."""
    doc = json.loads(Path(path).read_text())
    cases = [
        FigureGoldCase(
            case_key=c["case_key"],
            question=c["question"],
            query=FigureQuery(
                entity_cik=c["query"]["entity_cik"],
                concept=c["query"]["concept"],
                taxonomy=c["query"].get("taxonomy", "us-gaap"),
                fiscal_year=c["query"].get("fiscal_year"),
                fiscal_period=c["query"].get("fiscal_period"),
                period_end=_date(c["query"].get("period_end")),
                unit=c["query"].get("unit"),
            ),
            expected_behavior=c["expected_behavior"],
            expected_value=Decimal(c["expected_value"]) if c.get("expected_value") else None,
            expected_unit=c.get("expected_unit"),
            expected_accession=c.get("expected_accession"),
            expected_period_end=_date(c.get("expected_period_end")),
        )
        for c in doc["cases"]
    ]
    return doc.get("gold_set_version", "unknown"), doc.get("facts", []), cases


@dataclass
class NumericCaseResult:
    case_key: str
    expected_behavior: str
    actual_behavior: str
    behavior_match: bool
    value_exact_match: bool | None  # None when the case expects abstention
    citation_correct: bool | None


@dataclass
class NumericEvalReport:
    gold_set_version: str
    n_cases: int
    behavior_conformity: float
    exact_match_rate: float  # over resolved-expected cases
    citation_accuracy: float  # over resolved-expected cases
    cases: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _rate(num: int, den: int) -> float:
    return num / den if den else 1.0


def evaluate_figures(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    cases: list[FigureGoldCase],
    *,
    gold_set_version: str = "unknown",
) -> NumericEvalReport:
    """Run each gold figure query through `retrieve_figure` and score value + citation + behaviour.
    Deterministic given the fact store — no network."""
    results: list[NumericCaseResult] = []
    for c in cases:
        r = retrieve_figure(session, tenant_id, c.query)
        behavior_match = r.status == c.expected_behavior
        exact: bool | None = None
        citation: bool | None = None
        if c.expected_behavior == "resolved":
            exact = r.status == "resolved" and r.value == c.expected_value
            citation = (
                r.status == "resolved"
                and r.citation is not None
                and r.citation.accession == c.expected_accession
                and r.citation.period_end == c.expected_period_end
            )
        results.append(
            NumericCaseResult(
                case_key=c.case_key,
                expected_behavior=c.expected_behavior,
                actual_behavior=r.status,
                behavior_match=behavior_match,
                value_exact_match=exact,
                citation_correct=citation,
            )
        )

    resolved = [x for x in results if x.expected_behavior == "resolved"]
    return NumericEvalReport(
        gold_set_version=gold_set_version,
        n_cases=len(results),
        behavior_conformity=_rate(sum(x.behavior_match for x in results), len(results)),
        exact_match_rate=_rate(sum(bool(x.value_exact_match) for x in resolved), len(resolved)),
        citation_accuracy=_rate(sum(bool(x.citation_correct) for x in resolved), len(resolved)),
        cases=[asdict(x) for x in results],
    )


@dataclass(frozen=True)
class NumericBreach:
    metric: str
    value: float
    floor: float


def numeric_accuracy_gate(
    report: NumericEvalReport,
    *,
    min_exact_match: float = 1.0,
    min_citation: float = 1.0,
    min_behavior: float = 1.0,
) -> list[NumericBreach]:
    """Return floor breaches. Defaults to 1.0 — a figure store that returns a wrong value or a
    wrong citation is broken, so the bar is exactness, not a tolerance."""
    checks = [
        ("exact_match_rate", report.exact_match_rate, min_exact_match),
        ("citation_accuracy", report.citation_accuracy, min_citation),
        ("behavior_conformity", report.behavior_conformity, min_behavior),
    ]
    return [NumericBreach(m, v, f) for m, v, f in checks if v < f]
