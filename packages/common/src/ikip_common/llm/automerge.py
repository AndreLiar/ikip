"""Stage-1 hierarchical retrieval — parent/child auto-merging (ADR 0029).

After hybrid retrieval finds the sharp **child** chunks, expand each hit to its **parent
section**: merge the sibling chunks that share the hit's `section_id`, bounded to a token
budget (a window centred on the hit when the section is larger than the cap), and dedup so
several hits in one section collapse to a single parent. The LLM then reasons over the wider
section context while the citation still resolves to the precise child chunk (FR16).

Storage-neutral: reuses the existing `chunk`/`section` rows — no re-chunking, no re-embedding.
Lives at the retrieval boundary behind the retriever port (ADR 0003/0021); opt-in via
`make_hybrid_retrieve(auto_merge=True)`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from langchain_core.documents import Document
from sqlalchemy import text as _sql

from ikip_common.llm.hybrid import RetrievalOutcome

_CHARS_PER_TOKEN = 4  # matches chunking.estimate_tokens (~4 chars/token)
DEFAULT_PARENT_MAX_TOKENS = 1200
# Delimiters wrapping the precise matched child inside the parent, so a "generation contract"
# prompt can tell the model to ground its claims in the MATCHED passage and use the surrounding
# text only as context (MISSION-044 follow-up on the context↔grounding trade-off).
MATCH_OPEN = "<<<MATCHED PASSAGE (ground every claim strictly in here)>>>"
MATCH_CLOSE = "<<<END MATCHED PASSAGE>>>"


def _render(ordinal: int, content: str, hit_ordinal: int, mark_hit: bool) -> str:
    if mark_hit and ordinal == hit_ordinal:
        return f"{MATCH_OPEN}\n{content}\n{MATCH_CLOSE}"
    return content


def merge_section_window(
    hit_ordinal: int,
    siblings: Sequence[tuple[int, str]],
    *,
    max_tokens: int = DEFAULT_PARENT_MAX_TOKENS,
    mark_hit: bool = False,
) -> str:
    """Pure: merge a section's chunks into the parent context, bounded to ~max_tokens.

    `siblings` is (ordinal, content) for every chunk in the section. If the whole section fits
    the budget it is returned in document order; otherwise a contiguous window is grown outward
    from the hit chunk (forward first, then back) until the budget is reached — so the parent
    always *contains* the hit and stays coherent (no gaps). With `mark_hit`, the hit chunk is
    wrapped in MATCH delimiters for a generation-contract prompt."""
    budget = max(max_tokens, 1) * _CHARS_PER_TOKEN
    ordered = sorted(siblings, key=lambda s: s[0])
    if not ordered:
        return ""
    sep = 2  # "\n\n" between chunks

    def join(items: Sequence[tuple[int, str]]) -> str:
        return "\n\n".join(_render(o, c, hit_ordinal, mark_hit) for o, c in items)

    if sum(len(c) for _, c in ordered) + sep * (len(ordered) - 1) <= budget:
        return join(ordered)

    ordinals = [o for o, _ in ordered]
    center = ordinals.index(hit_ordinal) if hit_ordinal in ordinals else 0
    lo = hi = center
    used = len(ordered[center][1])
    while True:
        extended = False
        if hi + 1 < len(ordered) and used + len(ordered[hi + 1][1]) + sep <= budget:
            hi += 1
            used += len(ordered[hi][1]) + sep
            extended = True
        if lo - 1 >= 0 and used + len(ordered[lo - 1][1]) + sep <= budget:
            lo -= 1
            used += len(ordered[lo][1]) + sep
            extended = True
        if not extended:
            break
    return join(ordered[lo : hi + 1])


def expand_to_parents(
    session,  # noqa: ANN001 (SQLAlchemy Session)
    tenant_id: uuid.UUID,
    outcome: RetrievalOutcome,
    *,
    parent_max_tokens: int = DEFAULT_PARENT_MAX_TOKENS,
    mark_child: bool = False,
) -> RetrievalOutcome:
    """Expand each retrieved child chunk to its parent section (ADR 0029 Stage 1).

    Preserves rank order; collapses multiple hits in the same section to one parent (keeping the
    best-ranked child's citation metadata); leaves section-less chunks (e.g. page-only) untouched.
    """
    if outcome.abstained or not outcome.documents:
        return outcome

    representatives: dict[str, Document] = {}
    order: list[str] = []
    for doc in outcome.documents:
        sid = doc.metadata.get("section_id")
        key = f"section:{sid}" if sid else f"chunk:{doc.metadata.get('chunk_id')}"
        if key not in representatives:
            representatives[key] = doc
            order.append(key)

    merged: list[Document] = []
    for key in order:
        rep = representatives[key]
        sid = rep.metadata.get("section_id")
        if not sid:
            merged.append(rep)  # no parent section → keep the child as-is
            continue
        rows = session.execute(
            _sql(
                "select id::text, (chunk_metadata->>'ordinal')::int as ord, content "
                "from chunk where section_id = cast(:sid as uuid) "
                "and tenant_id = cast(:tid as uuid)"
            ),
            {"sid": str(sid), "tid": str(tenant_id)},
        ).all()
        if not rows:
            merged.append(rep)
            continue
        siblings = [(r[1] if r[1] is not None else 0, r[2]) for r in rows]
        hit_cid = str(rep.metadata.get("chunk_id"))
        hit_ord = next(
            (o for cid, o, _ in rows if cid == hit_cid and o is not None),
            siblings[0][0],
        )
        parent_text = merge_section_window(
            hit_ord, siblings, max_tokens=parent_max_tokens, mark_hit=mark_child
        )
        # Keep the child's metadata → citation still resolves to the precise chunk/page (FR16).
        merged.append(Document(page_content=parent_text, metadata=dict(rep.metadata)))

    return RetrievalOutcome(documents=merged, abstained=False, reason=outcome.reason)
