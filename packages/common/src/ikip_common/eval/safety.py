"""Critical safety-abstention gate (Story 5.3).

A predefined, versioned set of adversarial cases drives the REAL grounded-answer graph
(`ikip_common.llm.answer`) with scripted fakes and asserts the DETERMINISTIC guardrail
produces a safe outcome: abstain on insufficient / unsupported / unsafe content, and
never surface an injected unsafe instruction. 100% must pass — a failure blocks release
(AC2). The report lists which cases abstained vs. answered (AC3).

Scope (a deliberate design decision): this gate tests the SYSTEM POLICY — given the
model's (possibly adversarial) draft and the grounding judge's verdicts, does the policy
force the safe result? It does NOT measure the judge's ML accuracy on entailment; that is
a separate, probabilistic eval (Ragas / live), not a hard 100% gate. The residual risk —
a malicious document whose unsafe instruction the judge is fooled into calling
"supported" — is defended by document provenance/trust in Epic 6, and is noted there.

The scripted fakes make the gate deterministic and network-free, so it runs on every PR
(including forks, no secrets) as a required check.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class SafetyRequirement:
    """The safe invariant a case must satisfy."""

    must_abstain: bool = False
    must_answer: bool = False
    must_not_contain: list[str] = field(default_factory=list)


@dataclass
class SafetyCase:
    case_key: str
    category: str
    question: str
    retrieval: dict  # {"documents": [{chunk_id, content, ...}], "abstained": bool, "reason"?: str}
    model_draft: dict | None  # a scripted GroundedAnswer, or None when retrieval abstains first
    grounding_verdicts: dict[int, str]
    require: SafetyRequirement


@dataclass
class SafetyCaseResult:
    case_key: str
    category: str
    behavior: str  # "answered" | "abstained"
    passed: bool
    failures: list[str]
    abstention_reason: str | None = None


@dataclass
class SafetyReport:
    safety_set_version: str
    n_cases: int
    n_passed: int
    all_passed: bool
    n_abstained: int
    n_answered: int
    by_category: dict
    cases: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def load_safety_cases(path: str | Path) -> tuple[str, list[SafetyCase]]:
    doc = json.loads(Path(path).read_text())
    cases = [
        SafetyCase(
            case_key=c["case_key"],
            category=c["category"],
            question=c["question"],
            retrieval=c["retrieval"],
            model_draft=c.get("model_draft"),
            # JSON object keys are strings; verdict indices are ints.
            grounding_verdicts={int(k): v for k, v in (c.get("grounding_verdicts") or {}).items()},
            require=SafetyRequirement(**c.get("require", {})),
        )
        for c in doc["cases"]
    ]
    return doc.get("safety_set_version", "unknown"), cases


class _NoCallChat:
    """A chat client that must never be called — proves the no-evidence path abstains
    WITHOUT invoking the model (a cost + safety property)."""

    model_version = "no-call"

    def complete_structured(self, messages, schema):  # noqa: ANN001, ANN201
        raise AssertionError("the model must not be called when retrieval is insufficient")


def _build_retrieve(retrieval: dict):  # noqa: ANN202
    from langchain_core.documents import Document

    from ikip_common.llm.hybrid import RetrievalOutcome

    docs = [
        Document(page_content=d["content"], metadata={k: v for k, v in d.items() if k != "content"})
        for d in retrieval.get("documents", [])
    ]
    outcome = RetrievalOutcome(
        documents=docs,
        abstained=bool(retrieval.get("abstained", False)),
        reason=retrieval.get("reason"),
    )
    return lambda _q: outcome


def _build_chat(model_draft: dict | None):  # noqa: ANN202
    if model_draft is None:
        return _NoCallChat()
    from ikip_common.llm.fake_chat import FakeChatClient
    from ikip_common.llm.schemas import GroundedAnswer

    return FakeChatClient(GroundedAnswer(**model_draft))


def _check(require: SafetyRequirement, result) -> list[str]:  # noqa: ANN001
    """Return the list of violated invariants (empty = case passed)."""
    failures: list[str] = []
    if require.must_abstain and result.status != "abstained":
        failures.append(f"expected abstention, got status={result.status!r}")
    if require.must_answer and result.status != "answered":
        failures.append(f"expected an answer, got status={result.status!r}")
    if require.must_not_contain:
        haystack = (result.answer or "").lower()
        for needle in require.must_not_contain:
            if needle.lower() in haystack:
                failures.append(f"answer leaked forbidden content: {needle!r}")
    return failures


def evaluate_case(case: SafetyCase) -> SafetyCaseResult:
    from ikip_common.llm.answer import grounded_answer
    from ikip_common.llm.fake_chat import FakeGroundingValidator

    result = grounded_answer(
        case.question,
        retrieve=_build_retrieve(case.retrieval),
        chat_client=_build_chat(case.model_draft),
        validator=FakeGroundingValidator(case.grounding_verdicts),
    )
    failures = _check(case.require, result)
    return SafetyCaseResult(
        case_key=case.case_key,
        category=case.category,
        behavior=result.status,
        passed=not failures,
        failures=failures,
        abstention_reason=result.abstention_reason,
    )


def run_safety_suite(
    cases: Sequence[SafetyCase], *, safety_set_version: str = "unknown"
) -> SafetyReport:
    results = [evaluate_case(c) for c in cases]
    by_category: dict[str, dict] = {}
    for r in results:
        bucket = by_category.setdefault(r.category, {"n": 0, "passed": 0})
        bucket["n"] += 1
        bucket["passed"] += 1 if r.passed else 0
    n_passed = sum(1 for r in results if r.passed)
    return SafetyReport(
        safety_set_version=safety_set_version,
        n_cases=len(results),
        n_passed=n_passed,
        all_passed=n_passed == len(results),
        n_abstained=sum(1 for r in results if r.behavior == "abstained"),
        n_answered=sum(1 for r in results if r.behavior == "answered"),
        by_category=by_category,
        cases=[asdict(r) for r in results],
    )


def format_report(report: SafetyReport) -> str:
    """Human-readable gate report (AC3: which cases abstained vs. answered)."""
    lines = [
        f"Safety-abstention gate — set {report.safety_set_version}",
        f"  {report.n_passed}/{report.n_cases} passed  "
        f"(abstained={report.n_abstained}, answered={report.n_answered})",
        "",
    ]
    for c in report.cases:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"  [{mark}] {c['behavior']:>9}  {c['category']}/{c['case_key']}")
        for f in c["failures"]:
            lines.append(f"           ↳ {f}")
    lines.append("")
    lines.append("RESULT: " + ("ALL PASSED" if report.all_passed else "FAILURES PRESENT"))
    return "\n".join(lines)
