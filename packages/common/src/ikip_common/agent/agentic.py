"""Controller-backed retrieve — the first flow to actually *exercise* the cyclic controller
(ADR 0033 / Story 10.2). Where `decompose.py` runs a *static* fan-out (every sub-query, in
parallel), this runs the **dynamic** plan–act–observe loop: the policy picks each query from what
prior steps observed, so step N+1 can depend on step N's evidence — a **bridge / conditional hop**
("the max temp of the sensor *used by* system X": first find the sensor, then query its temp).

Why a flow was missing: the decomposition slice deliberately does NOT use the loop (its
`no_progress`/loop guards would truncate a fan-out), so the controller shipped tested-but-unused
(ADR 0033 §"Scope"). This wrapper is the eval seam to **measure** whether the loop earns its keep on
a failure class flat decomposition can't fix — same `retrieve(query) -> RetrievalOutcome` shape as
`make_decomposed_retrieve`, so it drops into the existing grounded-answer graph with no change to
generate/validate. Grounding is untouched: the loop only *gathers* cited evidence; the existing
validator + abstention still decide the answer (ADR 0022).

Single-tool for now (one tenant-scoped corpus): the loop iterates *queries* against it, which is
exactly the bridge mechanism. Multi-corpus routing (a registry with >1 tool) is a later slice.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ikip_common.agent.controller import AgentBudget, LlmControllerPolicy, run_agent
from ikip_common.agent.tools import RetrievalTool, ToolRegistry

DEFAULT_MAX_STEPS = 4  # a hard tail is usually 2–4 steps (AgentBudget default)


def make_agentic_retrieve(
    base_retrieve: Callable[[str], Any],  # Callable[[str], RetrievalOutcome]
    chat_client,  # noqa: ANN001 — ChatClient port (FakeChatClient in CI)
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    tool_name: str = "retrieval",
) -> Callable[[str], Any]:
    """Wrap a base `retrieve(query) -> RetrievalOutcome` into a **controller-driven** retrieve of
    the same shape. The cyclic controller (bounded by `AgentBudget` guardrails) picks each query
    from the observation history, unions the gathered evidence, and returns a `RetrievalOutcome`
    (abstains only if the loop gathered nothing). `RetrievalOutcome.reason` carries the loop's
    `stop_reason` when it abstains, for trajectory observability (Story 10.7)."""

    def retrieve(query: str) -> Any:
        from langchain_core.documents import Document

        from ikip_common.llm.hybrid import RetrievalOutcome

        registry = ToolRegistry()
        registry.register(
            RetrievalTool(
                name=tool_name,
                description='tenant-scoped hybrid retrieval over the corpus; args {"query": str}',
                retrieve=base_retrieve,
            )
        )
        trajectory = run_agent(
            question=query,
            registry=registry,
            policy=LlmControllerPolicy(chat_client),
            budget=AgentBudget(max_steps=max_steps),
        )
        documents = [
            Document(page_content=e.content, metadata=dict(e.provenance))
            for e in trajectory.evidence
        ]
        return RetrievalOutcome(
            documents=documents,
            abstained=not documents,
            reason=None if documents else f"agent:{trajectory.stop_reason}",
        )

    return retrieve
