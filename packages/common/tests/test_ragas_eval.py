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


def test_within_budget() -> None:
    from ikip_common.eval.ragas_eval import within_budget

    assert within_budget(0.01, 0.0) is True  # 0 cap = no cap
    assert within_budget(0.01, 0.05) is True
    assert within_budget(0.10, 0.05) is False  # over cap -> refused


def test_adapter_reports_measured_cost_from_token_callback(monkeypatch) -> None:
    # extend the contract test: a get_openai_callback that reports tokens -> cost_source
    # 'measured' and a cost derived from real tokens, not the estimate.
    import contextlib
    import sys
    import types

    from ikip_common.eval.ragas_eval import RAGAS_METRICS, EvalSample, RagasAdapter

    rows = [dict.fromkeys(RAGAS_METRICS, 0.9)]

    class _FakeDF:
        def __init__(self, r):  # noqa: ANN001
            self._r = r
            self.columns = set(r[0])

        @property
        def iloc(self):  # noqa: ANN202
            return self._r

    fake_ragas = types.ModuleType("ragas")
    fake_ragas.evaluate = lambda *_a, **_k: types.SimpleNamespace(to_pandas=lambda: _FakeDF(rows))
    fake_metrics = types.ModuleType("ragas.metrics")
    for n in RAGAS_METRICS:
        setattr(fake_metrics, n, object())
    fake_datasets = types.ModuleType("datasets")
    fake_datasets.Dataset = types.SimpleNamespace(from_dict=lambda rows: rows)
    fake_cb_mod = types.ModuleType("langchain_community.callbacks")

    @contextlib.contextmanager
    def _cb():
        yield types.SimpleNamespace(prompt_tokens=1000, completion_tokens=500)

    fake_cb_mod.get_openai_callback = _cb
    for name, mod in {
        "ragas": fake_ragas,
        "ragas.metrics": fake_metrics,
        "datasets": fake_datasets,
        "langchain_community.callbacks": fake_cb_mod,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)

    adapter = RagasAdapter.__new__(RagasAdapter)
    adapter._settings = types.SimpleNamespace(azure_openai_chat_deployment="judge")
    monkeypatch.setattr(adapter, "_judge", lambda: (None, None))
    scores = adapter.evaluate([EvalSample("c0", "q", "a", ["ctx"])])
    assert scores.cost_source == "measured"
    assert scores.prompt_tokens == 1000 and scores.completion_tokens == 500
    assert scores.cost_usd > 0.0


def test_means_exclude_nan() -> None:
    import math

    # Ragas returns NaN for a metric it can't judge (e.g. faithfulness on an abstained,
    # empty answer); one NaN must not NaN the whole mean.
    ev = FakeRagasEvaluator(default=0.8, overrides={"c1": {"faithfulness": float("nan")}})
    scores = ev.evaluate(_samples(2))
    assert math.isnan(scores.per_case["c1"]["faithfulness"])
    assert scores.means["faithfulness"] == 0.8  # NaN excluded, only c0 counts


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


def test_ragas_adapter_maps_scores_and_estimates_cost(monkeypatch) -> None:
    """Contract test: with a fake `ragas` + `datasets` (the API drifts across versions),
    RagasAdapter maps the result DataFrame columns to per-case scores and records a cost.
    No real ragas/Azure. Catches column/mapping drift before the nightly live run."""
    import sys
    import types

    from ikip_common.eval.ragas_eval import RAGAS_METRICS, EvalSample, RagasAdapter

    class _FakeDF:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows
            self.columns = set(rows[0])

        @property
        def iloc(self):  # noqa: ANN202
            return self._rows

    class _FakeResult:
        def __init__(self, rows: list[dict]) -> None:
            self._rows = rows

        def to_pandas(self) -> _FakeDF:
            return _FakeDF(self._rows)

    rows = [dict.fromkeys(RAGAS_METRICS, 0.5), dict.fromkeys(RAGAS_METRICS, 0.9)]
    fake_ragas = types.ModuleType("ragas")
    fake_ragas.evaluate = lambda dataset, metrics, llm, embeddings: _FakeResult(rows)  # noqa: ARG005
    fake_metrics = types.ModuleType("ragas.metrics")
    for name in (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_correctness",
    ):
        setattr(fake_metrics, name, object())
    fake_datasets = types.ModuleType("datasets")
    fake_datasets.Dataset = types.SimpleNamespace(from_dict=lambda rows: rows)
    monkeypatch.setitem(sys.modules, "ragas", fake_ragas)
    monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics)
    monkeypatch.setitem(sys.modules, "datasets", fake_datasets)

    adapter = RagasAdapter.__new__(RagasAdapter)  # skip __init__ (no Settings/Azure)
    adapter._settings = types.SimpleNamespace(azure_openai_chat_deployment="gpt-5.4-mini")
    monkeypatch.setattr(adapter, "_judge", lambda: (None, None))

    samples = [
        EvalSample("c0", "q0", "a0", ["ctx0"], ground_truth="g0"),
        EvalSample("c1", "q1", "a1", ["ctx1"], ground_truth="g1"),
    ]
    scores = adapter.evaluate(samples)
    assert scores.per_case["c0"]["faithfulness"] == 0.5
    assert scores.per_case["c1"]["answer_correctness"] == 0.9
    assert scores.judge_model == "gpt-5.4-mini"
    assert scores.cost_usd > 0.0  # estimated, not the 0.0 placeholder


def test_score_publisher_attaches_per_case_scores_to_traces() -> None:
    import types

    from ikip_common.eval.ragas_eval import LangfuseScorePublisher, RagasScores

    calls = []

    class _FakeClient:
        def __init__(self, **_) -> None:
            pass

        def create_score(self, **kw) -> None:
            calls.append(kw)

    pub = LangfuseScorePublisher.__new__(LangfuseScorePublisher)
    pub._Langfuse = _FakeClient
    pub._settings = types.SimpleNamespace(
        langfuse_public_key=types.SimpleNamespace(get_secret_value=lambda: "pk"),
        langfuse_secret_key=types.SimpleNamespace(get_secret_value=lambda: "sk"),
        langfuse_host="http://lf",
    )
    scores = RagasScores(
        per_case={"c0": {"faithfulness": 0.8}}, means={"faithfulness": 0.8}, judge_model="j"
    )
    pub.publish(scores, run_name="run1", trace_ids={"c0": "trace-xyz"})

    attached = [c for c in calls if c.get("trace_id")]
    assert attached and attached[0]["trace_id"] == "trace-xyz"
    assert attached[0]["name"] == "ragas.faithfulness"
    # the run mean is also pushed (no trace)
    assert any(c["name"] == "ragas.faithfulness.mean" and "trace_id" not in c for c in calls)


def test_compare_flags_divergence() -> None:
    # custom says grounded (coverage=1.0) but Ragas faithfulness is low -> entailment gap
    pairs = [MetricPair("c0", 1.0, 0.2), MetricPair("c1", 1.0, 0.95)]
    rep = compare(pairs, divergence_tol=0.3)
    assert [d["case_key"] for d in rep.divergent_cases] == ["c0"]
    assert "divergent" in rep.recommendation
    assert rep.agreement_rate == 0.5  # c0 disagrees across the 0.7 threshold
