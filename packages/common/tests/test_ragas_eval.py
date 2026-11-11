"""Ragas port (fake) + custom-vs-Ragas comparison math (Story 5.2) — pure, no network.

The live `RagasAdapter` (Azure judge) is [untested live]; here we cover the deterministic
surface: the fake evaluator, and the comparison that quantifies agreement/divergence,
cost and run-to-run variance (AC4).
"""

from __future__ import annotations

from ikip_common.eval.compare import (
    MetricPair,
    compare,
    pearson,
    population_variance,
    variance_across_runs,
)
from ikip_common.eval.ragas_eval import (
    RAGAS_METRICS,
    EvalSample,
    FakeRagasEvaluator,
)


def _samples(n: int) -> list[EvalSample]:
    return [
        EvalSample(case_key=f"c{i}", question="q", answer="a", contexts=["ctx"]) for i in range(n)
    ]


def test_fake_evaluator_scores_every_metric_with_overrides() -> None:
    ev = FakeRagasEvaluator(default=0.8, overrides={"c1": {"faithfulness": 0.2}})
    scores = ev.evaluate(_samples(3))
    assert set(scores.per_case["c0"]) == set(RAGAS_METRICS)
    assert scores.per_case["c0"]["faithfulness"] == 0.8
    assert scores.per_case["c1"]["faithfulness"] == 0.2  # override applied
    # mean faithfulness = (0.8 + 0.2 + 0.8)/3
    assert round(scores.means["faithfulness"], 4) == round((0.8 + 0.2 + 0.8) / 3, 4)


def test_pearson_edge_cases() -> None:
    assert pearson([1.0], [1.0]) is None  # n < 2
    assert pearson([0.5, 0.5, 0.5], [0.1, 0.9, 0.5]) is None  # zero variance in xs
    r = pearson([0.0, 1.0], [0.0, 1.0])
    assert r is not None and round(r, 6) == 1.0


def test_population_variance_and_across_runs() -> None:
    assert population_variance([]) == 0.0
    assert population_variance([2.0, 2.0]) == 0.0
    runs = [{"faithfulness": 0.9}, {"faithfulness": 0.7}, {"faithfulness": 0.8}]
    var = variance_across_runs(runs)
    assert round(var["faithfulness"], 6) == round(population_variance([0.9, 0.7, 0.8]), 6)


def test_compare_high_agreement() -> None:
    pairs = [
        MetricPair("c0", 1.0, 0.95),
        MetricPair("c1", 1.0, 0.9),
        MetricPair("c2", 0.0, 0.05),
    ]
    rep = compare(pairs, gold_set_version="fm-v1", ragas_runs=[{"faithfulness": 0.9}])
    assert rep.n_cases == 3
    assert rep.divergent_cases == []
    assert rep.agreement_rate == 1.0  # all three on the same side of the threshold
    assert rep.mean_abs_difference <= 0.1
    assert "deterministic metric" in rep.recommendation
    assert rep.pearson_correlation is not None and rep.pearson_correlation > 0.9


def test_compare_flags_divergence() -> None:
    # custom says grounded (coverage=1.0) but Ragas faithfulness is low -> entailment gap
    pairs = [MetricPair("c0", 1.0, 0.2), MetricPair("c1", 1.0, 0.95)]
    rep = compare(pairs, divergence_tol=0.3)
    assert [d["case_key"] for d in rep.divergent_cases] == ["c0"]
    assert "divergent" in rep.recommendation
    assert rep.agreement_rate == 0.5  # c0 disagrees across the 0.7 threshold
