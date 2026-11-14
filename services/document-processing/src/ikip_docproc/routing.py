"""Per-page hybrid extraction routing — the "ideal process" path.

Instead of forcing one engine on a whole document, classify EACH page from cheap stage-1
signals and send it to the engine that fits, then merge back in original page order:

  NATIVE  — dense native text, no tables      → PyMuPDF text layer (fast, $0)
  OCR     — no/sparse native text (scanned)    → OcrEngine (Indra by default)
  LAYOUT  — tables / rich structure on the page → Docling (per-page, docling-serve)

Everything stays behind the existing ports (ADR 0021): `NativeExtractor` and `OcrEngine`
come from `pipeline`; `LayoutEngine` is added here. `HybridPdfExtractor` is itself a
`TextExtractor`, so `curate_document` selects it with IKIP_PDF_EXTRACTOR=hybrid with no
change to anything downstream (it still only sees a `DocumentExtraction`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from ikip_docproc.models import (
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    TableRef,
    TextRegion,
)
from ikip_docproc.pipeline import NativeExtractor, OcrEngine
from ikip_docproc.quality import is_low_quality, needs_ocr, score_page

if TYPE_CHECKING:
    from ikip_docproc.docling_client import DoclingRemoteExtractor


class PageRoute(StrEnum):
    native = "native"
    ocr = "ocr"
    layout = "layout"


class LayoutEngine(Protocol):
    """Rich per-page layout/table extractor (e.g. Docling)."""

    def layout_page(self, pdf_bytes: bytes, page: int) -> PageExtraction: ...


def classify_page(page: PageExtraction) -> PageRoute:
    """Decide where a page should go from stage-1 signals.

    Tables win (Docling reconstructs them far better than flat text); then a page with
    almost no native text is treated as scanned and OCR'd; otherwise the native text layer
    is already good and cheapest. A scanned page with tables has no detectable table layer
    yet, so it falls through to OCR — Indra still recovers tabular text."""
    if page.tables:
        return PageRoute.layout
    if needs_ocr(page.text):
        return PageRoute.ocr
    return PageRoute.native


def extract_document_hybrid(
    pdf_bytes: bytes,
    *,
    native: NativeExtractor,
    ocr: OcrEngine | None = None,
    layout: LayoutEngine | None = None,
) -> DocumentExtraction:
    """Stage-1 once (native text + table detection + needs_ocr), then re-route each page.

    `layout`/`ocr` are optional: if a page routes to an engine that wasn't provided, the
    native result is kept (graceful degradation — never worse than native-only)."""
    doc = native.extract(pdf_bytes)

    for idx, pg in enumerate(doc.pages):
        route = classify_page(pg)
        if route is PageRoute.layout and layout is not None:
            doc.pages[idx] = _finalize(layout.layout_page(pdf_bytes, pg.page))
            continue
        if route is PageRoute.ocr and ocr is not None:
            ocr_text = ocr.ocr_page(pdf_bytes, pg.page)
            if ocr_text.strip():
                pg.text = ocr_text
                pg.method = ExtractionMethod.ocr
                pg.needs_ocr = False
        pg.needs_ocr = needs_ocr(pg.text)
        _finalize(pg)

    return doc


def _finalize(pg: PageExtraction) -> PageExtraction:
    pg.quality_score = score_page(pg.text)
    pg.low_quality = is_low_quality(pg.quality_score)
    return pg


class DoclingLayoutEngine:
    """`LayoutEngine` that extracts ONE page via docling-serve (cost is paid only for the
    pages that actually need rich layout). Slices the page to a 1-page PDF, converts it,
    and renumbers the result back to the real page number."""

    def __init__(self, extractor: DoclingRemoteExtractor | None = None) -> None:
        self._extractor = extractor  # built lazily if None

    def _engine(self) -> DoclingRemoteExtractor:
        if self._extractor is None:
            from ikip_docproc.docling_client import DoclingRemoteExtractor

            self._extractor = DoclingRemoteExtractor()
        return self._extractor

    def layout_page(self, pdf_bytes: bytes, page: int) -> PageExtraction:
        import pymupdf

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src:
            one = pymupdf.open()
            one.insert_pdf(src, from_page=page - 1, to_page=page - 1)
            clipped = one.tobytes()
            one.close()

        extraction = self._engine().extract(clipped)
        if not extraction.pages:
            return PageExtraction(page=page, text="", method=ExtractionMethod.docling)
        got = extraction.pages[0]
        return PageExtraction(
            page=page,
            text=got.text,
            method=ExtractionMethod.docling,
            regions=[TextRegion(page=page, text=r.text, bbox=r.bbox) for r in got.regions],
            tables=[TableRef(page=page, bbox=t.bbox) for t in got.tables],
        )


class HybridPdfExtractor:
    """`TextExtractor` that routes each page to native / OCR / Docling (see module doc)."""

    def __init__(
        self,
        *,
        native: NativeExtractor | None = None,
        ocr: OcrEngine | None = None,
        layout: LayoutEngine | None = None,
    ) -> None:
        if native is None:
            from ikip_docproc.engines import PyMuPDFExtractor

            native = PyMuPDFExtractor()
        self._native = native
        self._ocr = ocr
        self._layout = layout

    def extract(self, data: bytes) -> DocumentExtraction:
        return extract_document_hybrid(
            data, native=self._native, ocr=self._ocr, layout=self._layout
        )
