"""Controller-backed retrieve tests (ADR 0033 / Story 10.2). Pure — scripted chat + fake retrieve.

Mirrors test_agent_decompose.py: the loop logic + guardrails are already covered in
test_agent_controller.py; here we only check the eval seam — that make_agentic_retrieve drives the
cyclic controller over a RetrievalTool and returns a RetrievalOutcome of the same shape as the
fixed/decompose paths (so it drops into the existing graph unchanged)."""

from dataclasses import dataclass, field

import pytest
from ikip_common.agent.agentic import make_agentic_retrieve


# --- structural stand-ins (no langchain) ---------------------------------------------------
@dataclass
class _Doc:
    page_content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class _Outcome:
    documents: list
    abstained: bool = False
    reason: str | None = None


class _ScriptChat:
    """Replays one structured controller decision per call (then repeats the last) — so the loop's
    step sequence is deterministic. Each `out` is the kwargs for the _ControllerDecision schema."""

    def __init__(self, outs: list[dict]) -> None:
        self._outs = outs
        self._i = 0

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages, schema):  # noqa: ANN001, ANN201, ARG002
        out = self._outs[min(self._i, len(self._outs) - 1)]
        self._i += 1
        return schema(**out)


def test_agentic_retrieve_gathers_evidence_across_loop_steps() -> None:
    pytest.importorskip("langchain_core")
    mapping = {"q0": ["c1"], "q1": ["c2"]}  # two queries surface two distinct chunks

    def base_retrieve(q):  # noqa: ANN001, ANN202
        return _Outcome([_Doc(f"p {cid}", {"chunk_id": cid}) for cid in mapping.get(q, [])])

    chat = _ScriptChat(
        [
            {"tool": "retrieval", "query": "q0"},
            {"tool": "retrieval", "query": "q1"},
            {"tool": None},  # stop
        ]
    )
    outcome = make_agentic_retrieve(base_retrieve, chat, max_steps=4)("bridge question")
    assert [d.metadata["chunk_id"] for d in outcome.documents] == ["c1", "c2"]
    assert outcome.abstained is False


def test_agentic_retrieve_degrades_when_tenant_over_budget() -> None:
    pytest.importorskip("langchain_core")
    import uuid

    from ikip_common.budget import InMemoryBudgetLedger

    tenant = uuid.UUID("c0f90000-0000-4000-8000-0000000000b2")
    ledger = InMemoryBudgetLedger(cap_usd=0.001)  # tiny cap → any query's worst-case exceeds it
    called = []

    def base_retrieve(q):  # noqa: ANN001, ANN202
        called.append(q)
        return _Outcome([_Doc("p", {"chunk_id": "c1"})])

    chat = _ScriptChat([{"tool": "retrieval", "query": "q0"}, {"tool": None}])
    outcome = make_agentic_retrieve(base_retrieve, chat, ledger=ledger, tenant_id=tenant)("q")
    assert outcome.abstained is True and outcome.reason == "budget:tenant-cap-exceeded"
    assert called == []  # degraded BEFORE spending — base retrieve never ran


def test_agentic_retrieve_charges_the_ledger_per_step() -> None:
    pytest.importorskip("langchain_core")
    import uuid

    from ikip_common.budget import InMemoryBudgetLedger

    tenant = uuid.UUID("c0f90000-0000-4000-8000-0000000000b2")
    ledger = InMemoryBudgetLedger(cap_usd=100.0)  # generous → runs, then charges

    def base_retrieve(q):  # noqa: ANN001, ANN202
        return _Outcome([_Doc(f"p {q}", {"chunk_id": q})])

    chat = _ScriptChat([{"tool": "retrieval", "query": "a"}, {"tool": None}])
    make_agentic_retrieve(base_retrieve, chat, ledger=ledger, tenant_id=tenant)("q")
    assert ledger.spent(tenant) > 0.0  # one step ran → a non-zero charge landed


def test_agentic_retrieve_abstains_and_reports_stop_reason_when_empty() -> None:
    pytest.importorskip("langchain_core")

    def base_retrieve(q):  # noqa: ANN001, ANN202
        return _Outcome([])  # nothing retrieved -> the loop makes no progress

    chat = _ScriptChat([{"tool": "retrieval", "args": {"query": "q0"}}, {"tool": None}])
    outcome = make_agentic_retrieve(base_retrieve, chat)("q")
    assert outcome.documents == [] and outcome.abstained is True
    assert (
        outcome.reason == "agent:no_progress"
    )  # trajectory stop_reason surfaced for observability
