"""Per-page hybrid routing: classification + orchestration with fake engines (no heavy deps)."""

from __future__ import annotations

import pytest
from ikip_docproc.models import DocumentExtraction, ExtractionMethod, PageExtraction, TableRef
from ikip_docproc.routing import (
    HybridPdfExtractor,
    PageRoute,
    classify_page,
    extract_document_hybrid,
)

_LONG = "this is a page with plenty of readable native text to extract" * 2


def _page(n: int, text: str, tables: bool = False) -> PageExtraction:
    return PageExtraction(
        page=n,
        text=text,
        method=ExtractionMethod.native,
        tables=[TableRef(page=n, bbox=None)] if tables else [],
    )


class _FakeNative:
    def __init__(self, pages: list[PageExtraction]) -> None:
        self._pages = pages

    def extract(self, _data: bytes) -> DocumentExtraction:
        return DocumentExtraction(pages=self._pages)


class _FakeOcr:
    def ocr_page(self, _data: bytes, page: int) -> str:
        return f"ocr text page {page}"


class _FakeLayout:
    def layout_page(self, _data: bytes, page: int) -> PageExtraction:
        return PageExtraction(
            page=page,
            text=f"docling layout page {page}",
            method=ExtractionMethod.docling,
            tables=[TableRef(page=page, bbox=None)],
        )


def test_classify_page_routes() -> None:
    assert classify_page(_page(1, _LONG, tables=True)) is PageRoute.layout
    assert classify_page(_page(2, "")) is PageRoute.ocr
    assert classify_page(_page(3, _LONG)) is PageRoute.native


def test_hybrid_routes_each_page_to_its_engine() -> None:
    pages = [_page(1, _LONG, tables=True), _page(2, ""), _page(3, _LONG)]
    doc = extract_document_hybrid(
        b"%PDF-", native=_FakeNative(pages), ocr=_FakeOcr(), layout=_FakeLayout()
    )

    assert [p.page for p in doc.pages] == [1, 2, 3]  # order preserved
    assert doc.pages[0].method is ExtractionMethod.docling
    assert doc.pages[0].text == "docling layout page 1"
    assert doc.pages[1].method is ExtractionMethod.ocr
    assert doc.pages[1].text == "ocr text page 2"
    assert doc.pages[2].method is ExtractionMethod.native
    assert all(p.quality_score > 0 for p in doc.pages)  # every page finalized/scored


def test_missing_engine_degrades_to_native() -> None:
    # A table page but no layout engine, a scanned page but no ocr engine → keep native.
    pages = [_page(1, _LONG, tables=True), _page(2, "")]
    doc = extract_document_hybrid(b"%PDF-", native=_FakeNative(pages), ocr=None, layout=None)
    assert doc.pages[0].method is ExtractionMethod.native
    assert doc.pages[1].method is ExtractionMethod.native


def test_hybrid_extractor_wires_engines() -> None:
    pages = [_page(1, ""), _page(2, _LONG)]
    extractor = HybridPdfExtractor(native=_FakeNative(pages), ocr=_FakeOcr(), layout=_FakeLayout())
    doc = extractor.extract(b"%PDF-")
    assert doc.pages[0].text == "ocr text page 1"
    assert doc.pages[1].method is ExtractionMethod.native


def test_default_extractor_hybrid_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    from ikip_docproc.curation import _default_pdf_extractor

    monkeypatch.setenv("IKIP_PDF_EXTRACTOR", "hybrid")
    monkeypatch.setenv("IKIP_OCR_ENGINE", "tesseract")  # avoid loading Indra weights in this test
    assert isinstance(_default_pdf_extractor(), HybridPdfExtractor)
