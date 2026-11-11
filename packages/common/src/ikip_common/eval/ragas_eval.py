"""Ragas LLM-judged metrics behind a port (Story 5.2, ADR 0016).

Custom deterministic metrics (metrics.py) own Recall@K + citation resolution — fast, free,
reproducible, they gate every push. Ragas adds the *LLM-judged* metrics — `faithfulness`
(groundedness), `answer_relevancy`, `context_precision`, `context_recall` — judged by Azure
OpenAI. Those cost tokens and are non-deterministic, so they run on a bounded sample in CI
and in full nightly/on-demand.

Ragas is wrapped behind the `RagasEvaluator` port (ADR 0021): `RagasAdapter` lazy-imports
the library + builds the Azure judge; `FakeRagasEvaluator` gives deterministic scores so the
comparison logic (compare.py) is CI-testable with no network. Scores are pushed to Langfuse
behind the `ScorePublisher` port (no-op without creds).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

RAGAS_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "answer_correctness",  # uses ground_truth from the gold set (Story 5.1)
)


def estimate_ragas_cost_usd(samples: Sequence[EvalSample], n_metrics: int) -> float:
    """Coarse judge-cost estimate (not exact usage accounting): each metric issues ~one
    judge call per sample over (question+answer+contexts); output is short. Uses the same
    indicative Azure rates as metrics.estimate_cost_usd. A real usage-based figure (judge
    token counters) is a follow-up — this beats the previous 0.0 placeholder."""
    from ikip_common.eval.metrics import estimate_cost_usd

    total = 0.0
    for s in samples:
        judge_input = s.question + "\n" + s.answer + "\n" + "\n".join(s.contexts)
        # ~short verdict output per metric; scale the per-sample cost by the metric count.
        total += n_metrics * estimate_cost_usd(judge_input, s.answer[:200])
    return total


@dataclass
class EvalSample:
    """One (question → answer) with its retrieved contexts and an optional reference."""

    case_key: str
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str | None = None


@dataclass
class RagasScores:
    """Per-sample scores keyed by metric, plus means. `per_case[case_key][metric] -> float`."""

    per_case: dict[str, dict[str, float]]
    means: dict[str, float]
    judge_model: str
    cost_usd: float = 0.0
    # Real judge token usage (0 when estimated or unavailable). cost_source tells which.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_source: str = "estimated"  # "measured" | "estimated"

    def to_dict(self) -> dict:
        return asdict(self)


class BudgetExceededError(RuntimeError):
    """A Ragas run was refused because its estimated cost exceeds the budget cap."""


def within_budget(estimated_usd: float, budget_usd: float) -> bool:
    """True if the run is allowed. budget_usd <= 0 means 'no cap'."""
    return budget_usd <= 0 or estimated_usd <= budget_usd


def _means(per_case: dict[str, dict[str, float]]) -> dict[str, float]:
    import math

    means: dict[str, float] = {}
    for metric in RAGAS_METRICS:
        # Ragas returns NaN for a metric it can't judge (e.g. faithfulness on an abstained,
        # empty answer); exclude those so one abstention doesn't NaN the whole mean.
        vals = [c[metric] for c in per_case.values() if metric in c and not math.isnan(c[metric])]
        means[metric] = sum(vals) / len(vals) if vals else 0.0
    return means


class RagasEvaluator:
    """Port: judge a batch of samples and return LLM-judged metric scores."""

    def evaluate(self, samples: Sequence[EvalSample]) -> RagasScores:  # pragma: no cover
        raise NotImplementedError


@dataclass
class FakeRagasEvaluator(RagasEvaluator):
    """Deterministic stand-in: returns scripted scores (default or per-case overrides), so
    the comparison harness + CLI are testable with no LLM/network."""

    default: float = 0.9
    overrides: dict[str, dict[str, float]] = field(default_factory=dict)
    judge_model: str = "fake-judge"
    cost_usd: float = 0.0

    def evaluate(self, samples: Sequence[EvalSample]) -> RagasScores:
        per_case: dict[str, dict[str, float]] = {}
        for s in samples:
            over = self.overrides.get(s.case_key, {})
            per_case[s.case_key] = {m: over.get(m, self.default) for m in RAGAS_METRICS}
        return RagasScores(
            per_case=per_case,
            means=_means(per_case),
            judge_model=self.judge_model,
            cost_usd=self.cost_usd,
        )


class RagasAdapter(RagasEvaluator):
    """Real Ragas evaluator judged by Azure OpenAI (lazy import; needs the `ragas` group).

    [untested live] — exercised via FakeRagasEvaluator in CI; a real judged run needs Azure
    credentials and the `ragas` dependency group.
    """

    def __init__(self, settings=None) -> None:  # noqa: ANN001
        from ikip_common.config import get_settings

        self._settings = settings or get_settings()

    def _judge(self):  # noqa: ANN202 — ragas wrappers, lazy
        from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper

        s = self._settings
        llm = AzureChatOpenAI(
            azure_deployment=s.azure_openai_chat_deployment,
            api_version=s.azure_openai_api_version,
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key.get_secret_value() if s.azure_openai_api_key else None,
        )
        emb = AzureOpenAIEmbeddings(
            azure_deployment=s.azure_openai_embedding_deployment,
            api_version=s.azure_openai_api_version,
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key.get_secret_value() if s.azure_openai_api_key else None,
        )
        return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(emb)

    def evaluate(self, samples: Sequence[EvalSample]) -> RagasScores:
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import (
            answer_correctness,
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        from datasets import Dataset

        llm, emb = self._judge()
        rows = {
            "question": [s.question for s in samples],
            "answer": [s.answer for s in samples],
            "contexts": [s.contexts for s in samples],
            "ground_truth": [s.ground_truth or "" for s in samples],
        }
        metrics = [
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
        ]
        # Capture REAL judge token usage (not the chars/4 estimate). get_openai_callback
        # hooks on_llm_end for every langchain call within the context — including ragas'.
        prompt_tok = completion_tok = 0
        try:
            from langchain_community.callbacks import get_openai_callback

            with get_openai_callback() as cb:
                result = ragas_evaluate(
                    Dataset.from_dict(rows), metrics=metrics, llm=llm, embeddings=emb
                )
            prompt_tok, completion_tok = cb.prompt_tokens, cb.completion_tokens
        except ImportError:
            result = ragas_evaluate(
                Dataset.from_dict(rows), metrics=metrics, llm=llm, embeddings=emb
            )

        df = result.to_pandas()
        per_case: dict[str, dict[str, float]] = {}
        for i, s in enumerate(samples):
            per_case[s.case_key] = {
                m: float(df.iloc[i][m]) for m in RAGAS_METRICS if m in df.columns
            }
        model = self._settings.azure_openai_chat_deployment or "azure-judge"
        if prompt_tok or completion_tok:
            from ikip_common.eval.metrics import DEFAULT_IN_PER_1M, DEFAULT_OUT_PER_1M

            cost = (prompt_tok / 1_000_000) * DEFAULT_IN_PER_1M + (
                completion_tok / 1_000_000
            ) * DEFAULT_OUT_PER_1M
            source = "measured"
        else:
            cost = estimate_ragas_cost_usd(samples, len(metrics))
            source = "estimated"
        return RagasScores(
            per_case=per_case,
            means=_means(per_case),
            judge_model=model,
            cost_usd=cost,
            prompt_tokens=prompt_tok,
            completion_tokens=completion_tok,
            cost_source=source,
        )


def build_ragas_evaluator(settings=None) -> RagasEvaluator:  # noqa: ANN001
    """Real Azure-judged Ragas evaluator. Raises at evaluate-time if the `ragas` group or
    Azure creds are missing — callers in CI inject FakeRagasEvaluator instead."""
    return RagasAdapter(settings)


# --- Langfuse score publishing (AC3) ---------------------------------------


class ScorePublisher:
    """Port: push evaluation scores to the observability backend (Langfuse)."""

    def publish(
        self,
        scores: RagasScores,
        *,
        run_name: str,
        trace_ids: dict[str, str] | None = None,
    ) -> None:  # pragma: no cover
        raise NotImplementedError


class NullScorePublisher(ScorePublisher):
    def publish(
        self, scores: RagasScores, *, run_name: str, trace_ids: dict[str, str] | None = None
    ) -> None:
        return None


class LangfuseScorePublisher(ScorePublisher):
    """Push Ragas scores to Langfuse (lazy SDK import). Per-case scores are attached to the
    case's trace (Story 5.4 `trace_id`) when provided, so you can navigate trace→score→prompt;
    the run means are also pushed as run-level scores."""

    def __init__(self, settings=None) -> None:  # noqa: ANN001
        from langfuse import Langfuse

        from ikip_common.config import get_settings

        self._Langfuse = Langfuse
        self._settings = settings or get_settings()

    def publish(
        self, scores: RagasScores, *, run_name: str, trace_ids: dict[str, str] | None = None
    ) -> None:
        s = self._settings
        client = self._Langfuse(
            public_key=s.langfuse_public_key.get_secret_value(),
            secret_key=s.langfuse_secret_key.get_secret_value(),
            host=s.langfuse_host,
        )
        ids = trace_ids or {}
        # per-case scores attached to their trace (closes the trace↔score↔prompt loop)
        for case_key, metrics in scores.per_case.items():
            trace_id = ids.get(case_key)
            if not trace_id:
                continue
            for metric, value in metrics.items():
                client.create_score(
                    name=f"ragas.{metric}", value=value, trace_id=trace_id, comment=run_name
                )
        # run-level means (no trace)
        for metric, value in scores.means.items():
            client.create_score(name=f"ragas.{metric}.mean", value=value, comment=run_name)


def build_score_publisher(settings=None) -> ScorePublisher:  # noqa: ANN001
    """Langfuse publisher when creds + SDK are available, else a no-op."""
    from ikip_common.config import get_settings

    s = settings or get_settings()
    if s.langfuse_public_key is None or s.langfuse_secret_key is None:
        return NullScorePublisher()
    try:
        return LangfuseScorePublisher(s)
    except ImportError:
        return NullScorePublisher()
