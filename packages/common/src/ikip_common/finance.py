"""Numeric figure retrieval + comparison over the fact store (Epic 8, Story 8.2, ADR 0030).

The core of financial RAG: a figure is **retrieved, not generated**. A `FigureQuery` (resolved
upstream from the user's question) becomes an **exact SQL lookup** on `financial_fact` — never an
embedding/ranking of a number. The result carries the precise value + period + provenance
(citation, FR16), or **abstains** when the figure is unavailable or ambiguous. Comparisons
(period-over-period, entity-vs-entity) are computed **deterministically here**, never by the LLM.

Pure domain logic over the model; tenant-scoped. DB-backed tests exercise the SQL.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from ikip_common.db.models import FinancialFact


@dataclass(frozen=True)
class FigureQuery:
    """A resolved figure request (the NL→query step is upstream, e.g. an LLM router)."""

    entity_cik: str
    concept: str  # XBRL tag, e.g. "Assets"
    taxonomy: str = "us-gaap"
    fiscal_year: int | None = None
    fiscal_period: str | None = None  # FY | Q1..Q4
    period_end: date | None = None  # alternative to fiscal_year/period
    unit: str | None = None  # disambiguator (USD vs shares)


@dataclass(frozen=True)
class FigureCitation:
    """Provenance for a retrieved figure (FR16): the exact filing + period."""

    accession: str
    form: str | None
    filed_date: date | None
    period_start: date | None
    period_end: date
    document_version_id: str | None


@dataclass(frozen=True)
class FigureResult:
    status: str  # "resolved" | "abstained"
    concept: str
    entity_cik: str
    value: Decimal | None = None
    unit: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    citation: FigureCitation | None = None
    abstention_reason: str | None = None


def _abstain(q: FigureQuery, reason: str) -> FigureResult:
    return FigureResult(
        status="abstained", concept=q.concept, entity_cik=q.entity_cik, abstention_reason=reason
    )


def retrieve_figure(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    query: FigureQuery,
) -> FigureResult:
    """Resolve a single figure by exact match, or abstain. Restatement handling: when a
    (entity, concept, period, unit) is reported by several filings, keep the **latest-filed**
    value (the current figure); if that still leaves >1 distinct value, **abstain** (ambiguous —
    likely needs a dimension). Never guesses, never averages."""
    stmt = select(FinancialFact).where(
        FinancialFact.tenant_id == tenant_id,
        FinancialFact.entity_cik == query.entity_cik,
        FinancialFact.taxonomy == query.taxonomy,
        FinancialFact.concept == query.concept,
    )
    if query.fiscal_year is not None:
        stmt = stmt.where(FinancialFact.fiscal_year == query.fiscal_year)
    if query.fiscal_period is not None:
        stmt = stmt.where(FinancialFact.fiscal_period == query.fiscal_period)
    if query.period_end is not None:
        stmt = stmt.where(FinancialFact.period_end == query.period_end)
    if query.unit is not None:
        stmt = stmt.where(FinancialFact.unit == query.unit)

    rows = list(session.execute(stmt).scalars())
    if not rows:
        return _abstain(query, "figure unavailable for the requested entity/concept/period")

    # If no unit filter and multiple units are present (e.g. a value in USD and a per-share
    # figure), that's ambiguous — the caller must disambiguate.
    units = {r.unit for r in rows}
    if query.unit is None and len(units) > 1:
        return _abstain(query, f"ambiguous unit; specify one of {sorted(units)}")

    # Restatement: keep the latest-filed rows, then check they agree on a single value.
    latest = max((r.filed_date or date.min) for r in rows)
    current = [r for r in rows if (r.filed_date or date.min) == latest]
    distinct_values = {r.value_numeric for r in current}
    if len(distinct_values) > 1:
        return _abstain(query, "ambiguous: multiple distinct values match (dimension needed)")

    f = current[0]
    return FigureResult(
        status="resolved",
        concept=f.concept,
        entity_cik=f.entity_cik,
        value=f.value_numeric,
        unit=f.unit,
        period_start=f.period_start,
        period_end=f.period_end,
        fiscal_year=f.fiscal_year,
        fiscal_period=f.fiscal_period,
        citation=FigureCitation(
            accession=f.accession,
            form=f.form,
            filed_date=f.filed_date,
            period_start=f.period_start,
            period_end=f.period_end,
            document_version_id=str(f.document_version_id) if f.document_version_id else None,
        ),
    )


@dataclass(frozen=True)
class FigureComparison:
    status: str  # "computed" | "abstained"
    current: FigureResult | None = None
    prior: FigureResult | None = None
    delta: Decimal | None = None
    pct_change: Decimal | None = None
    abstention_reason: str | None = None


def compare_figures(current: FigureResult, prior: FigureResult) -> FigureComparison:
    """Deterministic comparison (period-over-period / entity-vs-entity). Both figures must be
    resolved and share a unit; the LLM never computes this — it narrates the computed result."""
    if current.status != "resolved" or prior.status != "resolved":
        return FigureComparison(
            status="abstained", abstention_reason="a figure could not be resolved"
        )
    if current.unit != prior.unit:
        return FigureComparison(
            status="abstained", abstention_reason=f"unit mismatch ({current.unit} vs {prior.unit})"
        )
    delta = current.value - prior.value  # type: ignore[operator]
    pct = (delta / prior.value * 100) if prior.value else None  # type: ignore[operator]
    return FigureComparison(
        status="computed", current=current, prior=prior, delta=delta, pct_change=pct
    )
