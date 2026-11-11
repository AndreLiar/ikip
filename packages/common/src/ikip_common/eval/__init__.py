"""RAG evaluation — deterministic baseline (Story 3.6, ADR 0016).

Deterministic, LLM-free metrics (Recall@K, citation resolution, citation-grounding
coverage) + a no-network harness and JSON regression reports. The LLM-judged metrics
(Ragas faithfulness, custom-vs-Ragas comparison) are Epic 5 — NOT here.

`metrics` is pure (no langchain) so it always runs in the fast CI gate. `harness` drives
the grounded-answer graph (needs the `embeddings` group) and is exercised with fakes.
"""

from ikip_common.eval.compare import ComparisonReport, MetricPair, compare
from ikip_common.eval.metrics import (
    CitationResolution,
    GroundingCoverage,
    citation_grounding_coverage,
    citation_resolution,
    estimate_cost_usd,
    percentile,
    recall_at_k,
)
from ikip_common.eval.ragas_eval import (
    EvalSample,
    FakeRagasEvaluator,
    RagasEvaluator,
    RagasScores,
)

__all__ = [
    "recall_at_k",
    "citation_resolution",
    "citation_grounding_coverage",
    "CitationResolution",
    "GroundingCoverage",
    "percentile",
    "estimate_cost_usd",
    # Story 5.2 — Ragas + comparison
    "RagasEvaluator",
    "FakeRagasEvaluator",
    "RagasScores",
    "EvalSample",
    "compare",
    "ComparisonReport",
    "MetricPair",
]
