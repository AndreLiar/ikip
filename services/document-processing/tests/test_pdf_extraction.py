"""Real PDF extraction via the PdfExtractor adapter (Story 2.3).

Gated on the `extraction` group (PyMuPDF). Builds a real one-page PDF in-memory with
PyMuPDF, then asserts curate_document auto-detects it and reads the text layer — i.e.
the text-first seam swaps to the real engine for PDFs with no code change elsewhere.
"""

import pytest

pymupdf = pytest.importorskip("pymupdf")  # skip unless the extraction group is installed

from ikip_docproc.curation import curate_document  # noqa: E402
from ikip_docproc.engines import PdfExtractor  # noqa: E402


def _one_page_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_curate_auto_detects_pdf_and_reads_text_layer() -> None:
    pdf = _one_page_pdf("Fault code E42 indicates the pump motor has overheated. Rev. D")
    assert pdf[:5] == b"%PDF-"  # it's a real PDF

    doc = curate_document(pdf, source="pump-manual.pdf")  # no extractor injected
    assert "E42" in doc.text  # native text layer was extracted (not decoded as bytes)
    assert doc.page_count == 1
    assert doc.metadata.revision == "D"


def test_pdf_extractor_native_only() -> None:
    pdf = _one_page_pdf("Torque the gearbox bolts to 42 Nm.")
    extraction = PdfExtractor(ocr=False).extract(pdf)
    assert "Torque" in extraction.text
    assert len(extraction.pages) == 1
