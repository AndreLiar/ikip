"""End-to-end custom-vs-Ragas comparison, offline (Story 5.2 AC4) — fakes, no network.

Runs the real deterministic harness (FakeChatClient) to produce answers + contexts, feeds
them to a FakeRagasEvaluator, aligns the two groundedness signals and builds the comparison
report — proving the whole pipeline (incl. the CaseResult.answer/contexts wiring) without
Azure. The live Azure-judged path is [untested live].
"""

import pytest

pytest.importorskip("langgraph")

from ikip_common.eval.compare import MetricPair, compare  # noqa: E402
from ikip_common.eval.harness import GoldCase, evaluate_dataset  # noqa: E402
from ikip_common.eval.ragas_eval import EvalSample, FakeRagasEvaluator  # noqa: E402
from ikip_common.llm import Claim, FakeChatClient, FakeGroundingValidator, GroundedAnswer  # noqa: E402
from ikip_common.llm.hybrid import RetrievalOutcome  # noqa: E402
from langchain_core.documents import Document  # noqa: E402


def _doc(cid: str, text: str) -> Document:
    return Document(page_content=text, metadata={"chunk_id": cid})


def _retrieve(q: str) -> RetrievalOutcome:
    if "E42" in q:
        docs = [_doc("c1", "Fault E42: pump overheat.")]
        return RetrievalOutcome(documents=docs, abstained=False)
    return RetrievalOutcome(documents=[], abstained=True, reason="insufficient evidence")


def test_full_custom_vs_ragas_comparison_offline() -> None:
    cases = [
        GoldCase("fault-e42", "What is E42?", "answered", ["c1"], category="equipment_identifier"),
        GoldCase("unanswerable", "Guest wifi password?", "abstained", [], category="unanswerable"),
    ]
    chat = FakeChatClient(
        GroundedAnswer(
            status="answered",
            claims=[Claim(text="E42 is pump overheat.", evidence_markers=["E1"])],
        )
    )
    report = evaluate_dataset(
        cases,
        retrieve=_retrieve,
        chat_client=chat,
        validator=FakeGroundingValidator(),
        gold_set_version="fm-v1",
    )
    # the harness now carries answer + contexts for the LLM judge (Story 5.2 wiring)
    answered = next(c for c in report.cases if c["case_key"] == "fault-e42")
    assert answered["answer"] and answered["contexts"] == ["Fault E42: pump overheat."]

    samples = [
        EvalSample(
            case_key=c["case_key"],
            question=next(x.question for x in cases if x.case_key == c["case_key"]),
            answer=c["answer"],
            contexts=c["contexts"],
        )
        for c in report.cases
    ]
    # Ragas judges fault-e42 as a faithfulness miss (entailment gap the deterministic
    # coverage can't see) -> the comparison must flag it divergent.
    ragas = FakeRagasEvaluator(default=1.0, overrides={"fault-e42": {"faithfulness": 0.2}})
    scores = ragas.evaluate(samples)
    by_case = {c["case_key"]: c for c in report.cases}
    pairs = [
        MetricPair(
            case_key=s.case_key,
            custom_groundedness=by_case[s.case_key]["citation_grounding_coverage"],
            ragas_faithfulness=scores.per_case[s.case_key]["faithfulness"],
        )
        for s in samples
    ]
    rep = compare(pairs, gold_set_version="fm-v1", ragas_runs=[scores.means])
    assert rep.n_cases == 2
    assert [d["case_key"] for d in rep.divergent_cases] == ["fault-e42"]
    assert "divergent" in rep.recommendation
