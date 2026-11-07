"""Real extraction engine adapters (Story 2.3).

Heavy, optional (install the `extraction` / `docling` extra). Imported lazily so
the core pipeline/quality logic stays testable without them.
  - PyMuPDFExtractor  : stage 1 — native text + table detection + page refs
  - TesseractOcrEngine: stage 2 — OCR a rendered page image ($0; needs tesseract binary)
  - DoclingExtractor  : optional richer structure/tables path
"""

from __future__ import annotations

from ikip_docproc.models import (
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    TableRef,
)
from ikip_docproc.quality import needs_ocr


class PyMuPDFExtractor:
    """Stage-1 native extractor using PyMuPDF (fitz)."""

    def extract(self, pdf_bytes: bytes) -> DocumentExtraction:
        import pymupdf  # lazy: only when actually extracting

        pages: list[PageExtraction] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                tables = self._find_tables(page, i)
                pages.append(
                    PageExtraction(
                        page=i,
                        text=text,
                        method=ExtractionMethod.native,
                        needs_ocr=needs_ocr(text),
                        tables=tables,
                    )
                )
        return DocumentExtraction(pages=pages)

    @staticmethod
    def _find_tables(page, page_no: int) -> list[TableRef]:
        try:
            found = page.find_tables()
        except Exception:  # noqa: BLE001 — table detection is best-effort
            return []
        return [TableRef(page=page_no, bbox=tuple(t.bbox)) for t in getattr(found, "tables", [])]


class TesseractOcrEngine:
    """Stage-2 OCR: render a page to an image and run Tesseract."""

    def __init__(self, dpi: int = 200, lang: str = "eng") -> None:
        self._dpi = dpi
        self._lang = lang

    def ocr_page(self, pdf_bytes: bytes, page: int) -> str:
        import io

        import pymupdf
        import pytesseract
        from PIL import Image

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            pix = doc[page - 1].get_pixmap(dpi=self._dpi)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img, lang=self._lang)


class DoclingExtractor:
    """Optional richer structure/tables extractor (Docling). Heavy (ML models)."""

    def extract(self, pdf_bytes: bytes) -> DocumentExtraction:
        import tempfile

        from docling.document_converter import DocumentConverter

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf_bytes)
            f.flush()
            result = DocumentConverter().convert(f.name)
        md = result.document.export_to_markdown()
        # Docling returns a whole-document rendering; keep it as a single "page 1"
        # record here (page-accurate Docling mapping is a follow-up).
        return DocumentExtraction(
            pages=[PageExtraction(page=1, text=md, method=ExtractionMethod.docling)]
        )
