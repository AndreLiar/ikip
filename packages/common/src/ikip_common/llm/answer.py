"""LangGraph grounded-answer service (Story 3.5, ADR 0022/0021).

A LangGraph `StateGraph` orchestrates the request-time RAG flow:

    analyze → retrieve → [sufficient?] → generate → validate_grounding → [ok?] → finalize
                              └ no → abstain          (draft abstained) ┘ no → abstain

Safety contract:
  - The model only sees opaque evidence handles ([E1]…); **citations are resolved
    server-side** from trusted retrieval metadata — the model cannot fabricate a
    reference (FR16).
  - After generation we **validate grounding** (entailment) and only keep supported
    claims. An unsupported *safety-critical* claim aborts the whole answer (abstain);
    an unsupported non-critical claim is dropped with a warning. We validate BEFORE
    returning anything — never surface an unverified claim.
  - Abstains ("insufficient evidence") rather than inventing (AC4); every answer
    carries a not-certified notice (AC5).

LangGraph/LangChain are used here (request-time orchestration, ADR 0021); retrieval +
tenant scoping stay in our SQL behind the injected `retrieve` callable.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TypedDict

from langchain_core.documents import Document
from langgraph.graph import END, StateGraph

from ikip_common.db.retrieval import DEFAULT_LIMIT, RetrievalFilters
from ikip_common.llm.base import ChatClient, ChatMessage
from ikip_common.llm.grounding import GroundingValidator, LLMGroundingValidator
from ikip_common.llm.hybrid import RetrievalOutcome
from ikip_common.llm.schemas import GroundedAnswer

NOT_CERTIFIED_NOTICE = (
    "This is an AI-generated summary of referenced documentation, not a certified "
    "manufacturer instruction. Verify against the cited source before acting."
)

_GENERATE_SYSTEM = (
    "You answer industrial maintenance questions using ONLY the evidence provided. "
    "Each evidence block has a handle like [E1]. Rules:\n"
    "- Ground every claim in the evidence; cite the supporting handles in evidence_markers.\n"
    "- Use ONLY handles shown; never invent a handle or use outside knowledge.\n"
    "- Mark safety_critical=true for hazards, lockout/tagout, injury or equipment-damage claims.\n"
    "- Put safety warnings / uncertainties from the evidence into warnings.\n"
    "- If the evidence does not answer the question, set status='abstained' with a reason.\n"
    "- Never present output as a certified manufacturer procedure."
)


@dataclass
class ResolvedCitation:
    """A citation resolved server-side from retrieval metadata (FR16)."""

    marker: str
    chunk_id: str | None
    document_id: str | None
    document_version_id: str | None
    revision: str | None
    is_current: bool | None
    section_id: str | None
    heading: str | None
    hierarchy_path: str | None
    page_start: int | None
    page_end: int | None


@dataclass
class AnsweredClaim:
    text: str
    safety_critical: bool
    verdict: str
    citations: list[ResolvedCitation]


@dataclass
class AnswerResult:
    status: str  # "answered" | "abstained"
    answer: str | None
    claims: list[AnsweredClaim] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    abstention_reason: str | None = None
    not_certified_notice: str = NOT_CERTIFIED_NOTICE


# --- citation resolution ---------------------------------------------------


def _citation_from_doc(marker: str, doc: Document) -> ResolvedCitation:
    m = doc.metadata
    return ResolvedCitation(
        marker=marker,
        chunk_id=m.get("chunk_id"),
        document_id=m.get("document_id"),
        document_version_id=m.get("document_version_id"),
        revision=m.get("revision"),
        is_current=m.get("is_current"),
        section_id=m.get("section_id"),
        heading=m.get("heading"),
        hierarchy_path=m.get("hierarchy_path"),
        page_start=m.get("page_start"),
        page_end=m.get("page_end"),
    )


def _apply_grounding_policy(
    draft: GroundedAnswer,
    verdict_by_index: dict[int, str],
    doc_by_marker: dict[str, Document],
) -> tuple[list[AnsweredClaim], list[str], str | None]:
    """Keep supported/partial claims, drop unsupported, abstain on unsupported
    safety-critical. Returns (kept_claims, warnings, abstain_reason|None)."""
    kept: list[AnsweredClaim] = []
    warnings: list[str] = list(draft.warnings)
    for i, claim in enumerate(draft.claims):
        verdict = verdict_by_index.get(i, "unsupported")
        known = [m for m in claim.evidence_markers if m in doc_by_marker]
        # A fabricated / unknown handle invalidates the grounding regardless of verdict.
        if len(known) != len(claim.evidence_markers) or not known:
            verdict = "unsupported"
        if verdict == "unsupported":
            if claim.safety_critical:
                return [], warnings, "a safety-critical claim was not supported by the evidence"
            warnings.append(f"dropped unsupported claim: {claim.text}")
            continue
        if verdict == "partial":
            warnings.append(f"claim only partially supported: {claim.text}")
        kept.append(
            AnsweredClaim(
                text=claim.text,
                safety_critical=claim.safety_critical,
                verdict=verdict,
                citations=[_citation_from_doc(m, doc_by_marker[m]) for m in known],
            )
        )
    return kept, warnings, None


def _render(claims: Sequence[AnsweredClaim]) -> str:
    parts = []
    for c in claims:
        markers = " ".join(f"[{cit.marker}]" for cit in c.citations)
        parts.append(f"{c.text} {markers}".strip())
    return "\n".join(parts)


# --- graph state -----------------------------------------------------------


class AnswerState(TypedDict, total=False):
    question: str
    documents: list[Document]
    doc_by_marker: dict[str, Document]
    evidence: dict[str, str]
    sufficient: bool
    draft: GroundedAnswer
    result: AnswerResult


def _evidence_block(evidence: dict[str, str]) -> str:
    return "\n\n".join(f"[{marker}] {text}" for marker, text in evidence.items())


def build_answer_graph(
    retrieve: Callable[[str], RetrievalOutcome],
    chat_client: ChatClient,
    validator: GroundingValidator,
):
    """Compile the LangGraph StateGraph with its dependencies bound into the nodes."""

    def analyze(state: AnswerState) -> AnswerState:
        # Lightweight (no LLM call — keeps to a 2-call budget): normalize the query.
        # Equipment identification refines via `filters` on the bound `retrieve`.
        return {"question": state["question"].strip()}

    def retrieve_node(state: AnswerState) -> AnswerState:
        outcome = retrieve(state["question"])
        if outcome.abstained or not outcome.documents:
            return {"sufficient": False, "documents": []}
        doc_by_marker = {f"E{i + 1}": doc for i, doc in enumerate(outcome.documents)}
        evidence = {marker: doc.page_content for marker, doc in doc_by_marker.items()}
        return {
            "sufficient": True,
            "documents": outcome.documents,
            "doc_by_marker": doc_by_marker,
            "evidence": evidence,
        }

    def generate(state: AnswerState) -> AnswerState:
        user = f"Question: {state['question']}\n\nEvidence:\n{_evidence_block(state['evidence'])}"
        messages = [
            ChatMessage(role="system", content=_GENERATE_SYSTEM),
            ChatMessage(role="user", content=user),
        ]
        return {"draft": chat_client.complete_structured(messages, GroundedAnswer)}

    def validate(state: AnswerState) -> AnswerState:
        draft = state["draft"]
        result = validator.validate(draft.claims, state["evidence"])
        verdict_by_index = {v.claim_index: v.verdict for v in result.verdicts}
        kept, warnings, abstain_reason = _apply_grounding_policy(
            draft, verdict_by_index, state["doc_by_marker"]
        )
        if abstain_reason is not None:
            return {
                "result": AnswerResult(
                    status="abstained",
                    answer=None,
                    warnings=warnings,
                    abstention_reason=abstain_reason,
                )
            }
        if not kept:
            return {
                "result": AnswerResult(
                    status="abstained",
                    answer=None,
                    warnings=warnings,
                    abstention_reason="no supported claims after grounding validation",
                )
            }
        return {
            "result": AnswerResult(
                status="answered", answer=_render(kept), claims=kept, warnings=warnings
            )
        }

    def abstain(state: AnswerState) -> AnswerState:
        draft = state.get("draft")
        reason = (
            draft.abstention_reason
            if draft and draft.abstention_reason
            else "insufficient evidence"
        )
        return {"result": AnswerResult(status="abstained", answer=None, abstention_reason=reason)}

    def route_after_retrieve(state: AnswerState) -> str:
        return "generate" if state.get("sufficient") else "abstain"

    def route_after_generate(state: AnswerState) -> str:
        return "abstain" if state["draft"].status == "abstained" else "validate"

    g = StateGraph(AnswerState)
    g.add_node("analyze", analyze)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate)
    g.add_node("validate", validate)
    g.add_node("abstain", abstain)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "retrieve")
    g.add_conditional_edges(
        "retrieve", route_after_retrieve, {"generate": "generate", "abstain": "abstain"}
    )
    g.add_conditional_edges(
        "generate", route_after_generate, {"validate": "validate", "abstain": "abstain"}
    )
    g.add_edge("validate", END)
    g.add_edge("abstain", END)
    return g.compile()


def grounded_answer(
    question: str,
    *,
    retrieve: Callable[[str], RetrievalOutcome],
    chat_client: ChatClient,
    validator: GroundingValidator | None = None,
) -> AnswerResult:
    """Run the grounded-answer graph once and return the final AnswerResult."""
    validator = validator or LLMGroundingValidator(chat_client)
    graph = build_answer_graph(retrieve, chat_client, validator)
    final = graph.invoke({"question": question})
    return final["result"]


def make_hybrid_retrieve(
    session,  # noqa: ANN001  (SQLAlchemy Session)
    tenant_id: uuid.UUID,
    embedding_client,  # noqa: ANN001  (EmbeddingClient)
    *,
    filters: RetrievalFilters | None = None,
    limit: int = DEFAULT_LIMIT,
    lexical_min_score: float | None = None,
    vector_min_score: float | None = None,
) -> Callable[[str], RetrievalOutcome]:
    """Bind our tenant-scoped hybrid retrieval into a `retrieve(query)` callable for
    the graph. Tenant scoping + citations stay in our SQL (ADR 0021)."""
    from ikip_common.llm.hybrid import hybrid_retrieve

    def retrieve(query: str) -> RetrievalOutcome:
        return hybrid_retrieve(
            session,
            tenant_id,
            query,
            embedding_client,
            filters=filters,
            limit=limit,
            lexical_min_score=lexical_min_score,
            vector_min_score=vector_min_score,
        )

    return retrieve
