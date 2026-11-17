"""Query decomposition tests (ADR 0033 / Story 10.5). Pure — fake chat + fake retrieve."""

from dataclasses import dataclass, field

import pytest
from ikip_common.agent.decompose import (
    decompose_question,
    fan_out_retrieve,
    make_decomposed_retrieve,
)
from ikip_common.agent.tools import RetrievalTool, ToolEvidence


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


class _FakeChat:
    def __init__(self, out) -> None:  # noqa: ANN001
        self._out = out

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages, schema):  # noqa: ANN001, ANN201, ARG002
        if isinstance(self._out, Exception):
            raise self._out
        return schema(sub_questions=self._out)


# --- decompose_question --------------------------------------------------------------------


def test_splits_a_compound_question() -> None:
    chat = _FakeChat(["what is the cable path?", "what limits transmission speed?"])
    assert decompose_question(chat, "cable path and speed?") == [
        "what is the cable path?",
        "what limits transmission speed?",
    ]


def test_single_ask_returns_original_unchanged() -> None:
    # model echoes one part -> treat as single-shot (no fan-out overhead)
    assert decompose_question(_FakeChat(["just one thing"]), "just one thing") == ["just one thing"]


def test_empty_split_falls_back_to_original() -> None:
    assert decompose_question(_FakeChat([]), "q") == ["q"]


def test_error_falls_back_to_original() -> None:
    # decomposition must never break retrieval
    assert decompose_question(_FakeChat(RuntimeError("llm down")), "q") == ["q"]


def test_caps_fan_out_at_max_parts() -> None:
    chat = _FakeChat(["a?", "b?", "c?", "d?", "e?"])
    assert decompose_question(chat, "many", max_parts=3) == ["a?", "b?", "c?"]


# --- fan_out_retrieve ----------------------------------------------------------------------


def _tool_returning(mapping: dict[str, list[str]]) -> RetrievalTool:
    # a RetrievalTool whose base retrieve returns a doc per chunk id, keyed by the sub-query
    def retrieve(q):  # noqa: ANN001, ANN202
        return _Outcome(
            [
                _Doc(page_content=f"passage {cid}", metadata={"chunk_id": cid})
                for cid in mapping.get(q, [])
            ]
        )

    return RetrievalTool(name="r", description="x", retrieve=retrieve)


def test_fan_out_unions_and_dedups_by_chunk_id() -> None:
    tool = _tool_returning({"q1": ["c1", "c2"], "q2": ["c2", "c3"]})  # c2 overlaps
    out = fan_out_retrieve(tool, ["q1", "q2"])
    assert [e.provenance["chunk_id"] for e in out] == ["c1", "c2", "c3"]
    assert all(isinstance(e, ToolEvidence) for e in out)


def test_fan_out_runs_every_sub_query_even_if_one_adds_nothing() -> None:
    # q2 returns only a dup -> a dynamic agent would stop (no_progress), but a fan-out must still
    # run q3. This is why decomposition does NOT go through the cyclic controller.
    tool = _tool_returning({"q1": ["c1"], "q2": ["c1"], "q3": ["c2"]})
    out = fan_out_retrieve(tool, ["q1", "q2", "q3"])
    assert [e.provenance["chunk_id"] for e in out] == ["c1", "c2"]  # q3 still contributed c2


# --- make_decomposed_retrieve (integration; langchain for Document/RetrievalOutcome) -------


def test_decomposed_retrieve_merges_parts() -> None:
    pytest.importorskip("langchain_core")
    mapping = {"sub a?": ["c1"], "sub b?": ["c2"]}

    def base_retrieve(q):  # noqa: ANN001, ANN202
        return _Outcome(
            [
                _Doc(page_content=f"p {cid}", metadata={"chunk_id": cid})
                for cid in mapping.get(q, [])
            ]
        )

    chat = _FakeChat(["sub a?", "sub b?"])
    retrieve = make_decomposed_retrieve(base_retrieve, chat)
    outcome = retrieve("compound a and b?")
    assert [d.metadata["chunk_id"] for d in outcome.documents] == ["c1", "c2"]
    assert outcome.abstained is False


def test_decomposed_retrieve_degrades_to_base_for_single_ask() -> None:
    pytest.importorskip("langchain_core")
    calls = []

    def base_retrieve(q):  # noqa: ANN001, ANN202
        calls.append(q)
        return _Outcome([_Doc(page_content="p", metadata={"chunk_id": "c1"})])

    # model returns a single part -> retrieve the ORIGINAL query once, no fan-out
    retrieve = make_decomposed_retrieve(base_retrieve, _FakeChat(["one"]))
    retrieve("simple question?")
    assert calls == ["simple question?"]  # base called once with the original query
