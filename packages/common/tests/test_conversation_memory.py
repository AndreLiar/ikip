"""Conversational query-contextualization tests (ADR 0032 layer 1). Pure — fake ChatClient."""

import uuid
from collections.abc import Sequence

import pytest
from ikip_common.conversation_memory import StandaloneQuery, contextualize_query
from ikip_common.llm.base import ChatMessage


class _FakeChat:
    def __init__(self, out) -> None:  # noqa: ANN001
        self._out = out

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages: Sequence[ChatMessage], schema: type):  # noqa: ANN201
        if isinstance(self._out, Exception):
            raise self._out
        return schema(query=self._out)


_HISTORY = [("What was Apple's FY2023 revenue?", "It was $383.3 billion.")]


def test_resolves_followup_into_standalone_query() -> None:
    chat = _FakeChat("What was Apple's FY2023 Q2 revenue?")
    out = contextualize_query(chat, "and Q2?", _HISTORY)
    assert out == "What was Apple's FY2023 Q2 revenue?"


def test_no_history_returns_question_unchanged_without_calling_llm() -> None:
    # No history -> no LLM call at all (a raised error would surface if it were called).
    chat = _FakeChat(RuntimeError("should not be called"))
    assert contextualize_query(chat, "What is the revenue?", []) == "What is the revenue?"


def test_falls_back_on_empty_output() -> None:
    assert contextualize_query(_FakeChat("   "), "and Q2?", _HISTORY) == "and Q2?"


def test_falls_back_on_client_error() -> None:
    # Retrieval must never break on a contextualization failure.
    assert (
        contextualize_query(_FakeChat(RuntimeError("llm down")), "and Q2?", _HISTORY) == "and Q2?"
    )


def test_standalone_query_model() -> None:
    assert StandaloneQuery(query="x").query == "x"


def test_make_hybrid_retrieve_contextualizes_only_with_history(monkeypatch) -> None:  # noqa: ANN001
    # make_hybrid_retrieve pulls llm.hybrid (langchain) → skip in the base `validate` CI env.
    pytest.importorskip("langchain_core")
    # No network/DB: stub hybrid_retrieve to capture the query it actually searches with, and
    # stub the contextualizer to prove the thread is used BEFORE retrieval.
    import ikip_common.conversation_memory as cm
    import ikip_common.llm.hybrid as hybrid_mod
    from ikip_common.llm.answer import make_hybrid_retrieve
    from ikip_common.llm.hybrid import RetrievalOutcome

    searched: list[str] = []

    def fake_hybrid(session, tenant, query, emb, **kw):  # noqa: ANN001, ANN202, ARG001
        searched.append(query)
        return RetrievalOutcome(documents=[], abstained=True)

    monkeypatch.setattr(hybrid_mod, "hybrid_retrieve", fake_hybrid)
    monkeypatch.setattr(cm, "contextualize_query", lambda _c, _q, _h: "STANDALONE Apple Q2 revenue")

    chat = _FakeChat("unused")
    # with history + a client → retrieval searches the contextualized query
    make_hybrid_retrieve(None, uuid.uuid4(), None, history=_HISTORY, contextualize_client=chat)(
        "and Q2?"
    )
    assert searched == ["STANDALONE Apple Q2 revenue"]

    # without history → the raw follow-up is searched (no contextualization)
    searched.clear()
    make_hybrid_retrieve(None, uuid.uuid4(), None)("and Q2?")
    assert searched == ["and Q2?"]
