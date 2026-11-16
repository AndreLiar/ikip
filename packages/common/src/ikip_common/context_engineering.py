"""Context engineering — budget, dedup, reorder the retrieved evidence (ADR 0032 layer 3).

The assembled context should be *deliberate*, not "top-k raw". This module provides the safe,
model-free post-retrieval transforms as a composable pipeline over the retrieved documents:

- **dedup** — drop near-duplicate chunks (token-shingle Jaccard), keeping the higher-ranked one;
- **token budget** — keep the strongest chunks until a token budget is hit (don't dilute/overflow);
- **lost-in-the-middle reorder** — put the strongest evidence at the edges, weakest in the middle.

Two invariants make this grounding-safe (ADR 0022/0032):

1. **It only drops or reorders retrieved chunks** — it never fabricates, merges or summarizes
   content. Every surviving document keeps its *original* `metadata` (its citation chain, FR16), so
   the citation/abstention guarantee is untouched. (LLM summarization/compression is deliberately
   NOT done here: a summary used for generation would have to carry the original chunk citations,
   and that risk isn't worth taking until measured — deferred per ADR 0032.)
2. **Everything is opt-in and no-op by default** — `ContextBudget()` changes nothing. MISSION-044
   measured that "more/different context" is a trade-off, not a free win, so no knob becomes default
   without a measured faithfulness ≥ baseline + a recall/correctness win (A/B-gated, ADR 0016).

Pure + base-env safe: operates on a structural `SupportsContent` protocol (anything with
`page_content: str` + `metadata: dict`, e.g. a LangChain `Document`), so no heavy imports and it's
testable in the base `validate` CI env.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class SupportsContent(Protocol):
    page_content: str
    metadata: dict


# ~4 chars/token is the usual rough rule for English/French prose; good enough for *budgeting*
# (we only need a stable monotonic estimate, not exact tokenization). Callers may inject a real
# tokenizer via `token_counter` for precision.
_CHARS_PER_TOKEN = 4

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class ContextBudget:
    """Opt-in context-engineering knobs. All default to no-op (MISSION-044: measure, not assume)."""

    max_tokens: int | None = None  # None -> no budget cut
    dedup: bool = False  # drop near-duplicate chunks
    dedup_threshold: float = 0.9  # Jaccard ≥ this -> considered a near-duplicate
    lost_in_the_middle: bool = False  # strongest evidence to the edges


def estimate_tokens(text: str) -> int:
    """Cheap, stable token estimate (chars/4). Used for budgeting only."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _shingles(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b)


def dedup_documents[D: SupportsContent](
    documents: Sequence[D], *, threshold: float = 0.9
) -> list[D]:
    """Drop near-duplicate chunks (word-set Jaccard ≥ threshold), keeping the first occurrence —
    which, on a relevance-ordered list, is the higher-ranked one. Citations are preserved (we keep
    an original document, never a merged one)."""
    kept: list[D] = []
    kept_shingles: list[set[str]] = []
    for doc in documents:
        sh = _shingles(doc.page_content)
        if any(_jaccard(sh, prev) >= threshold for prev in kept_shingles):
            continue
        kept.append(doc)
        kept_shingles.append(sh)
    return kept


def apply_token_budget[D: SupportsContent](
    documents: Sequence[D],
    max_tokens: int,
    *,
    token_counter=estimate_tokens,  # noqa: ANN001 — callable(str)->int, defaults to the heuristic
) -> list[D]:
    """Keep documents from the top (relevance order) until the running token total would exceed
    `max_tokens`. Always keeps at least the first document (so retrieval never silently abstains via
    the budget — abstention stays the retriever's decision)."""
    kept: list[D] = []
    used = 0
    for i, doc in enumerate(documents):
        cost = token_counter(doc.page_content)
        if i > 0 and used + cost > max_tokens:
            break
        kept.append(doc)
        used += cost
    return kept


def reorder_lost_in_the_middle[D: SupportsContent](documents: Sequence[D]) -> list[D]:
    """Mitigate "lost-in-the-middle": place the strongest evidence at the start AND end, the weakest
    in the middle. Expects `documents` in descending relevance order. Pure reshuffle — same set."""
    rest = list(documents)
    rest.reverse()  # now ascending relevance
    reordered: list[D] = []
    for i, doc in enumerate(rest):
        if i % 2 == 1:
            reordered.append(doc)  # weaker ones drift inward
        else:
            reordered.insert(0, doc)  # stronger ones to the front edge
    return reordered


def engineer_context[D: SupportsContent](
    documents: Sequence[D],
    budget: ContextBudget | None = None,
    *,
    token_counter=estimate_tokens,  # noqa: ANN001
) -> list[D]:
    """Apply the opt-in transforms in a safe order: **dedup → budget → reorder**.

    Dedup first (so the budget isn't spent on duplicates), budget next (cut on true relevance
    order, before any reshuffle), reorder last (presentation only). With a default `ContextBudget()`
    this is an identity pass. Never adds, merges or rewrites content — only drops/reorders chunks,
    so every survivor keeps its citation (grounding invariant intact)."""
    budget = budget or ContextBudget()
    docs: list[D] = list(documents)
    if budget.dedup:
        docs = dedup_documents(docs, threshold=budget.dedup_threshold)
    if budget.max_tokens is not None:
        docs = apply_token_budget(docs, budget.max_tokens, token_counter=token_counter)
    if budget.lost_in_the_middle:
        docs = reorder_lost_in_the_middle(docs)
    return docs
