"""Cross-encoder reranker behind the `Reranker` port (ADR 0032 §3 / ADR 0021).

Our retrieval scores query and passage *independently* (a bi-encoder: embeddings → cosine) and
fuses with RRF. A **cross-encoder** scores the `(query, passage)` **pair jointly** in one forward
pass — much sharper relevance — but at O(candidates) model calls, so it runs only as a *reranker*
over the already-fused top-N, never over the corpus. It **reorders only**: never drops content or
rewrites citations (each Document keeps its metadata), so the grounding/citation guarantee
(ADR 0022) is untouched. Default stays `IdentityReranker`; this is opt-in + A/B-gated
(MISSION-044/047 discipline — most retrieval add-ons don't beat baseline, so measure first).

**Design-only (MISSION-048).** The scoring function is **injectable** (`score_fn`), so the reorder
logic + the A/B wiring are pure and fully tested with **no heavy dependency**. The live-model path
lazy-imports `sentence-transformers` (deliberately *not* a declared dependency-group yet — it pulls
torch); it raises a clear error if absent. We only pay that cost if/when a live A/B is judged worth
running — given the measured retrieval headroom, it may not be.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from ikip_common.context_engineering import SupportsContent

# Canonical lightweight cross-encoder (sentence-transformers / UKPLab), MS MARCO-trained, English,
# Apache-2.0. A multilingual run (FR corpora) would swap in e.g. BAAI/bge-reranker-v2-m3.
DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# (query, passage) pairs -> a relevance score per pair (higher = more relevant).
ScoreFn = Callable[[Sequence[tuple[str, str]]], Sequence[float]]


class CrossEncoderReranker:
    """Reorders candidates by a cross-encoder relevance score. Satisfies the `Reranker` port.

    `score_fn` injected → pure/testable with no model. `score_fn` omitted → the live path
    lazy-loads `sentence-transformers` (uncommitted dep; raises if missing)."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_CROSS_ENCODER_MODEL,
        score_fn: ScoreFn | None = None,
    ) -> None:
        self._model_name = model_name
        self._score_fn = score_fn
        self._model = None

    def _score(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        if self._score_fn is not None:
            return [float(s) for s in self._score_fn(pairs)]
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - exercised only on the live path
                raise RuntimeError(
                    "CrossEncoderReranker's live model needs `sentence-transformers` (pulls "
                    "torch), intentionally not a declared dependency. Install it to run the live "
                    "A/B, or inject a `score_fn`. The default retriever uses IdentityReranker."
                ) from exc
            self._model = CrossEncoder(self._model_name)
        return [float(s) for s in self._model.predict(list(pairs))]

    def rerank[D: SupportsContent](
        self, query: str, documents: Sequence[D], *, top_k: int | None = None
    ) -> list[D]:
        """Reorder `documents` (fused candidates) by cross-encoder relevance to `query`, optionally
        keeping the top_k. Stamps each doc's `metadata['cross_encoder_score']` (observability; the
        citation chain is untouched). Pure reorder — same documents, no content change."""
        docs = list(documents)
        if not docs:
            return []
        scores = self._score([(query, d.page_content) for d in docs])
        for doc, score in zip(docs, scores, strict=True):
            doc.metadata["cross_encoder_score"] = float(score)
        order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
        ranked = [docs[i] for i in order]
        return ranked[:top_k] if top_k is not None else ranked
