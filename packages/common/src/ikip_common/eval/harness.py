"""Deterministic evaluation harness (Story 3.6, ADR 0016).

Runs each gold case through the grounded-answer graph (Story 3.5) with an injected
`retrieve` + `chat_client`, keeping **retrieval results and answer results separate**
so a regression can be attributed to one or the other. With a `FakeChatClient` and a
fixed `retrieve` this runs **with no network** — the per-push CI gate.

Does NOT re-implement the Story 3.5 grounding judge: it reuses the AnswerResult (whose
citations are already server-resolved) and measures *deterministic* signals only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from ikip_common.eval.metrics import (
    citation_grounding_coverage,
    citation_resolution,
    estimate_cost_usd,
    percentile,
    recall_at_k,
)
from ikip_common.llm.answer import AnswerResult, grounded_answer
from ikip_common.llm.base import ChatClient
from ikip_common.llm.grounding import GroundingValidator
from ikip_common.llm.hybrid import RetrievalOutcome


@dataclass
class GoldCase:
    case_key: str
    question: str
    expected_behavior: str  # "answered" | "abstained"
    relevant_chunk_ids: list[str] = field(default_factory=list)
    # Story 5.1: failure-mode label (equipment_identifier | outdated_manual |
    # conflicting_sources | unanswerable | table | scanned_pdf | malicious_document) and an
    # optional reference answer used by Ragas (answer_correctness / context_recall).
    category: str = ""
    ground_truth: str | None = None


@dataclass
class CaseResult:
    case_key: str
    # --- retrieval side ---
    retrieved_chunk_ids: list[str]
    recall_at_k: float
    # --- answer side ---
    expected_behavior: str
    actual_behavior: str
    behavior_match: bool
    num_claims: int
    citation_resolution: float
    unresolved_citations: list[str]
    citation_grounding_coverage: float
    ungrounded_claims: list[str]
    # --- cost / latency ---
    latency_ms: float
    estimated_cost_usd: float
    # --- material for LLM-judged (Ragas) metrics (Story 5.2) ---
    answer: str = ""
    contexts: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    gold_set_version: str
    config: dict
    aggregate: dict
    cases: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class _CapturingRetrieve:
    """Wraps the bound retrieve so we can read what it returned for each query without
    running retrieval twice (grounded_answer uses this same callable)."""

    def __init__(self, inner: Callable[[str], RetrievalOutcome]) -> None:
        self._inner = inner
        self.last: RetrievalOutcome | None = None

    def __call__(self, query: str) -> RetrievalOutcome:
        self.last = self._inner(query)
        return self.last


def _evaluate_case(
    case: GoldCase,
    retrieve: Callable[[str], RetrievalOutcome],
    chat_client: ChatClient,
    validator: GroundingValidator | None,
    k: int,
) -> CaseResult:
    capturing = _CapturingRetrieve(retrieve)
    start = time.perf_counter()
    result: AnswerResult = grounded_answer(
        case.question, retrieve=capturing, chat_client=chat_client, validator=validator
    )
    latency_ms = (time.perf_counter() - start) * 1000

    outcome = capturing.last
    retrieved_ids = [str(d.metadata.get("chunk_id")) for d in outcome.documents] if outcome else []
    evidence_text = "\n".join(d.page_content for d in outcome.documents) if outcome else ""

    cited_ids = [
        cit.chunk_id for c in result.claims for cit in c.citations if cit.chunk_id is not None
    ]
    res = citation_resolution(cited_ids, retrieved_ids)
    cov = citation_grounding_coverage([(c.text, len(c.citations)) for c in result.claims])

    return CaseResult(
        case_key=case.case_key,
        retrieved_chunk_ids=retrieved_ids,
        recall_at_k=recall_at_k(retrieved_ids, case.relevant_chunk_ids, k),
        expected_behavior=case.expected_behavior,
        actual_behavior=result.status,
        behavior_match=result.status == case.expected_behavior,
        num_claims=len(result.claims),
        citation_resolution=res.resolved,
        unresolved_citations=res.unresolved,
        citation_grounding_coverage=cov.coverage,
        ungrounded_claims=cov.ungrounded,
        latency_ms=latency_ms,
        estimated_cost_usd=estimate_cost_usd(
            case.question + "\n" + evidence_text, result.answer or ""
        ),
        answer=result.answer or "",
        contexts=[d.page_content for d in outcome.documents] if outcome else [],
    )


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def evaluate_dataset(
    cases: Sequence[GoldCase],
    *,
    retrieve: Callable[[str], RetrievalOutcome],
    chat_client: ChatClient,
    validator: GroundingValidator | None = None,
    k: int = 5,
    gold_set_version: str = "unknown",
    config: dict | None = None,
) -> EvalReport:
    """Run all cases, aggregating retrieval + answer metrics. Deterministic given a fixed
    retrieve + FakeChatClient."""
    results = [_evaluate_case(c, retrieve, chat_client, validator, k) for c in cases]
    latencies = [r.latency_ms for r in results]
    aggregate = {
        "n_cases": len(results),
        "k": k,
        "recall_at_k_mean": _mean([r.recall_at_k for r in results]),
        "citation_resolution_mean": _mean([r.citation_resolution for r in results]),
        "citation_grounding_coverage_mean": _mean([r.citation_grounding_coverage for r in results]),
        "behavior_conformity": _mean([1.0 if r.behavior_match else 0.0 for r in results]),
        "abstention_rate": _mean(
            [1.0 if r.actual_behavior == "abstained" else 0.0 for r in results]
        ),
        "latency_ms_p50": percentile(latencies, 50),
        "latency_ms_p95": percentile(latencies, 95),
        "estimated_cost_usd_total": sum(r.estimated_cost_usd for r in results),
    }
    return EvalReport(
        gold_set_version=gold_set_version,
        config={"k": k, **(config or {})},
        aggregate=aggregate,
        cases=[asdict(r) for r in results],
    )


# --- regression comparison -------------------------------------------------

# Higher-is-better metrics regress when they DROP more than tolerance below baseline.
_HIGHER_BETTER = (
    "recall_at_k_mean",
    "citation_resolution_mean",
    "citation_grounding_coverage_mean",
    "behavior_conformity",
)


@dataclass
class Regression:
    metric: str
    baseline: float
    current: float
    delta: float


def compare_to_baseline(
    report: EvalReport, baseline: dict, *, tolerance: float = 0.0
) -> list[Regression]:
    """Return regressions: higher-is-better metrics that fell more than `tolerance`
    below the approved baseline's aggregate. Empty list = no regression."""
    base_agg = baseline.get("aggregate", {})
    regressions: list[Regression] = []
    for metric in _HIGHER_BETTER:
        if metric not in base_agg or metric not in report.aggregate:
            continue
        base = base_agg[metric]
        cur = report.aggregate[metric]
        if cur < base - tolerance:
            regressions.append(
                Regression(metric=metric, baseline=base, current=cur, delta=cur - base)
            )
    return regressions
