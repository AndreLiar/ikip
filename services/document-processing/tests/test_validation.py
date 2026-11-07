"""Content validation tests (Story 2.4 AC3/AC4). Pure (Pandera + report)."""

from ikip_docproc.models import DocumentExtraction, ExtractionMethod, PageExtraction
from ikip_docproc.validation import validate_pages


def _page(page: int, text: str, q: float, low: bool = False) -> PageExtraction:
    return PageExtraction(
        page=page, text=text, method=ExtractionMethod.native, quality_score=q, low_quality=low
    )


def test_valid_document_passes() -> None:
    doc = DocumentExtraction(
        pages=[_page(1, "Good content here.", 0.9), _page(2, "More content.", 0.8)]
    )
    report = validate_pages(doc)
    assert report.ok
    assert report.page_count == 2
    assert report.empty_pages == []


def test_all_empty_document_fails() -> None:
    doc = DocumentExtraction(pages=[_page(1, "", 0.0), _page(2, "   ", 0.0)])
    report = validate_pages(doc)
    assert not report.ok
    assert "all pages are empty" in report.errors
    assert report.empty_pages == [1, 2]


def test_no_pages_fails() -> None:
    report = validate_pages(DocumentExtraction(pages=[]))
    assert not report.ok
    assert "document has no pages" in report.errors


def test_report_low_quality_pages_and_error_info() -> None:
    doc = DocumentExtraction(pages=[_page(1, "ok content", 0.9), _page(2, "noise", 0.1, low=True)])
    report = validate_pages(doc)
    assert report.ok  # one low-quality page doesn't invalidate the doc
    assert report.low_quality_pages == [2]
    info = report.as_error_info()
    assert info["low_quality_pages"] == [2]
