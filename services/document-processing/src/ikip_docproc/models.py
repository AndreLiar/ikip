"""Extraction data models (Story 2.3). Engine-free, so the orchestration/quality
logic is testable without PyMuPDF/Docling/Tesseract installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ExtractionMethod(StrEnum):
    native = "native"  # text read from the PDF's text layer (PyMuPDF) — fast, $0
    ocr = "ocr"  # text recognized from a page image (Tesseract) — $0
    docling = "docling"  # rich structure/tables (optional richer path)


@dataclass(frozen=True)
class TableRef:
    """A detected table located by its page (AC3). Content extraction is richer
    via Docling; at minimum we record *where* tables are."""

    page: int
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class TextRegion:
    """Text block with a normalized PDF bounding box (x0, y0, x1, y1)."""

    page: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass
class PageExtraction:
    page: int  # 1-based page number (preserves page references, AC1)
    text: str
    method: ExtractionMethod
    needs_ocr: bool = False  # set by stage 1 when the native text layer is empty/sparse
    tables: list[TableRef] = field(default_factory=list)
    regions: list[TextRegion] = field(default_factory=list)
    quality_score: float = 0.0  # 0..1; low -> flagged (AC4)
    low_quality: bool = False


@dataclass
class DocumentExtraction:
    pages: list[PageExtraction]

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def needs_ocr_pages(self) -> list[int]:
        return [p.page for p in self.pages if p.needs_ocr]

    @property
    def low_quality_pages(self) -> list[int]:
        return [p.page for p in self.pages if p.low_quality]
