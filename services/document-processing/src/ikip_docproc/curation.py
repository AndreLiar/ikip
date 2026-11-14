"""Curation: raw bytes → clean, curated text + metadata (Story 2.3/2.4 assembly).

Text-first (ADR 0012 / decision): raw bytes are decoded as text (HTML tags stripped),
then `clean_text` + `build_metadata`. A PDF `NativeExtractor` (PyMuPDF, Story 2.3) is
an **injectable Protocol** — pass one to extract a PDF's text layer instead; OCR stays
a later adapter behind the same seam. Pure + engine-free by default → CI-testable.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Protocol

from ikip_docproc.cleaning import clean_text
from ikip_docproc.metadata import DocumentMetadata, build_metadata
from ikip_docproc.models import TextRegion

_TAG = re.compile(r"<[^>]+>")
# Boilerplate regions to drop before extracting text: scripts/styles plus nav/header/
# footer/aside/form — the menus, cookie banners and version pickers that otherwise
# pollute the curated text (and retrieval). Removed whole, tag + contents.
_BOILERPLATE = re.compile(
    r"<(script|style|nav|header|footer|aside|form)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
# Prefer the main content region when the page marks one (<main>/<article>). Picks
# the largest such block so a page with several <article>s keeps the biggest.
_MAIN_REGION = re.compile(r"<(main|article)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
# Sniff HTML by content, since the content-type isn't always threaded through
# (ingestion jobs don't persist it). A connector that fetches an HTML page yields
# bytes starting with a doctype/<html>; strip tags even when content_type is None.
_HTML_SNIFF = re.compile(r"<!doctype\s+html|<html[\s>]", re.IGNORECASE)


class TextExtractor(Protocol):
    """A PDF/native extractor (e.g. PyMuPDF). Returns an object exposing `.text` +
    `.pages` (see `ikip_docproc.models.DocumentExtraction`)."""

    def extract(self, data: bytes): ...  # noqa: ANN201


@dataclass
class CuratedDocument:
    text: str
    metadata: DocumentMetadata
    page_count: int
    regions: list[TextRegion] = field(default_factory=list)


def _strip_html(text: str) -> str:
    """Extract readable text from HTML: drop boilerplate regions, prefer the main
    content block if the page marks one, then strip remaining tags + unescape.
    Pure heuristic (no dep); `trafilatura`-grade extraction is a future adapter."""
    body = _BOILERPLATE.sub(" ", text)
    regions = _MAIN_REGION.findall(body)
    if regions:
        # findall returns (tag, inner); keep the largest inner region.
        body = max((inner for _tag, inner in regions), key=len)
    body = _TAG.sub(" ", body)
    return html.unescape(body)


def _decode_text(raw: bytes, content_type: str | None) -> str:
    text = raw.decode("utf-8", errors="replace")
    is_html = (content_type is not None and "html" in content_type.lower()) or bool(
        _HTML_SNIFF.search(text[:4096])
    )
    return _strip_html(text) if is_html else text


def _title_from(source: str) -> str:
    tail = source.rstrip("/").split("/")[-1] or source
    return tail.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip() or source


def _looks_like_pdf(raw_bytes: bytes, content_type: str | None) -> bool:
    return (content_type is not None and "pdf" in content_type.lower()) or raw_bytes[:5] == b"%PDF-"


# OOXML MIME substrings (docx/pptx/xlsx + the legacy ms* types) and the office folders
# inside the ZIP container — either is enough to route the artifact to Docling.
_OFFICE_CTYPE_HINTS = ("officedocument", "msword", "ms-powerpoint", "ms-excel")
_OFFICE_ZIP_MEMBERS = ("word/", "ppt/", "xl/")


def _looks_like_office(raw_bytes: bytes, content_type: str | None) -> bool:
    """True for Word/PowerPoint/Excel (OOXML). PyMuPDF can't read these; Docling can.
    Trusts the content-type hint (jobs carry it) and falls back to sniffing the ZIP."""
    if content_type and any(h in content_type.lower() for h in _OFFICE_CTYPE_HINTS):
        return True
    if raw_bytes[:4] == b"PK\x03\x04":
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                return any(n.startswith(_OFFICE_ZIP_MEMBERS) for n in zf.namelist())
        except zipfile.BadZipFile:
            return False
    return False


def _default_office_extractor() -> TextExtractor:
    # Office formats have no native PyMuPDF path — Docling (docling-serve container) parses
    # docx/pptx/xlsx whole-document. Requires the container; same TextExtractor seam (ADR 0021).
    import os

    from ikip_docproc.docling_client import DoclingRemoteExtractor

    return DoclingRemoteExtractor(
        base_url=os.environ.get("IKIP_DOCLING_URL", "http://localhost:5001")
    )


def _default_ocr_engine():  # noqa: ANN202
    """The OCR engine for stage 2, chosen by IKIP_OCR_ENGINE. Default is **Indra** (faster,
    reading-order/table-aware); falls back to Tesseract if the `indra` group isn't installed,
    so environments without the weights still work. Both satisfy the `OcrEngine` seam."""
    import os

    choice = os.environ.get("IKIP_OCR_ENGINE", "indra").strip().lower()
    if choice != "tesseract":
        try:
            import indra_ocr  # noqa: F401 — probe availability before committing to it

            from ikip_docproc.engines import IndraOcrEngine

            return IndraOcrEngine()
        except ImportError:
            pass  # indra group not installed → Tesseract
    from ikip_docproc.engines import TesseractOcrEngine

    return TesseractOcrEngine()


def _default_pdf_extractor() -> TextExtractor:
    # The extractor is chosen by IKIP_PDF_EXTRACTOR (same TextExtractor seam, ADR 0021):
    #   pymupdf (default) — two-stage PyMuPDF native → OCR fallback (OCR engine = Indra)
    #   docling           — whole-doc Docling via the docling-serve container
    #   hybrid | auto     — per-page routing: native / OCR / Docling (the "ideal" path)
    # Heavy engines are imported lazily, only when a PDF is actually seen.
    import os

    choice = os.environ.get("IKIP_PDF_EXTRACTOR", "pymupdf").strip().lower()
    docling_url = os.environ.get("IKIP_DOCLING_URL", "http://localhost:5001")

    if choice == "docling":
        from ikip_docproc.docling_client import DoclingRemoteExtractor

        return DoclingRemoteExtractor(base_url=docling_url)

    if choice in ("hybrid", "auto"):
        from ikip_docproc.docling_client import DoclingRemoteExtractor
        from ikip_docproc.engines import PyMuPDFExtractor
        from ikip_docproc.routing import DoclingLayoutEngine, HybridPdfExtractor

        return HybridPdfExtractor(
            native=PyMuPDFExtractor(),
            ocr=_default_ocr_engine(),
            layout=DoclingLayoutEngine(DoclingRemoteExtractor(base_url=docling_url)),
        )

    from ikip_docproc.engines import PdfExtractor

    return PdfExtractor(ocr_engine=_default_ocr_engine())


def curate_document(
    raw_bytes: bytes,
    *,
    source: str,
    content_type: str | None = None,
    extractor: TextExtractor | None = None,
) -> CuratedDocument:
    """Produce curated text + metadata from a raw artifact. With `extractor` given, read
    the PDF text layer; otherwise decode text-first."""
    # Route by format when no extractor was injected (injected always wins): PDF → the real
    # PDF extractor (PyMuPDF/OCR/hybrid); Office (docx/pptx/xlsx) → Docling; else decode
    # text-first (HTML/plain text).
    if extractor is None:
        if _looks_like_pdf(raw_bytes, content_type):
            extractor = _default_pdf_extractor()
        elif _looks_like_office(raw_bytes, content_type):
            extractor = _default_office_extractor()

    if extractor is not None:
        extraction = extractor.extract(raw_bytes)
        raw_text = extraction.text
        page_count = len(extraction.pages)
        regions = [region for page in extraction.pages for region in getattr(page, "regions", [])]
    else:
        raw_text = _decode_text(raw_bytes, content_type)
        page_count = 1
        regions = []

    text = clean_text(raw_text)
    metadata = build_metadata(title=_title_from(source), text=text, page_count=page_count)
    return CuratedDocument(text=text, metadata=metadata, page_count=page_count, regions=regions)
