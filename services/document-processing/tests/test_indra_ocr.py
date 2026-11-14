"""Indra OCR engine: wiring with a fake converter (no weights) + a gated live OCR.

Indra's weights are OpenRAIL-M (restricted) — these tests never require them unless you
opt in with IKIP_INDRA_LIVE=1.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
from ikip_docproc.engines import IndraOcrEngine

# The slicing tests build a real PDF with PyMuPDF (the `extraction` extra); skip them when
# it isn't installed so the fast `validate` CI job (base deps only) stays green.
_needs_pymupdf = pytest.mark.skipif(
    importlib.util.find_spec("pymupdf") is None, reason="pymupdf (extraction extra) not installed"
)


def _one_page_pdf(text: str) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text, fontsize=12)
    return doc.tobytes()


@_needs_pymupdf
def test_ocr_page_slices_and_joins_converter_text(monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _one_page_pdf("native")

    class _FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

    class _FakeConverter:
        def convert(self, _path: str):  # noqa: ANN202 — mimics indra_ocr Converter.convert
            yield (1, _FakePage("recovered line one"))
            yield (2, _FakePage("recovered line two"))

    engine = IndraOcrEngine()
    monkeypatch.setattr(engine, "_load", lambda: _FakeConverter())
    assert engine.ocr_page(pdf, 1) == "recovered line one\nrecovered line two"


def test_default_ocr_engine_is_indra_when_installed() -> None:
    import importlib.util

    from ikip_docproc.curation import _default_ocr_engine

    engine = _default_ocr_engine()
    if importlib.util.find_spec("indra_ocr") is not None:
        assert isinstance(engine, IndraOcrEngine)
    else:  # graceful fallback path
        from ikip_docproc.engines import TesseractOcrEngine

        assert isinstance(engine, TesseractOcrEngine)


@_needs_pymupdf
@pytest.mark.skipif(
    os.environ.get("IKIP_INDRA_LIVE") != "1",
    reason="set IKIP_INDRA_LIVE=1 to run real Indra OCR (downloads OpenRAIL-M weights)",
)
def test_indra_live_ocr() -> None:
    pdf = _one_page_pdf("Indra live OCR smoke test")
    text = IndraOcrEngine().ocr_page(pdf, 1)
    assert "Indra" in text
