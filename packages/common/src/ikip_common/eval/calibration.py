"""Judge calibration against human labels (Story 5.2, judge-quality gap).

Ragas / our grounding judge are LLMs — we must not trust them blindly. This runs our REAL
`GroundingValidator` (the Azure judge, ADR 0022) over a small HUMAN-labeled set of
(claim, evidence) pairs and reports how often it agrees with the humans: accuracy, a
3-class confusion matrix, per-label accuracy, a binary (supported vs not) view, and Cohen's
kappa (agreement beyond chance). Port-injected, so tests use a scripted validator.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

_LABELS = ("supported", "partial", "unsupported")


@dataclass
class CalibrationCase:
    case_key: str
    claim: str
    evidence: dict[str, str]
    evidence_markers: list[str]
    human_label: str


@dataclass
class CalibrationReport:
    calibration_set_version: str
    n: int
    accuracy: float  # exact 3-class agreement
    binary_accuracy: float  # supported vs {partial, unsupported}
    cohen_kappa: float  # 3-class agreement beyond chance
    by_human_label: dict  # human_label -> {n, correct}
    confusion: dict  # "human->judge" -> count
    judge_model: str
    cases: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def load_calibration(path: str | Path) -> tuple[str, list[CalibrationCase]]:
    doc = json.loads(Path(path).read_text())
    cases = [
        CalibrationCase(
            case_key=c["case_key"],
            claim=c["claim"],
            evidence=c["evidence"],
            evidence_markers=c["evidence_markers"],
            human_label=c["human_label"],
        )
        for c in doc["cases"]
    ]
    return doc.get("calibration_set_version", "unknown"), cases


def _binary(label: str) -> str:
    return "supported" if label == "supported" else "not_supported"


def _cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float:
    """3-class Cohen's kappa between human (first) and judge (second)."""
    n = len(pairs)
    if n == 0:
        return 0.0
    po = sum(1 for h, j in pairs if h == j) / n
    pe = 0.0
    for label in _LABELS:
        p_h = sum(1 for h, _ in pairs if h == label) / n
        p_j = sum(1 for _, j in pairs if j == label) / n
        pe += p_h * p_j
    return 1.0 if pe == 1.0 else (po - pe) / (1.0 - pe)


def run_calibration(
    cases: Sequence[CalibrationCase],
    validator,  # noqa: ANN001 — GroundingValidator port
    *,
    calibration_set_version: str = "unknown",
    judge_model: str = "unknown",
) -> CalibrationReport:
    from ikip_common.llm.schemas import Claim

    pairs: list[tuple[str, str]] = []
    confusion: dict[str, int] = {}
    by_label: dict[str, dict] = {lab: {"n": 0, "correct": 0} for lab in _LABELS}
    case_rows: list[dict] = []
    for c in cases:
        claim = Claim(text=c.claim, evidence_markers=c.evidence_markers)
        result = validator.validate([claim], c.evidence)
        judge = result.verdicts[0].verdict if result.verdicts else "unsupported"
        pairs.append((c.human_label, judge))
        key = f"{c.human_label}->{judge}"
        confusion[key] = confusion.get(key, 0) + 1
        bucket = by_label.setdefault(c.human_label, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += 1 if judge == c.human_label else 0
        case_rows.append({"case_key": c.case_key, "human": c.human_label, "judge": judge})

    n = len(cases)
    accuracy = sum(1 for h, j in pairs if h == j) / n if n else 0.0
    binary_accuracy = sum(1 for h, j in pairs if _binary(h) == _binary(j)) / n if n else 0.0
    return CalibrationReport(
        calibration_set_version=calibration_set_version,
        n=n,
        accuracy=accuracy,
        binary_accuracy=binary_accuracy,
        cohen_kappa=_cohen_kappa(pairs),
        by_human_label=by_label,
        confusion=confusion,
        judge_model=judge_model,
        cases=case_rows,
    )
