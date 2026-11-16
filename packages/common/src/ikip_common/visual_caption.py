"""Caption-and-embed: make visual elements searchable + citable (Epic 9, Story 9.2, ADR 0031).

For each visual element: caption its image (vision LLM, via `VisionCaptioner`), store the caption,
and create a **Chunk** whose content IS the caption — so the *existing* embedding + hybrid
retrieval index and find it with no new retrieval code. The caption-chunk's metadata carries the
`visual_element_id` + region (page/bbox/kind), so a retrieval hit resolves to the exact visual
region (`VisualCitation`) the viewer highlights (FR16).

The caption chunk is marked `is_visual` so the answer layer can treat it as visual evidence.
Image bytes are loaded via an injected callable (crops live in R2); captioning is idempotent
(skips elements already captioned).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select

from ikip_common.db.models import Chunk, VisualElement
from ikip_common.vision import VisionCaptioner


@dataclass(frozen=True)
class VisualCitation:
    """A citation that resolves to a visual region the viewer can highlight (Story 9.3)."""

    visual_element_id: str
    kind: str
    page: int
    bbox: list | None
    crop_object_key: str | None


def caption_and_index_visual_elements(
    session,  # noqa: ANN001 — SQLAlchemy Session
    tenant_id: uuid.UUID,
    document_version_id: uuid.UUID,
    captioner: VisionCaptioner,
    load_image: Callable[[VisualElement], bytes | None],
) -> int:
    """Caption + index the uncaptioned visual elements of a version. Returns the number captioned.
    Skips elements already captioned, lacking a section, or whose image can't be loaded."""
    elements = (
        session.execute(
            select(VisualElement).where(
                VisualElement.tenant_id == tenant_id,
                VisualElement.document_version_id == document_version_id,
                VisualElement.caption.is_(None),
            )
        )
        .scalars()
        .all()
    )

    captioned = 0
    for el in elements:
        if el.section_id is None:  # need a section to attach the searchable chunk to (FR16)
            continue
        image = load_image(el)
        if not image:
            continue
        caption = (captioner.caption(image, kind=el.kind) or "").strip()
        if not caption:
            continue
        el.caption = caption
        session.add(
            Chunk(
                tenant_id=tenant_id,
                section_id=el.section_id,
                content=caption,  # the caption IS the embedded/searched text (reuses the stack)
                page_start=el.page,
                page_end=el.page,
                chunk_metadata={
                    "is_visual": True,
                    "visual_element_id": str(el.id),
                    "kind": el.kind,
                    "page": el.page,
                    "bbox": el.bbox,
                    "crop_object_key": el.crop_object_key,
                },
            )
        )
        captioned += 1
    return captioned


def visual_citation_from_chunk_metadata(meta: dict) -> VisualCitation | None:
    """If a retrieved chunk is a visual caption-chunk, resolve its region citation; else None."""
    if not meta or not meta.get("is_visual"):
        return None
    return VisualCitation(
        visual_element_id=str(meta.get("visual_element_id")),
        kind=meta.get("kind", "figure"),
        page=meta.get("page_start") or meta.get("page") or 0,
        bbox=meta.get("bbox"),
        crop_object_key=meta.get("crop_object_key"),
    )
