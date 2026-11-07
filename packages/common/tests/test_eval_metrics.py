"""Deterministic eval metrics (Story 3.6) — pure, edge cases, always in CI."""

import pytest
from ikip_common.eval.metrics import (
    citation_grounding_coverage,
    citation_resolution,
    estimate_cost_usd,
    percentile,
    recall_at_k,
)


def test_recall_at_k_basic() -> None:
    assert recall_at_k(["a", "b", "c"], {"b", "d"}, k=3) == 0.5  # b found, d not
    assert recall_at_k(["a", "b"], {"a", "b"}, k=5) == 1.0


def test_recall_at_k_respects_k_cutoff() -> None:
    # relevant id only appears beyond the top-k window
    assert recall_at_k(["x", "y", "a"], {"a"}, k=2) == 0.0
    assert recall_at_k(["x", "y", "a"], {"a"}, k=3) == 1.0


def test_recall_at_k_empty_relevant_is_vacuously_perfect() -> None:
    assert recall_at_k([], set(), k=5) == 1.0


def test_recall_at_k_invalid_k() -> None:
    with pytest.raises(ValueError, match="k must be"):
        recall_at_k(["a"], {"a"}, k=0)


def test_citation_resolution() -> None:
    r = citation_resolution(["c1", "c9"], {"c1", "c2"})
    assert r.resolved == 0.5
    assert r.unresolved == ["c9"]


def test_citation_resolution_no_citations_vacuous() -> None:
    r = citation_resolution([], {"c1"})
    assert r.resolved == 1.0 and r.unresolved == []


def test_grounding_coverage_flags_claims_without_citations() -> None:
    cov = citation_grounding_coverage([("claim A", 2), ("claim B", 0), ("claim C", 1)])
    assert cov.coverage == pytest.approx(2 / 3)
    assert cov.ungrounded == ["claim B"]


def test_grounding_coverage_no_claims_vacuous() -> None:
    assert citation_grounding_coverage([]).coverage == 1.0


def test_percentile() -> None:
    assert percentile([], 95) == 0.0
    assert percentile([5.0], 95) == 5.0
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile([1, 2, 3, 4], 100) == 4.0


def test_estimate_cost_scales_with_text() -> None:
    cheap = estimate_cost_usd("short q", "short a")
    pricey = estimate_cost_usd("x" * 4000, "y" * 4000)
    assert pricey > cheap >= 0.0
