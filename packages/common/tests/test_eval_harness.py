"""Eval harness + report tests (Story 3.6) — fakes, no network, reproducible.

Skipped when langgraph is absent (fast CI without `embeddings`). Drives the real
grounded-answer graph with a FakeChatClient + a fixed retrieve, so a per-push run is
deterministic. Also covers the 3-artifact report writer + baseline regression check.
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from ikip_common.eval.harness import (  # noqa: E402
    EvalReport,
    GoldCase,
    compare_to_baseline,
    evaluate_dataset,
)
from ikip_common.eval.report import load_json, promote, write_run  # noqa: E402
from ikip_common.llm import Claim, FakeChatClient, FakeGroundingValidator, GroundedAnswer  # noqa: E402
from ikip_common.llm.hybrid import RetrievalOutcome  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

_FIXTURE = Path(__file__).parent / "fixtures" / "gold" / "v1.json"


def _doc(cid: str, content: str) -> Document:
    return Document(
        page_content=content,
        metadata={
            "chunk_id": cid,
            "document_id": "d1",
            "document_version_id": "v1",
            "revision": "A",
            "is_current": True,
            "section_id": "s1",
            "heading": "3.2",
            "hierarchy_path": "3.2",
            "page_start": 1,
            "page_end": 1,
        },
    )


def _load_cases() -> list[GoldCase]:
    doc = json.loads(_FIXTURE.read_text())
    return [
        GoldCase(
            case_key=c["case_key"],
            question=c["question"],
            expected_behavior=c["expected_behavior"],
            relevant_chunk_ids=c.get("relevant_chunk_ids", []),
        )
        for c in doc["cases"]
    ]


def _answered() -> FakeChatClient:
    return FakeChatClient(
        GroundedAnswer(
            status="answered",
            claims=[Claim(text="E42 is pump overheat.", evidence_markers=["E1"])],
        )
    )


def test_harness_runs_over_fixture_deterministically() -> None:
    cases = _load_cases()

    # case 1 answers (evidence c1 retrieved + cited); case 2 abstains (empty retrieval)
    def retrieve(q: str) -> RetrievalOutcome:
        if "E42" in q:
            return RetrievalOutcome(
                documents=[_doc("c1", "Fault E42: pump overheat.")], abstained=False
            )
        return RetrievalOutcome(documents=[], abstained=True, reason="insufficient evidence")

    report = evaluate_dataset(
        cases,
        retrieve=retrieve,
        chat_client=_answered(),
        validator=FakeGroundingValidator(),
        k=5,
        gold_set_version="v1",
    )
    agg = report.aggregate
    assert agg["n_cases"] == 2
    assert agg["behavior_conformity"] == 1.0  # both behaved as the gold expects
    assert agg["recall_at_k_mean"] == 1.0  # c1 retrieved for case 1; case 2 vacuous
    assert agg["abstention_rate"] == 0.5
    assert agg["citation_grounding_coverage_mean"] == 1.0

    # determinism: a second run yields identical *quality* metrics (latency is wall-clock,
    # inherently non-deterministic, so it's excluded from the reproducibility contract).
    report2 = evaluate_dataset(
        cases,
        retrieve=retrieve,
        chat_client=_answered(),
        validator=FakeGroundingValidator(),
        k=5,
        gold_set_version="v1",
    )
    quality = lambda a: {k: v for k, v in a.items() if not k.startswith("latency_")}  # noqa: E731
    assert quality(report.aggregate) == quality(report2.aggregate)


def test_report_three_artifacts_and_baseline_not_auto_set(tmp_path: Path) -> None:
    report = EvalReport(
        gold_set_version="v1",
        config={"k": 5},
        aggregate={"recall_at_k_mean": 0.9, "behavior_conformity": 1.0},
        cases=[],
    )
    run_path, latest = write_run(report, tmp_path)
    assert run_path.exists() and latest.exists()
    assert (tmp_path / "runs").is_dir()
    assert not (tmp_path / "baseline.json").exists()  # never auto-created

    promote(tmp_path)  # explicit approval
    assert (tmp_path / "baseline.json").exists()
    assert load_json(tmp_path / "baseline.json")["aggregate"]["recall_at_k_mean"] == 0.9


def test_compare_to_baseline_flags_regression() -> None:
    baseline = {"aggregate": {"recall_at_k_mean": 0.9, "behavior_conformity": 1.0}}
    worse = EvalReport("v1", {"k": 5}, {"recall_at_k_mean": 0.7, "behavior_conformity": 1.0}, [])
    regs = compare_to_baseline(worse, baseline, tolerance=0.05)
    assert [r.metric for r in regs] == ["recall_at_k_mean"]
    assert regs[0].delta == pytest.approx(-0.2)

    ok = EvalReport("v1", {"k": 5}, {"recall_at_k_mean": 0.89, "behavior_conformity": 1.0}, [])
    assert compare_to_baseline(ok, baseline, tolerance=0.05) == []  # within tolerance
