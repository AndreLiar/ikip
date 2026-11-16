"""Figure-question answering: NL router + grounded numeric answer (Epic 8, Story 8.2, ADR 0030).

Ties the user's natural-language question to the deterministic fact store:
  1. **Route** (LLM, structured output) — is this a figure question? which entity/concept/period?
  2. **Resolve + retrieve** — entity name → CIK (tenant's filer map), then `retrieve_figure`
     (exact SQL, abstains on unavailable/ambiguous — the number is looked up, not approximated).
  3. **Narrate** (LLM) — compose prose around the exact value, quoting it.
  4. **Guard (pure, the safety crux)** — the number in the generated answer MUST match the
     retrieved fact (within rounding) or we **abstain**. This is what keeps the figure
     *retrieved, not generated*: the LLM narrates, but it cannot fabricate or miscopy the number.

The LLM calls go through the `ChatClient` port (FakeChatClient in CI). The guard + entity/amount
parsing are pure. Comparisons (period-over-period) reuse `compare_figures` — arithmetic in code.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from ikip_common.finance import (
    FigureComparison,
    FigureQuery,
    FigureResult,
    compare_figures,
    retrieve_figure,
)
from ikip_common.llm.base import ChatClient, ChatMessage

_SCALES = {
    "trillion": Decimal(10) ** 12,
    "tn": Decimal(10) ** 12,
    "t": Decimal(10) ** 12,
    "billion": Decimal(10) ** 9,
    "bn": Decimal(10) ** 9,
    "b": Decimal(10) ** 9,
    "million": Decimal(10) ** 6,
    "mn": Decimal(10) ** 6,
    "m": Decimal(10) ** 6,
    "thousand": Decimal(10) ** 3,
    "k": Decimal(10) ** 3,
}
_AMOUNT = re.compile(
    r"\$?\s?(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand|tn|bn|mn|t|b|m|k)?\b",
    re.IGNORECASE,
)


class RoutedFigureQuery(BaseModel):
    """Structured LLM routing of a question into a figure request (or not)."""

    is_figure_query: bool
    entity_name: str | None = None
    concept: str | None = None  # XBRL tag (best effort), e.g. "Revenues"
    fiscal_year: int | None = None
    fiscal_period: str | None = None  # FY | Q1..Q4
    unit: str | None = None
    prior_fiscal_year: int | None = None  # set for a period-over-period comparison


class FigureNarration(BaseModel):
    answer: str


@dataclass
class FigureAnswer:
    status: str  # answered | abstained | not_a_figure_query
    answer: str | None = None
    figure: FigureResult | None = None
    comparison: FigureComparison | None = None
    abstention_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def resolve_entity(name: str | None, entities: dict[str, str]) -> str | None:
    """Map an entity name to a CIK using the tenant's filer map (case/space-insensitive)."""
    if not name:
        return None
    norm = {k.lower().strip(): v for k, v in entities.items()}
    return norm.get(name.lower().strip())


def parse_amounts(text: str) -> list[Decimal]:
    """Extract monetary/number mentions as Decimals, applying scale words ($383.3 billion → ...)."""
    out: list[Decimal] = []
    for digits, scale in _AMOUNT.findall(text):
        try:
            val = Decimal(digits.replace(",", ""))
        except InvalidOperation:
            continue
        if scale:
            val *= _SCALES[scale.lower()]
        out.append(val)
    return out


def answer_states_value(answer: str, value: Decimal, *, rel_tol: Decimal = Decimal("0.01")) -> bool:
    """True if the answer states a number consistent with `value` (exact or rounded within
    rel_tol). Rounding like '383.3 billion' matches 383,285,000,000; a wrong figure (390 bn) does
    not. This is the guard that forbids a fabricated/miscopied figure."""
    if value == 0:
        return any(a == 0 for a in parse_amounts(answer))
    tol = abs(value) * rel_tol
    return any(abs(a - value) <= tol for a in parse_amounts(answer))


