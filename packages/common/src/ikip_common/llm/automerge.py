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


def merge_section_window(
    hit_ordinal: int,
    siblings: Sequence[tuple[int, str]],
    *,
    max_tokens: int = DEFAULT_PARENT_MAX_TOKENS,
) -> str:
    """Pure: merge a section's chunks into the parent context, bounded to ~max_tokens.

    `siblings` is (ordinal, content) for every chunk in the section. If the whole section fits
    the budget it is returned in document order; otherwise a contiguous window is grown outward
    from the hit chunk (forward first, then back) until the budget is reached — so the parent
    always *contains* the hit and stays coherent (no gaps)."""
    budget = max(max_tokens, 1) * _CHARS_PER_TOKEN
    ordered = sorted(siblings, key=lambda s: s[0])
    contents = [c for _, c in ordered]
    if not contents:
        return ""
    sep = 2  # "\n\n" between chunks
    if sum(len(c) for c in contents) + sep * (len(contents) - 1) <= budget:
        return "\n\n".join(contents)

    ordinals = [o for o, _ in ordered]
    center = ordinals.index(hit_ordinal) if hit_ordinal in ordinals else 0
    lo = hi = center
    used = len(contents[center])
    while True:
        extended = False
        if hi + 1 < len(contents) and used + len(contents[hi + 1]) + sep <= budget:
            hi += 1
            used += len(contents[hi]) + sep
            extended = True
        if lo - 1 >= 0 and used + len(contents[lo - 1]) + sep <= budget:
            lo -= 1
            used += len(contents[lo]) + sep
            extended = True
        if not extended:
            break
    return "\n\n".join(contents[lo : hi + 1])


def expand_to_parents(
    session,  # noqa: ANN001 (SQLAlchemy Session)
    tenant_id: uuid.UUID,
    outcome: RetrievalOutcome,
    *,
    parent_max_tokens: int = DEFAULT_PARENT_MAX_TOKENS,
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
        parent_text = merge_section_window(hit_ord, siblings, max_tokens=parent_max_tokens)
        # Keep the child's metadata → citation still resolves to the precise chunk/page (FR16).
        merged.append(Document(page_content=parent_text, metadata=dict(rep.metadata)))

    return RetrievalOutcome(documents=merged, abstained=False, reason=outcome.reason)
