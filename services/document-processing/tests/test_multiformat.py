"""Multi-format routing: Office (docx/pptx/xlsx) detection + upload typing for Docling.

Unit tests build tiny ZIP/OOXML byte blobs (no container). A gated live test converts a
minimal real .docx through the docling-serve container (IKIP_DOCLING_LIVE=1).
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest
from ikip_docproc.curation import _default_office_extractor, _looks_like_office
from ikip_docproc.docling_client import DoclingRemoteExtractor, _upload_for

_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _zip_with(member: str, body: bytes = b"<xml/>") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, body)
    return buf.getvalue()


def test_upload_for_detects_formats() -> None:
    assert _upload_for(b"%PDF-1.7 ...") == ("document.pdf", "application/pdf")
    assert _upload_for(_zip_with("word/document.xml"))[0] == "document.docx"
    assert _upload_for(_zip_with("ppt/presentation.xml"))[0] == "document.pptx"
    assert _upload_for(_zip_with("xl/workbook.xml"))[0] == "document.xlsx"
    assert _upload_for(b"<!DOCTYPE html><html></html>") == ("document.html", "text/html")
    assert _upload_for(_zip_with("random/thing.txt"))[1] == "application/zip"


def test_looks_like_office_by_content_type_and_sniff() -> None:
    assert _looks_like_office(b"", _DOCX_CT) is True
    assert _looks_like_office(_zip_with("word/document.xml"), None) is True
    assert _looks_like_office(_zip_with("xl/workbook.xml"), None) is True
    assert _looks_like_office(b"%PDF-1.7", "application/pdf") is False
    assert _looks_like_office(b"just text", "text/plain") is False
    assert _looks_like_office(_zip_with("random/thing.txt"), None) is False  # a non-office zip


def test_default_office_extractor_is_docling() -> None:
    assert isinstance(_default_office_extractor(), DoclingRemoteExtractor)


def _minimal_docx(text: str) -> bytes:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'  # noqa: E501
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'  # noqa: E501
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'  # noqa: E501
        "</Relationships>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


@pytest.mark.skipif(
    os.environ.get("IKIP_DOCLING_LIVE") != "1",
    reason="set IKIP_DOCLING_LIVE=1 to convert a real .docx via docling-serve",
)
def test_live_docx_roundtrip() -> None:
    docx = _minimal_docx("Hybrid multiformat docx smoke test")
    assert _looks_like_office(docx, None) is True
    extraction = DoclingRemoteExtractor().extract(docx)
    assert "multiformat docx smoke test" in extraction.text
