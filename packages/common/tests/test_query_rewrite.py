"""Query-rewrite tests (ADR 0026). Pure — a fake ChatClient, no network/langchain."""

from collections.abc import Sequence

from ikip_common.llm.base import ChatMessage
from ikip_common.llm.query_rewrite import RewrittenQuery, rewrite_query


class _FakeChat:
    """Minimal ChatClient: returns a preset query, or raises if given an Exception."""

    def __init__(self, out: object) -> None:
        self._out = out

    @property
    def model_version(self) -> str:
        return "fake"

    def complete_structured(self, messages: Sequence[ChatMessage], schema: type) -> object:
        if isinstance(self._out, Exception):
            raise self._out
        return schema(query=self._out)


def test_rewrite_returns_enhanced_query() -> None:
    out = rewrite_query(
        _FakeChat("LEVA protective visor polycarbonate material"), "wat is leva made of"
    )
    assert out == "LEVA protective visor polycarbonate material"


def test_rewrite_falls_back_on_empty_output() -> None:
    assert rewrite_query(_FakeChat("   "), "original question") == "original question"


def test_rewrite_falls_back_on_client_error() -> None:
    # Retrieval must never break on a rewrite failure.
    assert rewrite_query(_FakeChat(RuntimeError("judge down")), "original question") == (
        "original question"
    )


def test_rewritten_query_model() -> None:
    assert RewrittenQuery(query="x").query == "x"
