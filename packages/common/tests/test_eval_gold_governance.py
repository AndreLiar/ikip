"""Gold governance: language tag + SME-review provenance + FR corpus (Story 5.1 gaps).

Pure: the FR gold is well-formed, language/reviewed load, and the seed corpus backs the FR
handles. langgraph-gated: the harness reports behaviour conformity per language.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from ikip_common.eval.__main__ import _load_gold
from ikip_common.eval.seed import EVAL_CORPUS

_FR = Path(__file__).parent / "fixtures" / "gold" / "failure_modes_fr.json"
_no_langgraph = importlib.util.find_spec("langgraph") is None


def test_fr_gold_is_french_and_unreviewed() -> None:
    doc = json.loads(_FR.read_text())
    assert doc["language"] == "fr"
    for c in doc["cases"]:
        assert c["language"] == "fr"
        assert c["reviewed"] is False  # honest: hand-written, not SME-validated yet


def test_loader_threads_language_and_review_provenance() -> None:
    version, cases = _load_gold(str(_FR))
    assert version == "failure-modes-fr-v1"
    assert all(c.language == "fr" for c in cases)
    assert all(not c.reviewed and c.reviewer is None for c in cases)


def test_fr_corpus_backs_every_fr_gold_handle() -> None:
    _, cases = _load_gold(str(_FR))
    referenced = {cid for c in cases for cid in c.relevant_chunk_ids}
    seeded = {d.symbolic_id for d in EVAL_CORPUS}
    assert referenced <= seeded, f"FR handles with no seed doc: {referenced - seeded}"
    # the FR seed docs are tagged fr
    fr_docs = {d.symbolic_id for d in EVAL_CORPUS if d.language == "fr"}
    assert referenced <= fr_docs


@pytest.mark.skipif(_no_langgraph, reason="langgraph not installed")
def test_aggregate_reports_behavior_conformity_per_language() -> None:
    from ikip_common.eval.harness import GoldCase, evaluate_dataset
    from ikip_common.llm import Claim, FakeChatClient, FakeGroundingValidator, GroundedAnswer
    from ikip_common.llm.hybrid import RetrievalOutcome
    from langchain_core.documents import Document

    def retrieve(_q: str) -> RetrievalOutcome:
        doc = Document(page_content="evidence", metadata={"chunk_id": "c1"})
        return RetrievalOutcome(documents=[doc], abstained=False)

    cases = [
        GoldCase("en1", "q?", "answered", ["c1"], language="en"),
        GoldCase("fr1", "q?", "answered", ["c1"], language="fr"),
    ]
    chat = FakeChatClient(
        GroundedAnswer(status="answered", claims=[Claim(text="x", evidence_markers=["E1"])])
    )
    report = evaluate_dataset(
        cases, retrieve=retrieve, chat_client=chat, validator=FakeGroundingValidator()
    )
    by_lang = report.aggregate["by_language"]
    assert set(by_lang) == {"en", "fr"}
    assert by_lang["en"]["n"] == 1 and by_lang["fr"]["n"] == 1
    assert by_lang["fr"]["behavior_conformity"] == 1.0
