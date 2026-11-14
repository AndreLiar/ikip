"""Docling-serve adapter: pure mapping (fixture), env selection, and a gated live call.

The mapping tests use a fixture captured from a REAL docling-serve conversion
(tests/fixtures/docling_sample.json), so they are deterministic and need no container
and no httpx. The live test runs the real HTTP round-trip only when IKIP_DOCLING_LIVE=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from ikip_docproc.docling_client import (
    DoclingConversionError,
    DoclingRemoteExtractor,
    docling_document_to_extraction,
)
from ikip_docproc.models import ExtractionMethod

_FIXTURE = Path(__file__).parent / "fixtures" / "docling_sample.json"


def test_maps_real_fixture_to_extraction() -> None:
    doc = json.loads(_FIXTURE.read_text())
    extraction = docling_document_to_extraction(doc)

    assert len(extraction.pages) == 1
    page = extraction.pages[0]
    assert page.page == 1
    assert page.method is ExtractionMethod.docling
    assert "IKIP Pump Maintenance Manual" in extraction.text
    # every region carries a 4-tuple bbox from the Docling provenance
    assert page.regions and all(len(r.bbox) == 4 for r in page.regions)


def test_maps_tables_and_multiple_pages() -> None:
    doc = {
        "pages": {"1": {}, "2": {}},
        "texts": [
            {
                "text": "page one heading",
                "prov": [{"page_no": 1, "bbox": {"l": 1, "t": 2, "r": 3, "b": 4}}],
            },
            {
                "text": "page two body",
                "prov": [{"page_no": 2, "bbox": {"l": 5, "t": 6, "r": 7, "b": 8}}],
            },
        ],
        "tables": [{"prov": [{"page_no": 2, "bbox": {"l": 0, "t": 0, "r": 9, "b": 9}}]}],
    }
    extraction = docling_document_to_extraction(doc)

    assert [p.page for p in extraction.pages] == [1, 2]
    assert extraction.pages[0].text == "page one heading"
    assert extraction.pages[1].tables and extraction.pages[1].tables[0].page == 2


def test_empty_document_yields_single_empty_page() -> None:
    extraction = docling_document_to_extraction({})
    assert len(extraction.pages) == 1
    assert extraction.text == ""


def test_default_extractor_selects_docling_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from ikip_docproc.curation import _default_pdf_extractor

    monkeypatch.setenv("IKIP_PDF_EXTRACTOR", "docling")
    monkeypatch.setenv("IKIP_DOCLING_URL", "http://docling.internal:5001")
    extractor = _default_pdf_extractor()

    assert isinstance(extractor, DoclingRemoteExtractor)
    assert extractor._base_url == "http://docling.internal:5001"


def test_non_success_status_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable docling-serve that reports a failed conversion surfaces as our error."""
    import httpx

    response = httpx.Response(
        200,
        json={"status": "failure", "errors": ["boom"], "document": {}},
        request=httpx.Request("POST", "http://localhost:5001/v1/convert/file"),
    )
    monkeypatch.setattr(httpx, "post", lambda *_a, **_k: response)
    with pytest.raises(DoclingConversionError):
        DoclingRemoteExtractor().extract(b"%PDF-1.4 ...")


@pytest.mark.skipif(
    os.environ.get("IKIP_DOCLING_LIVE") != "1",
    reason="set IKIP_DOCLING_LIVE=1 to hit a live docling-serve",
)
def test_live_roundtrip_against_container() -> None:
    import pymupdf  # the live test needs a real PDF to send

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Live Docling smoke test", fontsize=14)
    pdf_bytes = doc.tobytes()

    extractor = DoclingRemoteExtractor(os.environ.get("IKIP_DOCLING_URL", "http://localhost:5001"))
    extraction = extractor.extract(pdf_bytes)
    assert "Live Docling smoke test" in extraction.text
