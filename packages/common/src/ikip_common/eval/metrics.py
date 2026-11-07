"""Deterministic RAG metrics (Story 3.6, ADR 0016). Pure: no LLM, no network, no DB.

These own NFR6/NFR7-style quality signals that need no judge:
  - `recall_at_k`              — did retrieval surface the relevant evidence in top-K?
  - `citation_resolution`      — do the answer's cited chunks resolve to retrieved ones?
  - `citation_grounding_coverage` — does every claim carry ≥1 resolvable citation?

IMPORTANT (scope): `citation_grounding_coverage` checks that evidence is *present and
resolvable*, NOT that it semantically *entails* the claim. LLM-judged faithfulness
(entailment) is Epic 5 (Ragas) — deliberately not computed here.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

# Indicative Azure gpt-5.4-mini DataZoneStandard rates (USD / 1M tokens). Used only for
# a rough per-answer cost estimate; real FinOps accounting is Epic 5. Override as needed.
DEFAULT_IN_PER_1M = 0.825
DEFAULT_OUT_PER_1M = 4.95
_CHARS_PER_TOKEN = 4


def recall_at_k(retrieved: Sequence[str], relevant: Collection[str], k: int) -> float:
    """Fraction of relevant ids present in the top-K retrieved ids. K is explicit.
    No relevant ids (e.g. an abstain case) → 1.0 (nothing to recall, vacuously perfect)."""
    if k < 1:
        raise ValueError("k must be >= 1")
    rel = set(relevant)
    if not rel:
        return 1.0
    topk = set(retrieved[:k])
    return len(rel & topk) / len(rel)


@dataclass
class CitationResolution:
    resolved: float  # fraction of cited ids that resolve to a retrieved id
    unresolved: list[str]


def citation_resolution(cited: Sequence[str], retrieved: Collection[str]) -> CitationResolution:
    """Do the answer's cited chunk ids resolve to chunks that were actually retrieved?
    No citations (e.g. abstained) → resolved=1.0, empty unresolved (vacuous)."""
    if not cited:
        return CitationResolution(resolved=1.0, unresolved=[])
    known = set(retrieved)
    unresolved = [c for c in cited if c not in known]
    return CitationResolution(
        resolved=(len(cited) - len(unresolved)) / len(cited), unresolved=unresolved
    )


@dataclass
class GroundingCoverage:
    coverage: float  # fraction of claims with >=1 resolvable citation
    ungrounded: list[str]  # texts of claims lacking any resolvable citation


def citation_grounding_coverage(claims: Sequence[tuple[str, int]]) -> GroundingCoverage:
    """`claims` = (claim_text, number_of_resolvable_citations). Coverage = fraction with
    ≥1. Presence/resolution only — NOT semantic entailment (that's Epic 5). No claims
    (e.g. abstained) → coverage=1.0 (vacuous)."""
    if not claims:
        return GroundingCoverage(coverage=1.0, ungrounded=[])
    ungrounded = [text for text, n in claims if n <= 0]
    return GroundingCoverage(
        coverage=(len(claims) - len(ungrounded)) / len(claims), ungrounded=ungrounded
    )


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolated percentile (p in [0,100]). Empty → 0.0."""
    if not values:
        return 0.0
    if not 0 <= p <= 100:
        raise ValueError("p must be in [0, 100]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _estimate_tokens(text: str) -> int:
    return max(0, len(text) // _CHARS_PER_TOKEN)


def estimate_cost_usd(
    input_text: str,
    output_text: str,
    *,
    in_per_1m: float = DEFAULT_IN_PER_1M,
    out_per_1m: float = DEFAULT_OUT_PER_1M,
) -> float:
    """Rough per-answer cost estimate from char/4 token approximation + indicative rates.
    Deterministic (no API usage counters); real accounting is Epic 5."""
    in_tok = _estimate_tokens(input_text)
    out_tok = _estimate_tokens(output_text)
    return (in_tok / 1_000_000) * in_per_1m + (out_tok / 1_000_000) * out_per_1m
