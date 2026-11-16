"""Visual-retrieval evaluation (Epic 9, Story 9.2 AC4, ADR 0031).

DocVQA-style: a question → the visual region (element) that supports the answer. Measures whether
caption-and-embed retrieval surfaces the right **visual element** (region-hit recall@k) and whether
the resolved visual citation points at that region. Deterministic + free (compare ids), gate-able.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VisualGoldCase:
    case_key: str
    question: str
    relevant_visual_element_ids: list[str] = field(default_factory=list)


def visual_region_recall_at_k(
    retrieved_visual_element_ids: list[str], relevant: list[str], k: int
) -> float:
    """Fraction of relevant visual elements present in the top-k retrieved (region-hit recall)."""
    if not relevant:
        return 1.0
    top = set(retrieved_visual_element_ids[:k])
    return sum(1 for r in relevant if r in top) / len(relevant)


def visual_elements_from_hits(chunk_metadatas: list[dict]) -> list[str]:
    """Extract the visual_element_ids from a ranked list of retrieved chunk metadatas (visual
    caption-chunks only), preserving order — the retrieval surface for region-hit scoring."""
    out: list[str] = []
    for m in chunk_metadatas:
        if m and m.get("is_visual") and m.get("visual_element_id"):
            out.append(str(m["visual_element_id"]))
    return out
