"""Visual-element extraction: diagrams + visual tables as evidence (Epic 9, Story 9.1, ADR 0031).

Turns a page's detected tables (`TableRef`) and pictures (`PictureRef`, from the `LayoutEngine`)
into `VisualElementSpec`s — the DB-free record persisted as retrievable visual evidence (page +
bbox, kind, detector confidence). Low-confidence detections are flagged for review (AC3). Content
becomes searchable later via caption-and-embed (Story 9.2); here we capture *where* and *what kind*.

Pure + deterministic → unit-testable without Docling.
"""

from __future__ import annotations

from dataclasses import dataclass

from ikip_docproc.models import PageExtraction

# Below this detector confidence, a visual element is flagged for human review (AC3).
VISUAL_LOW_CONFIDENCE = 0.6
# A detected (structural) table is reliable; pictures carry the detector's own confidence.
_TABLE_CONFIDENCE = 0.9


@dataclass(frozen=True)
class VisualElementSpec:
    """A planned visual element (DB-free): where it is, what kind, how confident."""

    kind: str  # "table" | "figure"
    page: int
    bbox: tuple[float, float, float, float] | None
    confidence: float

    @property
    def low_confidence(self) -> bool:
        return self.confidence < VISUAL_LOW_CONFIDENCE


def visual_elements_from_page(page: PageExtraction) -> list[VisualElementSpec]:
    """Collect a page's tables + pictures as visual-element specs (AC1)."""
    specs: list[VisualElementSpec] = []
    for t in page.tables:
        specs.append(
            VisualElementSpec(kind="table", page=t.page, bbox=t.bbox, confidence=_TABLE_CONFIDENCE)
        )
    for p in page.pictures:
        specs.append(
            VisualElementSpec(kind="figure", page=p.page, bbox=p.bbox, confidence=p.confidence)
        )
    return specs


def visual_elements_from_pages(pages: list[PageExtraction]) -> list[VisualElementSpec]:
    out: list[VisualElementSpec] = []
    for page in pages:
        out.extend(visual_elements_from_page(page))
    return out
