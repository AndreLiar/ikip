"""Judge calibration (Story 5.2, judge-quality gap) — pure, no network.

A scripted validator plays the judge; we assert accuracy / binary / kappa / confusion are
computed correctly. The live Azure judge path is exercised by the CLI (`eval calibrate`).
"""

from __future__ import annotations

from pathlib import Path

from ikip_common.eval.calibration import (
    CalibrationCase,
    load_calibration,
    run_calibration,
)
from ikip_common.llm.schemas import ClaimVerdict, GroundingResult

_FIXTURE = Path(__file__).parent / "fixtures" / "eval" / "judge_calibration.json"


class _ScriptedJudge:
    """Returns a verdict per claim text (deterministic stand-in for the LLM judge)."""

    def __init__(self, by_text: dict[str, str]) -> None:
        self._by_text = by_text

    def validate(self, claims, evidence) -> GroundingResult:  # noqa: ANN001
        return GroundingResult(
            verdicts=[
                ClaimVerdict(claim_index=i, verdict=self._by_text.get(c.text, "unsupported"))
                for i, c in enumerate(claims)
            ]
        )


def test_fixture_loads_and_is_well_formed() -> None:
    version, cases = load_calibration(_FIXTURE)
    assert version == "judge-cal-v1"
    assert len(cases) >= 5
    assert all(c.human_label in {"supported", "partial", "unsupported"} for c in cases)


def test_perfect_judge_scores_1() -> None:
    _, cases = load_calibration(_FIXTURE)
    judge = _ScriptedJudge({c.claim: c.human_label for c in cases})  # agrees with humans
    report = run_calibration(cases, judge)
    assert report.accuracy == 1.0
    assert report.binary_accuracy == 1.0
    assert report.cohen_kappa == 1.0


def test_metrics_and_confusion_on_a_wrong_judge() -> None:
    cases = [
        CalibrationCase("a", "c-a", {"E1": "x"}, ["E1"], "supported"),
        CalibrationCase("b", "c-b", {"E1": "x"}, ["E1"], "unsupported"),
        CalibrationCase("c", "c-c", {"E1": "x"}, ["E1"], "unsupported"),
    ]
    # judge calls everything 'supported' -> only case a is right
    judge = _ScriptedJudge({"c-a": "supported", "c-b": "supported", "c-c": "supported"})
    report = run_calibration(cases, judge)
    assert round(report.accuracy, 3) == round(1 / 3, 3)
    # binary: a(sup==sup) ok; b,c (not_supported vs supported) wrong -> 1/3
    assert round(report.binary_accuracy, 3) == round(1 / 3, 3)
    assert report.confusion["unsupported->supported"] == 2
    assert report.by_human_label["unsupported"] == {"n": 2, "correct": 0}
    assert report.cohen_kappa <= 0.0  # no agreement beyond chance (judge is constant)
