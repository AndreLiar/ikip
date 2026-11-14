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
    TextRegion,
)
from ikip_docproc.quality import needs_ocr


class PdfExtractor:
    """Two-stage PDF extractor as a `TextExtractor` (native PyMuPDF → OCR fallback).

    Satisfies `ikip_docproc.curation.TextExtractor` (`.extract(bytes) -> DocumentExtraction`
    with `.text` + `.pages`), so curation can read a real PDF instead of decoding text.
    OCR (Tesseract) is applied only to pages whose native text layer is empty/sparse
    (`extract_document`); pass `ocr=False` for native-only (digital-born PDFs, no tesseract)."""

    def __init__(self, *, ocr: bool = True, ocr_engine: object | None = None) -> None:
        self._native = PyMuPDFExtractor()
        # Injected engine wins (the factory passes Indra by default); else Tesseract when
        # ocr=True, or None for native-only (digital-born PDFs, no OCR binary needed).
        if ocr_engine is not None:
            self._ocr = ocr_engine
        else:
            self._ocr = TesseractOcrEngine() if ocr else None

    def extract(self, data: bytes) -> DocumentExtraction:
        from ikip_docproc.pipeline import extract_document

        return extract_document(data, native=self._native, ocr=self._ocr)


class PyMuPDFExtractor:
    """Stage-1 native extractor using PyMuPDF (fitz)."""

    def extract(self, pdf_bytes: bytes) -> DocumentExtraction:
        import pymupdf  # lazy: only when actually extracting

        pages: list[PageExtraction] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc, start=1):
                regions = self._text_regions(page, i)
                text = "\n".join(region.text for region in regions)
                tables = self._find_tables(page, i)
                pages.append(
                    PageExtraction(
                        page=i,
                        text=text,
                        method=ExtractionMethod.native,
                        needs_ocr=needs_ocr(text),
                        tables=tables,
                        regions=regions,
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

    @staticmethod
    def _text_regions(page, page_no: int) -> list[TextRegion]:
        width, height = float(page.rect.width), float(page.rect.height)
        if width <= 0 or height <= 0:
            return []
        regions: list[TextRegion] = []
        for block in page.get_text("blocks") or []:
            x0, y0, x1, y1, text = block[:5]
            if not str(text).strip():
                continue
            regions.append(
                TextRegion(
                    page=page_no,
                    text=str(text).strip(),
                    bbox=(x0 / width, y0 / height, x1 / width, y1 / height),
                )
            )
        return regions


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


class IndraOcrEngine:
    """Stage-2 OCR via Indra (Datalab, 2026) — a ~1M-param ONNX model, CPU-only, that
    reconstructs reading order + tables and emits clean text/markdown. Drop-in for the
    `OcrEngine` seam (`ocr_page -> str`), so it replaces Tesseract without touching the
    pipeline.

    LICENSE CAVEAT: Indra's CODE is Apache-2.0 but its WEIGHTS are a modified OpenRAIL-M
    (free for research/personal use and startups < $20M; not usable competitively with
    their API). That is NOT in `is_license_allowed` (Story 6.5) — acceptable for this
    thesis/portfolio, flagged for a commercial SaaS. See ADR on extraction routing.
    """

    def __init__(self, *, threads: int = 4, dpi: float = 200.0, mode: str = "auto") -> None:
        self._threads = threads
        self._dpi = dpi
        self._mode = mode
        self._converter = None  # loaded lazily (model load is expensive) and cached

    def _load(self):  # noqa: ANN202
        if self._converter is None:
            import indra_ocr  # lazy: only when Indra is actually used (`--group indra`)

            self._converter = indra_ocr.load(threads=self._threads, dpi=self._dpi, mode=self._mode)
        return self._converter

    def ocr_page(self, pdf_bytes: bytes, page: int) -> str:
        import tempfile

        import pymupdf

        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src:
            one = pymupdf.open()
            one.insert_pdf(src, from_page=page - 1, to_page=page - 1)
            data = one.tobytes()
            one.close()
        # Indra's convert() takes a path, not bytes — write the single-page slice out.
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(data)
            handle.flush()
            texts = [pg.text for _i, pg in self._load().convert(handle.name)]
        return "\n".join(t for t in texts if t)


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
