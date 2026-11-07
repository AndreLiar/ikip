"""Two-stage extraction orchestration (Story 2.3). Pure + injected engines.

Stage 1 (NativeExtractor, e.g. PyMuPDF): read the native text layer per page,
detect tables, flag pages with no/sparse text as `needs_ocr`. Fast, $0.
Stage 2 (OcrEngine, e.g. Tesseract): OCR only the flagged pages. $0.
Then score quality and flag low-quality pages (AC4).

Cost control (AC2): OCR runs only on pages stage 1 couldn't read natively. A paid
engine (Azure Document Intelligence) can be injected as the OcrEngine later for
pages that still fail — same port.
"""

from __future__ import annotations

from typing import Protocol

from ikip_docproc.models import DocumentExtraction, ExtractionMethod, PageExtraction
from ikip_docproc.quality import is_low_quality, needs_ocr, score_page


class NativeExtractor(Protocol):
    """Stage 1: extract the PDF's native text + tables, per page."""

    def extract(self, pdf_bytes: bytes) -> DocumentExtraction: ...


class OcrEngine(Protocol):
    """Stage 2: OCR a single page image (rendered from the PDF) to text."""

    def ocr_page(self, pdf_bytes: bytes, page: int) -> str: ...


def extract_document(
    pdf_bytes: bytes,
    *,
    native: NativeExtractor,
    ocr: OcrEngine | None = None,
) -> DocumentExtraction:
    """Run the two-stage pipeline and score quality."""
    doc = native.extract(pdf_bytes)

    for pg in doc.pages:
        # Stage 1 may already flag needs_ocr; recompute from text as the source of truth.
        pg.needs_ocr = needs_ocr(pg.text)
        if pg.needs_ocr and ocr is not None:
            ocr_text = ocr.ocr_page(pdf_bytes, pg.page)
            if ocr_text.strip():
                pg.text = ocr_text
                pg.method = ExtractionMethod.ocr
                pg.needs_ocr = False  # satisfied by OCR
        pg.quality_score = score_page(pg.text)
        pg.low_quality = is_low_quality(pg.quality_score)

    return doc


def empty_document() -> DocumentExtraction:
    return DocumentExtraction(
        pages=[PageExtraction(page=1, text="", method=ExtractionMethod.native)]
    )
