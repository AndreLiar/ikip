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

import uuid
from collections.abc import Callable
from typing import Any

from ikip_common.agent.controller import AgentBudget, LlmControllerPolicy, run_agent
from ikip_common.agent.tools import RetrievalTool, ToolRegistry, ToolResult
from ikip_common.budget import BudgetLedger

DEFAULT_MAX_STEPS = 4  # a hard tail is usually 2–4 steps (AgentBudget default)
# Flat estimate of one controller step (one gpt-5.4-mini decision + one retrieval) at the indicative
# Azure rates. Precise enough to CAP a loop, not for billing — a hard ceiling, not exact
# accounting (ADR 0034).
STEP_COST_USD = 0.002


def _step_cost(_action: Any, _result: ToolResult | None) -> float:
    return STEP_COST_USD


def make_agentic_retrieve(
    base_retrieve: Callable[[str], Any],  # Callable[[str], RetrievalOutcome]
    chat_client,  # noqa: ANN001 — ChatClient port (FakeChatClient in CI)
    *,
    max_steps: int = DEFAULT_MAX_STEPS,
    tool_name: str = "retrieval",
    ledger: BudgetLedger | None = None,
    tenant_id: uuid.UUID | None = None,
) -> Callable[[str], Any]:
    """Wrap a base `retrieve(query) -> RetrievalOutcome` into a **controller-driven** retrieve of
    the same shape. The cyclic controller (bounded by `AgentBudget` guardrails) picks each query
    from the observation history, unions the gathered evidence, and returns a `RetrievalOutcome`
    (abstains only if the loop gathered nothing). `RetrievalOutcome.reason` carries the loop's
    `stop_reason` when it abstains, for trajectory observability (Story 10.7).

    When a `ledger` + `tenant_id` are given, the per-tenant **spend cap** (ADR 0034) is enforced
    around the loop: if the worst-case cost of this query would cross the tenant's cap, the agentic
    branch **degrades to abstention** (never overspends, never crashes); otherwise the loop runs and
    its actual step cost is charged. The loop is also cost-capped per query (`AgentBudget`)."""

    def retrieve(query: str) -> Any:
        from langchain_core.documents import Document

        from ikip_common.llm.hybrid import RetrievalOutcome

        worst_case = max_steps * STEP_COST_USD
        if (
            ledger is not None
            and tenant_id is not None
            and ledger.would_exceed(tenant_id, worst_case)
        ):
            return RetrievalOutcome(
                documents=[], abstained=True, reason="budget:tenant-cap-exceeded"
            )

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
            cost_fn=_step_cost,
        )
        if ledger is not None and tenant_id is not None:
            ledger.charge(tenant_id, len(trajectory.steps) * STEP_COST_USD)

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
