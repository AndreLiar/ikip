"""Hybrid structured + unstructured answering (Epic 8, Story 8.2 AC1, ADR 0030).

Join an exact **figure** (from the fact store, with its filing citation) with **narrative document
evidence** (chunks, with their citations) into **one** cited answer — "revenue was $X, and here is
why it changed". Two evidence types, two citation types, one answer:

  - the figure stays numerically **guarded** (the stated number must match the retrieved fact or we
    abstain — a figure is never generated, ADR 0030);
  - narrative claims are grounded in the `[D#]` document evidence and cited to their chunks (FR16).

The document evidence enters as plain `DocEvidence` (not LangChain `Document`), so the fusion core
stays import-light + testable in the base env; the request-time graph adapts its hits into it.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ikip_common.finance import (
    FigureCitation,
    FigureComparison,
    FigureQuery,
    FigureResult,
    compare_figures,
    retrieve_figure,
)
from ikip_common.finance_answer import (
    FigureNarration,
    answer_states_value,
    resolve_entity,
    route_figure_query,
)
from ikip_common.llm.base import ChatClient, ChatMessage


@dataclass(frozen=True)
class DocEvidence:
    """A narrative evidence block for fusion (a retrieved chunk, citation-resolved, FR16)."""

    marker: str  # e.g. "D1"
    text: str
    chunk_id: str | None = None
    document_id: str | None = None
    page_start: int | None = None


@dataclass
class FusedAnswer:
    status: str  # answered | abstained | not_a_figure_query
    answer: str | None = None
    figure: FigureResult | None = None
    figure_citation: FigureCitation | None = None
    comparison: FigureComparison | None = None
    doc_citations: list[DocEvidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    abstention_reason: str | None = None


_FUSE_SYS = (
    "You answer a financial question in two parts, using ONLY what you are given. (1) State the "
    "exact FIGURE provided, quoting it (you may format with units, e.g. '$383.3 billion'); never "
    "state a number not given, and never compute — any comparison is already provided. (2) Add "
    "brief narrative CONTEXT grounded ONLY in the [D#] evidence, citing the [D#] you use. If the "
    "[D#] evidence doesn't explain it, give the figure alone. Keep it to 2-3 sentences."
)


def _fused_evidence(
    fig: FigureResult, comp: FigureComparison | None, docs: list[DocEvidence]
) -> str:
    cit = fig.citation
    lines = [
        f"FIGURE: {fig.concept} = {fig.value} {fig.unit} for period ending {fig.period_end} "
        f"(FY{fig.fiscal_year} {fig.fiscal_period}); source filing {cit.accession} ({cit.form})."
    ]
    if comp and comp.status == "computed" and comp.prior:
        lines.append(
            f"PRIOR: {comp.prior.value} {comp.prior.unit} (ending {comp.prior.period_end}); "
            f"COMPUTED change = {comp.delta} ({comp.pct_change:.2f}%)."
        )
    for d in docs:
        lines.append(f"[{d.marker}] {d.text}")
    return "\n".join(lines)


def fuse_answer(
    question: str,
    fig: FigureResult,
    docs: list[DocEvidence],
    chat: ChatClient,
    *,
    comparison: FigureComparison | None = None,
) -> FusedAnswer:
    """Compose one answer over an exact figure + narrative docs; guard the figure; return both
    citation sets. Abstains if the generated answer's figure doesn't match the fact."""
    if fig.status != "resolved":
        return FusedAnswer(status="abstained", figure=fig, abstention_reason=fig.abstention_reason)
    narration = chat.complete_structured(
        [
            ChatMessage(role="system", content=_FUSE_SYS),
            ChatMessage(
                role="user",
                content=(
                    f"Question: {question}\n\nEvidence:\n{_fused_evidence(fig, comparison, docs)}"
                ),
            ),
        ],
        FigureNarration,
    )
    answer = (narration.answer or "").strip()
    if not answer_states_value(answer, fig.value):  # type: ignore[arg-type]
        return FusedAnswer(
            status="abstained",
            figure=fig,
            comparison=comparison,
            abstention_reason="generated answer's figure did not match the retrieved fact",
        )
    # Keep only the doc citations actually referenced by marker in the answer (no phantom cites).
    cited = [d for d in docs if f"[{d.marker}]" in answer]
    warnings: list[str] = []
    if (
        comparison
        and comparison.status == "computed"
        and comparison.prior
        and not answer_states_value(
            answer,
            comparison.prior.value,  # type: ignore[arg-type]
        )
    ):
        warnings.append("prior-period figure not clearly stated")
    return FusedAnswer(
        status="answered",
        answer=answer,
        figure=fig,
        figure_citation=fig.citation,
        comparison=comparison,
        doc_citations=cited,
        warnings=warnings,
    )


def answer_financial_question(
    question: str,
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    chat: ChatClient,
    entities: dict[str, str],
    retrieve_docs: Callable[[str], list[DocEvidence]],
) -> FusedAnswer:
    """Route → figure (exact) → narrative docs → fused, guarded answer. Non-figure questions
    return status 'not_a_figure_query' so the caller falls back to the pure document path."""
    route = route_figure_query(chat, question)
    if not route.is_figure_query:
        return FusedAnswer(status="not_a_figure_query")
    if not route.concept:
        return FusedAnswer(status="abstained", abstention_reason="could not identify the figure")
    cik = resolve_entity(route.entity_name, entities)
    if not cik:
        return FusedAnswer(
            status="abstained", abstention_reason=f"unknown entity: {route.entity_name!r}"
        )

    fig = retrieve_figure(
        session,
        tenant_id,
        FigureQuery(
            entity_cik=cik,
            concept=route.concept,
            fiscal_year=route.fiscal_year,
            fiscal_period=route.fiscal_period,
            unit=route.unit,
        ),
    )
    if fig.status != "resolved":
        return FusedAnswer(status="abstained", figure=fig, abstention_reason=fig.abstention_reason)

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

    docs = retrieve_docs(question)
    return fuse_answer(question, fig, docs, chat, comparison=comp)
