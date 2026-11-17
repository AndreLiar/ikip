"""Query decomposition — the first measured flow on the agentic foundation (ADR 0033 / Story 10.5).

[MISSION-049](../../../docs/learning/missions/MISSION-049/mission.md) measured the gap: on multi-hop
questions a single retrieval surfaces ≈one hop's evidence (recall@5 0.889 → 0.444 at 2 hops), and
neither a bigger k nor a single-query rewrite fixes it — **only asking the parts separately** does
(→ 0.889). This implements that fix:

    decompose (1 LLM call) → fan-out retrieval (each sub-question, via a RetrievalTool) → merge
    (union, dedup by chunk_id) → hand to the EXISTING generate/validate

The agentic decision is the **split** (the model decides *how many* retrievals and *what* they are);
the fan-out is deterministic. So this uses the foundation's **Tool port** (`RetrievalTool` — carries
provenance, tenant-scoped) but *not* the cyclic controller's dynamic loop: a static plan wants to
run *every* sub-query, whereas the loop's `no_progress`/loop guards exist to stop a *dynamic* agent
— they'd wrongly truncate a fan-out. The controller is reserved for capabilities whose steps depend
on prior observations (iterative/conditional hops) — not needed here.

Grounding is untouched: generation still answers the **original** question over the merged, cited
evidence; the validator + abstention are unchanged (ADR 0022). `decompose_question` +
`fan_out_retrieve` are base-env safe; `make_decomposed_retrieve` lazily builds LangChain
`Document`s/`RetrievalOutcome` for the existing graph.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from ikip_common.agent.tools import RetrievalTool, ToolEvidence

DEFAULT_MAX_PARTS = 4  # cap the fan-out (cost/latency bound); a hard tail is 2–3 parts

_SYSTEM = (
    "You split a user's question into the minimal set of self-contained sub-questions needed to "
    "answer it — one per distinct thing it asks. If it already asks only one thing, return just "
    "that question unchanged. Preserve intent exactly; resolve pronouns so each sub-question "
    "stands alone; never add facts or invent sub-questions. Fewer is better."
)


class _Decomposition(BaseModel):
    sub_questions: list[str] = Field(default_factory=list)


def decompose_question(
    chat_client,  # noqa: ANN001 — ChatClient port (FakeChatClient in CI)
    question: str,
    *,
    max_parts: int = DEFAULT_MAX_PARTS,
) -> list[str]:
    """Split a compound question into sub-questions. Returns `[question]` unchanged when it's a
    single ask, or on any failure (decomposition must never break retrieval — it degrades to the
    normal single-shot path). Caps the fan-out at `max_parts`."""
    from ikip_common.llm.base import ChatMessage

    try:
        out = chat_client.complete_structured(
            [
                ChatMessage(role="system", content=_SYSTEM),
                ChatMessage(role="user", content=f"Question: {question}\n\nSub-questions:"),
            ],
            _Decomposition,
        )
        parts = [p.strip() for p in (out.sub_questions or []) if p and p.strip()]
    except Exception:  # noqa: BLE001 — never break retrieval on a decomposition failure
        return [question]
    if len(parts) <= 1:
        return [question]  # single ask (or the model echoed it) → normal path, no fan-out overhead
    return parts[:max_parts]


def fan_out_retrieve(tool: RetrievalTool, sub_queries: Sequence[str]) -> list[ToolEvidence]:
    """Retrieve each sub-question through the tool and union the evidence, de-duplicating by
    `chunk_id` (so overlapping hops don't double-count). Deterministic — runs *every* sub-query
    (unlike the dynamic controller, which may stop early). Provenance is preserved per passage."""
    seen: set[Any] = set()
    merged: list[ToolEvidence] = []
    for sq in sub_queries:
        result = tool.invoke({"query": sq})
        for ev in result.evidence:
            cid = ev.provenance.get("chunk_id")
            if cid in seen:
                continue
            seen.add(cid)
            merged.append(ev)
    return merged


def make_decomposed_retrieve(
    base_retrieve: Callable[[str], Any],  # Callable[[str], RetrievalOutcome]
    chat_client,  # noqa: ANN001 — ChatClient port
    *,
    max_parts: int = DEFAULT_MAX_PARTS,
    tool_name: str = "retrieval",
) -> Callable[[str], Any]:
    """Wrap a base `retrieve(query) -> RetrievalOutcome` into a **decomposing** retrieve of the same
    shape, so it drops into the existing grounded-answer graph with no change to generate/validate.

    For a single-ask question it calls `base_retrieve` directly (zero overhead). For a compound one
    it decomposes, fans out over a `RetrievalTool` wrapping `base_retrieve`, and returns the merged
    evidence as a `RetrievalOutcome` (abstains only if *every* sub-query did)."""

    def retrieve(query: str) -> Any:
        sub_queries = decompose_question(chat_client, query, max_parts=max_parts)
        if len(sub_queries) <= 1:
            return base_retrieve(query)

        from langchain_core.documents import Document

        from ikip_common.llm.hybrid import RetrievalOutcome

        tool = RetrievalTool(
            name=tool_name,
            description="tenant-scoped hybrid retrieval over the corpus",
            retrieve=base_retrieve,
        )
        evidence = fan_out_retrieve(tool, sub_queries)
        documents = [
            Document(page_content=e.content, metadata=dict(e.provenance)) for e in evidence
        ]
        return RetrievalOutcome(documents=documents, abstained=not documents)

    return retrieve
