"""Real PyMuPDF extraction test (Story 2.3 AC1). Skipped unless the `extraction`
extra is installed (heavy engines are kept out of the fast CI job).
Run with: uv run --group extraction pytest services/document-processing/tests/test_engines.py
"""

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pymupdf") is None, reason="pymupdf (extraction extra) not installed"
)


def _make_native_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_pymupdf_extracts_native_text_with_page_refs() -> None:
    from ikip_docproc.engines import PyMuPDFExtractor
    from ikip_docproc.models import ExtractionMethod

    pdf = _make_native_pdf("Siemens S7-1500 fault code E42 reset procedure.")
    doc = PyMuPDFExtractor().extract(pdf)

    assert len(doc.pages) == 1
    assert doc.pages[0].page == 1  # page reference preserved (AC1)
    assert "E42" in doc.pages[0].text
    assert doc.pages[0].method is ExtractionMethod.native
    assert not doc.pages[0].needs_ocr  # native text present -> no OCR needed
    assert doc.pages[0].regions
    assert "E42" in doc.pages[0].regions[0].text
    assert all(0 <= value <= 1 for value in doc.pages[0].regions[0].bbox)


def test_detect_tables_flag_defaults_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from ikip_docproc.engines import PyMuPDFExtractor

    assert PyMuPDFExtractor(detect_tables=False)._detect_tables is False
    assert PyMuPDFExtractor(detect_tables=True)._detect_tables is True
    monkeypatch.setenv("IKIP_PDF_DETECT_TABLES", "0")
    assert PyMuPDFExtractor()._detect_tables is False  # bulk fast path
    monkeypatch.setenv("IKIP_PDF_DETECT_TABLES", "1")
    assert PyMuPDFExtractor()._detect_tables is True


def test_detect_tables_off_skips_table_detection_keeps_text() -> None:
    from ikip_docproc.engines import PyMuPDFExtractor

    pdf = _make_native_pdf("Boiler feedwater pump vibration limits table.")
    doc = PyMuPDFExtractor(detect_tables=False).extract(pdf)
    assert "vibration" in doc.pages[0].text  # native text unaffected
    assert doc.pages[0].tables == []  # detection skipped


def test_pymupdf_flags_empty_page_for_ocr() -> None:
    import pymupdf
    from ikip_docproc.engines import PyMuPDFExtractor

    doc = pymupdf.open()
    doc.new_page()  # a page with no text
    pdf = doc.tobytes()
    doc.close()

    extracted = PyMuPDFExtractor().extract(pdf)
    assert extracted.pages[0].needs_ocr is True