_ROUTE_SYS = (
    "You route a user question for a financial-figure system. Decide if it asks for a specific "
    "reported figure (e.g. revenue, assets, net income) for a company and period. If so, set "
    "is_figure_query=true and fill entity_name, the XBRL us-gaap concept tag (best effort, e.g. "
    "'Revenues', 'Assets', 'NetIncomeLoss'), fiscal_year, fiscal_period (FY or Q1..Q4), and "
    "prior_fiscal_year if it asks for a change/comparison. Otherwise is_figure_query=false. "
    "Never answer the question or invent a number."
)
_NARRATE_SYS = (
    "You write a one- or two-sentence answer to a financial question using ONLY the exact "
    "figure(s) given. Quote the figure as provided (you may format with units, e.g. '$383.3 "
    "billion'). Do NOT state any number not given to you, and do NOT compute values yourself — "
    "any comparison is already computed and provided. Cite the period."
)


def route_figure_query(chat: ChatClient, question: str) -> RoutedFigureQuery:
    return chat.complete_structured(
        [
            ChatMessage(role="system", content=_ROUTE_SYS),
            ChatMessage(role="user", content=question),
        ],
        RoutedFigureQuery,
    )


def _evidence(fig: FigureResult, comp: FigureComparison | None) -> str:
    cit = fig.citation
    lines = [
        f"FIGURE: {fig.concept} = {fig.value} {fig.unit} "
        f"for period ending {fig.period_end} (FY{fig.fiscal_year} {fig.fiscal_period}); "
        f"source filing {cit.accession} ({cit.form})."
    ]
    if comp and comp.status == "computed" and comp.prior:
        lines.append(
            f"PRIOR: {comp.prior.value} {comp.prior.unit} (period ending {comp.prior.period_end}). "
            f"COMPUTED change = {comp.delta} ({comp.pct_change:.2f}%)."
        )
    return "\n".join(lines)


def answer_figure_question(
    question: str,
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    chat: ChatClient,
    entities: dict[str, str],
) -> FigureAnswer:
    """Route → retrieve (exact) → narrate → numeric-guard. Abstains rather than surface an
    unverifiable number. `entities` maps the tenant's filer names to CIKs."""
    route = route_figure_query(chat, question)
    if not route.is_figure_query:
        return FigureAnswer(status="not_a_figure_query")
    if not route.concept:
        return FigureAnswer(status="abstained", abstention_reason="could not identify the figure")
    cik = resolve_entity(route.entity_name, entities)
    if not cik:
        return FigureAnswer(
            status="abstained", abstention_reason=f"unknown entity: {route.entity_name!r}"
        )

    q = FigureQuery(
        entity_cik=cik,
        concept=route.concept,
        fiscal_year=route.fiscal_year,
        fiscal_period=route.fiscal_period,
        unit=route.unit,
    )
    fig = retrieve_figure(session, tenant_id, q)
    if fig.status != "resolved":
        return FigureAnswer(status="abstained", figure=fig, abstention_reason=fig.abstention_reason)

    comp: FigureComparison | None = None
    if route.prior_fiscal_year is not None:
        prior = retrieve_figure(
            session,
            tenant_id,
            FigureQuery(
                entity_cik=cik,
                concept=route.concept,
                fiscal_year=route.prior_fiscal_year,
                fiscal_period=route.fiscal_period,
                unit=fig.unit,
            ),
        )
        comp = compare_figures(fig, prior)

    narration = chat.complete_structured(
        [
            ChatMessage(role="system", content=_NARRATE_SYS),
            ChatMessage(
                role="user", content=f"Question: {question}\n\nEvidence:\n{_evidence(fig, comp)}"
            ),
        ],
        FigureNarration,
    )
    answer = (narration.answer or "").strip()

    # The guard (ADR 0030): the stated figure MUST match the retrieved fact, else we can't trust
    # the number — abstain rather than surface it. A requested comparison must also state the prior.
    if not answer_states_value(answer, fig.value):  # type: ignore[arg-type]
        return FigureAnswer(
            status="abstained",
            figure=fig,
            comparison=comp,
            abstention_reason="generated answer's figure did not match the retrieved fact",
        )
    warnings: list[str] = []
    if (
        comp
        and comp.status == "computed"
        and comp.prior
        and not answer_states_value(
            answer,
            comp.prior.value,  # type: ignore[arg-type]
        )
    ):
        warnings.append("prior-period figure not clearly stated in the answer")
    return FigureAnswer(
        status="answered", answer=answer, figure=fig, comparison=comp, warnings=warnings
    )
