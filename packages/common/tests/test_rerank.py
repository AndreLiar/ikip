"""Cross-encoder reranker tests (ADR 0032 §3). Pure — injected score_fn, no model/torch."""

from dataclasses import dataclass, field

import pytest
from ikip_common.rerank import DEFAULT_CROSS_ENCODER_MODEL, CrossEncoderReranker


@dataclass
class _Doc:
    """Structural stand-in for a LangChain Document (page_content + metadata)."""

    page_content: str
    metadata: dict = field(default_factory=dict)


def _doc(cid: str, text: str) -> _Doc:
    return _Doc(page_content=text, metadata={"chunk_id": cid})


def test_reorders_by_injected_score_descending() -> None:
    # score_fn returns a relevance per (query, passage) pair; reranker sorts desc.
    scores = {"a": 0.1, "b": 0.9, "c": 0.5}
    rr = CrossEncoderReranker(score_fn=lambda pairs: [scores[p[1]] for p in pairs])
    out = rr.rerank("q", [_doc("a", "a"), _doc("b", "b"), _doc("c", "c")])
    assert [d.metadata["chunk_id"] for d in out] == ["b", "c", "a"]


def test_top_k_truncates_after_reorder() -> None:
    scores = {"a": 0.1, "b": 0.9, "c": 0.5}
    rr = CrossEncoderReranker(score_fn=lambda pairs: [scores[p[1]] for p in pairs])
    out = rr.rerank("q", [_doc("a", "a"), _doc("b", "b"), _doc("c", "c")], top_k=2)
    assert [d.metadata["chunk_id"] for d in out] == ["b", "c"]  # top-2 by score, a dropped


def test_stamps_score_without_touching_citation() -> None:
    rr = CrossEncoderReranker(score_fn=lambda pairs: [0.42 for _ in pairs])
    [out] = rr.rerank("q", [_doc("a", "text")])
    assert out.metadata["chunk_id"] == "a"  # citation preserved
    assert out.metadata["cross_encoder_score"] == 0.42  # score stamped for observability


def test_empty_candidates_safe() -> None:
    rr = CrossEncoderReranker(score_fn=lambda pairs: [])
    assert rr.rerank("q", []) == []


def test_passes_query_passage_pairs_to_score_fn() -> None:
    seen = []

    def score_fn(pairs):  # noqa: ANN001, ANN202
        seen.extend(pairs)
        return [1.0 for _ in pairs]

    CrossEncoderReranker(score_fn=score_fn).rerank("what is X?", [_doc("a", "passage A")])
    assert seen == [("what is X?", "passage A")]


def test_is_a_reranker_port() -> None:
    # Structurally satisfies the Reranker protocol (reorder-only seam, ADR 0021).
    # hybrid pulls langchain → skip in the base `validate` CI env.
    pytest.importorskip("langchain_core")
    from ikip_common.llm.hybrid import Reranker

    assert isinstance(CrossEncoderReranker(score_fn=lambda p: [0.0 for _ in p]), Reranker)


def test_live_model_path_errors_clearly_without_the_optional_dep() -> None:
    # No score_fn + sentence-transformers not installed -> a clear, actionable RuntimeError (not a
    # raw ImportError). If the dep IS present this would load a model, so only assert when absent.
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="sentence-transformers"):
            CrossEncoderReranker().rerank("q", [_doc("a", "x")])


def test_default_model_name() -> None:
    assert DEFAULT_CROSS_ENCODER_MODEL == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_make_hybrid_retrieve_forwards_the_reranker(monkeypatch) -> None:  # noqa: ANN001
    # make_hybrid_retrieve pulls llm.hybrid (langchain) → skip in the base `validate` CI env.
    pytest.importorskip("langchain_core")
    import uuid

    import ikip_common.llm.hybrid as hybrid_mod
    from ikip_common.llm.answer import make_hybrid_retrieve
    from ikip_common.llm.hybrid import RetrievalOutcome

    seen = {}

    def fake_hybrid(session, tenant, query, emb, **kw):  # noqa: ANN001, ANN202, ARG001
        seen["reranker"] = kw.get("reranker")
        return RetrievalOutcome(documents=[], abstained=True)

    monkeypatch.setattr(hybrid_mod, "hybrid_retrieve", fake_hybrid)
    rr = CrossEncoderReranker(score_fn=lambda p: [0.0 for _ in p])
    make_hybrid_retrieve(None, uuid.uuid4(), None, reranker=rr)("q")
    assert seen["reranker"] is rr  # the port instance is threaded into hybrid_retrieve
