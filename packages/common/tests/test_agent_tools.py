"""Tool port + registry tests (ADR 0033 / Story 10.1). Pure — fakes, no DB/LLM/network."""

from dataclasses import dataclass, field

import pytest
from ikip_common.agent.tools import (
    FakeTool,
    RetrievalTool,
    Tool,
    ToolEvidence,
    ToolRegistry,
    ToolResult,
)


# --- a minimal stand-in for RetrievalOutcome + Document (structural, no langchain) -----------
@dataclass
class _Doc:
    page_content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class _Outcome:
    documents: list
    abstained: bool = False
    reason: str | None = None


# --- RetrievalTool -------------------------------------------------------------------------


def test_retrieval_tool_maps_outcome_to_evidence_with_provenance() -> None:
    doc = _Doc(page_content="pump spec", metadata={"chunk_id": "c1", "document_id": "d1"})
    tool = RetrievalTool(
        name="manuals", description="aircraft manuals", retrieve=lambda q: _Outcome([doc])
    )
    res = tool.invoke({"query": "pump torque?"})
    assert res.tool == "manuals"
    assert res.abstained is False
    assert res.evidence == [
        ToolEvidence(content="pump spec", provenance={"chunk_id": "c1", "document_id": "d1"})
    ]


def test_retrieval_tool_propagates_abstention() -> None:
    tool = RetrievalTool(
        name="manuals",
        description="x",
        retrieve=lambda q: _Outcome([], abstained=True, reason="insufficient"),
    )
    res = tool.invoke({"query": "unknown"})
    assert res.abstained is True
    assert res.reason == "insufficient"
    assert res.evidence == []


def test_retrieval_tool_empty_query_abstains_without_calling_retrieve() -> None:
    def boom(_q):  # noqa: ANN001, ANN202
        raise AssertionError("retrieve must not be called on an empty query")

    res = RetrievalTool(name="m", description="x", retrieve=boom).invoke({"query": "   "})
    assert res.abstained is True and res.reason == "empty query"


def test_retrieval_tool_is_tenant_scoped_by_construction() -> None:
    # The tool can only ever reach whatever its injected `retrieve` reaches — there is no tenant arg
    # on invoke(), so a caller cannot redirect it to another tenant (NFR10, structural).
    seen = []
    RetrievalTool(
        name="t", description="x", retrieve=lambda q: seen.append(q) or _Outcome([])
    ).invoke({"query": "q"})
    assert seen == [
        "q"
    ]  # invoke takes only the query; tenant is bound in the closure, not passable


# --- Tool protocol + FakeTool --------------------------------------------------------------


def test_fake_tool_records_calls_and_returns_canned_result() -> None:
    canned = ToolResult(tool="fake", value=42)
    t = FakeTool(result=canned)
    assert t.invoke({"query": "x"}) is canned
    assert t.calls == [{"query": "x"}]


def test_both_tools_satisfy_the_port() -> None:
    assert isinstance(FakeTool(), Tool)
    assert isinstance(
        RetrievalTool(name="t", description="d", retrieve=lambda q: _Outcome([])), Tool
    )


# --- ToolRegistry --------------------------------------------------------------------------


def test_registry_register_get_names() -> None:
    reg = ToolRegistry()
    a, b = (
        FakeTool(name="assurance", description="FR insurance"),
        FakeTool(name="law", description="FR law"),
    )
    reg.register(a)
    reg.register(b)
    assert reg.names() == ["assurance", "law"]  # sorted, stable
    assert reg.get("law") is b
    assert "assurance" in reg and len(reg) == 2


def test_registry_rejects_duplicate_names() -> None:
    reg = ToolRegistry()
    reg.register(FakeTool(name="dup"))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(FakeTool(name="dup"))


def test_registry_get_unknown_raises() -> None:
    with pytest.raises(KeyError, match="unknown tool"):
        ToolRegistry().get("nope")


def test_registry_describe_renders_the_controller_menu() -> None:
    reg = ToolRegistry()
    reg.register(FakeTool(name="manuals", description="aircraft manuals"))
    reg.register(FakeTool(name="calc", description="unit/torque calculator"))
    assert reg.describe() == "- calc: unit/torque calculator\n- manuals: aircraft manuals"
