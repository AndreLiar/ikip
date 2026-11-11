"""Custom-vs-Ragas comparison report (Story 5.2 AC4, ADR 0016).

The thesis deliverable: run BOTH metric systems on the same gold set and report whether
they agree, how much they cost, and how stable Ragas is run-to-run — so we can justify
which set gates releases. We align the custom deterministic *groundedness* (citation
grounding coverage, from the harness) with Ragas *faithfulness* (the LLM-judged analogue)
per case, then quantify agreement.

Pure stdlib (no numpy) so it runs in the fast gate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field


@dataclass
class MetricPair:
    case_key: str
    custom_groundedness: float  # citation_grounding_coverage (deterministic)
    ragas_faithfulness: float  # LLM-judged


@dataclass
class ComparisonReport:
    gold_set_version: str
    n_cases: int
    # agreement
    pearson_correlation: float | None  # None when a series has zero variance
    mean_abs_difference: float
    agreement_rate: float  # fraction of cases where both agree above/below `threshold`
    threshold: float
    divergent_cases: list[dict]  # cases whose |custom - ragas| > divergence_tol
    # cost + stability
    ragas_cost_usd: float
    ragas_variance: dict  # per-metric population variance across repeated Ragas runs
    recommendation: str
    pairs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson correlation; None if undefined (n<2 or a zero-variance series)."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = _mean(xs), _mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx**0.5 * syy**0.5)


def population_variance(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def variance_across_runs(runs: Sequence[dict[str, float]]) -> dict[str, float]:
    """Per-metric population variance of the means across repeated Ragas runs (AC4:
    run-to-run variance). `runs` = list of `RagasScores.means` dicts."""
    if not runs:
        return {}
    metrics = set().union(*(r.keys() for r in runs))
    return {m: population_variance([r[m] for r in runs if m in r]) for m in sorted(metrics)}


def compare(
    pairs: Sequence[MetricPair],
    *,
    gold_set_version: str = "unknown",
    threshold: float = 0.7,
    divergence_tol: float = 0.3,
    ragas_cost_usd: float = 0.0,
    ragas_runs: Sequence[dict[str, float]] = (),
) -> ComparisonReport:
    """Build the comparison. `threshold` = the pass line both metrics are bucketed against
    for the agreement rate; `divergence_tol` = how far apart a single case may be before it
    is flagged divergent."""
    custom = [p.custom_groundedness for p in pairs]
    ragas = [p.ragas_faithfulness for p in pairs]
    diffs = [abs(c - r) for c, r in zip(custom, ragas, strict=True)]
    agree = [(c >= threshold) == (r >= threshold) for c, r in zip(custom, ragas, strict=True)]
    divergent = [
        {
            "case_key": p.case_key,
            "custom_groundedness": p.custom_groundedness,
            "ragas_faithfulness": p.ragas_faithfulness,
            "difference": round(abs(p.custom_groundedness - p.ragas_faithfulness), 4),
        }
        for p in pairs
        if abs(p.custom_groundedness - p.ragas_faithfulness) > divergence_tol
    ]
    corr = pearson(custom, ragas)
    mad = _mean(diffs)
    return ComparisonReport(
        gold_set_version=gold_set_version,
        n_cases=len(pairs),
        pearson_correlation=corr,
        mean_abs_difference=mad,
        agreement_rate=_mean([1.0 if a else 0.0 for a in agree]),
        threshold=threshold,
        divergent_cases=divergent,
        ragas_cost_usd=ragas_cost_usd,
        ragas_variance=variance_across_runs(ragas_runs),
        recommendation=_recommend(mad, divergent, ragas_cost_usd),
        pairs=[asdict(p) for p in pairs],
    )


def _recommend(mad: float, divergent: list[dict], cost: float) -> str:
    """A short, honest recommendation on which set should gate releases."""
    if not divergent and mad <= 0.1:
        return (
            "High agreement: the deterministic metric tracks Ragas faithfulness closely. "
            "Gate releases on the deterministic metric (free, reproducible); keep Ragas as "
            "a sampled cross-check."
        )
    if divergent:
        return (
            f"{len(divergent)} divergent case(s): the deterministic coverage and Ragas "
            "faithfulness disagree (coverage checks citation presence, not entailment). "
            "Investigate those cases; gate on deterministic + run Ragas nightly to catch "
            "entailment gaps the deterministic metric can't see."
        )
    return (
        "Moderate agreement. Gate on deterministic metrics per push; run Ragas on a bounded "
        f"sample in CI (cost≈${cost:.4f}) and in full nightly."
    )
