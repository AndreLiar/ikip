"""Two-stage pipeline tests (Story 2.3 AC1/AC2/AC3). Pure — fake engines, no PDFs."""

from ikip_docproc.models import (
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    TableRef,
)
from ikip_docproc.pipeline import extract_document


class FakeNative:
    """Stage-1 fake: page 1 native text, page 2 empty (scanned), with a table."""

    def extract(self, pdf_bytes: bytes) -> DocumentExtraction:
        return DocumentExtraction(
            pages=[
                PageExtraction(
                    page=1,
                    text="Pump S7-1500 maintenance. " * 10,
                    method=ExtractionMethod.native,
                    tables=[TableRef(page=1, bbox=(0, 0, 100, 50))],
                ),
                PageExtraction(page=2, text="", method=ExtractionMethod.native),
            ]
        )


class FakeOcr:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def ocr_page(self, pdf_bytes: bytes, page: int) -> str:
        self.calls.append(page)
        return "Recognized text from the scanned page. " * 5


def test_native_only_keeps_page_refs_and_tables() -> None:
    doc = extract_document(b"%PDF", native=FakeNative(), ocr=None)
    assert [p.page for p in doc.pages] == [1, 2]
    assert doc.pages[0].tables[0].page == 1  # table located by page (AC3)
    assert doc.pages[0].method is ExtractionMethod.native
    # page 2 is empty + no OCR -> flagged needs_ocr and low quality
    assert 2 in doc.needs_ocr_pages
    assert 2 in doc.low_quality_pages


def test_ocr_runs_only_on_scanned_pages() -> None:
    ocr = FakeOcr()
    doc = extract_document(b"%PDF", native=FakeNative(), ocr=ocr)
    # stage 2 called only for the empty page (cost control, AC2)
    assert ocr.calls == [2]
    assert doc.pages[1].method is ExtractionMethod.ocr
    assert 2 not in doc.needs_ocr_pages  # satisfied by OCR
    assert doc.pages[1].quality_score > 0


def test_document_text_concatenates_pages() -> None:
    doc = extract_document(b"%PDF", native=FakeNative(), ocr=FakeOcr())
    assert "Pump S7-1500" in doc.text
    assert "Recognized text" in doc.text
