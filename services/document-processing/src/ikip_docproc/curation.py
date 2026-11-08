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


def _default_pdf_extractor() -> TextExtractor:
    # Lazy: only imports the heavy engines (PyMuPDF/Tesseract) when a PDF is actually seen.
    from ikip_docproc.engines import PdfExtractor

    return PdfExtractor()


def curate_document(
    raw_bytes: bytes,
    *,
    source: str,
    content_type: str | None = None,
    extractor: TextExtractor | None = None,
) -> CuratedDocument:
    """Produce curated text + metadata from a raw artifact. With `extractor` given, read
    the PDF text layer; otherwise decode text-first."""
    # Pick the real PDF extractor (PyMuPDF → OCR) when the artifact is a PDF and no
    # extractor was injected; otherwise decode text-first. Injected extractor always wins.
    if extractor is None and _looks_like_pdf(raw_bytes, content_type):
        extractor = _default_pdf_extractor()

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
