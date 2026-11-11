"""Multi-turn eval (Story 5.2 multi-turn gap). Pure contextualization + a fakes run."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from ikip_common.eval.multiturn import contextualize, load_multiturn

_FIXTURE = Path(__file__).parent / "fixtures" / "gold" / "multi_turn.json"
_no_langgraph = importlib.util.find_spec("langgraph") is None


def test_contextualize_folds_history_as_natural_context() -> None:
    assert contextualize([], "What is E42?") == "What is E42?"  # first turn: unchanged
    out = contextualize([("What is E42?", "Overheat.")], "What should I do?")
    assert out.startswith("What should I do?")  # the actual question leads
    assert "earlier in this conversation we discussed" in out
    assert "What is E42" in out  # prior topic folded in


def test_fixture_is_well_formed() -> None:
    version, cases = load_multiturn(_FIXTURE)
    assert version == "multi-turn-v1"
    assert all(len(c.turns) >= 2 for c in cases)  # every case is multi-turn
    assert {c.language for c in cases} >= {"en", "fr"}


@pytest.mark.skipif(_no_langgraph, reason="langgraph not installed")
def test_evaluate_multiturn_scores_final_turn() -> None:
    from ikip_common.eval.multiturn import MultiTurnCase, evaluate_multiturn
    from ikip_common.llm import Claim, FakeChatClient, FakeGroundingValidator, GroundedAnswer
    from ikip_common.llm.hybrid import RetrievalOutcome
    from langchain_core.documents import Document

    seen_queries: list[str] = []

    def retrieve(q: str) -> RetrievalOutcome:
        seen_queries.append(q)
        doc = Document(page_content="Fault E42: overheat.", metadata={"chunk_id": "c1"})
        return RetrievalOutcome(documents=[doc], abstained=False)

    chat = FakeChatClient(
        GroundedAnswer(status="answered", claims=[Claim(text="overheat", evidence_markers=["E1"])])
    )
    cases = [
        MultiTurnCase(
            "mt1", ["Is there an E42?", "What does it mean?"], "answered", ["c1"], language="en"
        )
    ]
    report = evaluate_multiturn(
        cases, retrieve=retrieve, chat_client=chat, validator=FakeGroundingValidator()
    )
    assert report.n_cases == 1
    assert report.behavior_conformity == 1.0
    assert report.by_language["en"]["n"] == 1
    # the 2nd turn's retrieval query carried the 1st turn as context
    assert seen_queries[1].startswith("What does it mean?")
    assert "Is there an E42" in seen_queries[1]
