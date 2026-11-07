"""Metadata schema + classification tests (Story 2.4 AC2). Pure."""

import pytest
from ikip_docproc.metadata import (
    DocumentMetadata,
    DocumentType,
    build_metadata,
    classify_document,
    extract_revision,
)
from pydantic import ValidationError


def test_classify_troubleshooting() -> None:
    assert classify_document("See fault code E42 in the diagnostic table.") is (
        DocumentType.troubleshooting
    )


def test_classify_parts_catalog() -> None:
    assert classify_document("Spare part number 12345, bill of materials.") is (
        DocumentType.parts_catalog
    )


def test_classify_unknown() -> None:
    assert classify_document("Nothing recognizable here.") is DocumentType.unknown


def test_extract_revision() -> None:
    assert extract_revision("Document Rev. A2 dated 2026") == "A2"
    assert extract_revision("Revision 2.1") == "2.1"
    assert extract_revision("no revision marker") is None


def test_build_metadata_validates_and_classifies() -> None:
    md = build_metadata(
        title="  Siemens S7-1500 Manual  ",
        text="Installation and operating manual. Rev. B.",
        page_count=120,
        manufacturer="Siemens",
        model="S7-1500",
    )
    assert isinstance(md, DocumentMetadata)
    assert md.title == "Siemens S7-1500 Manual"  # stripped
    assert md.doc_type is DocumentType.manual
    assert md.revision == "B"
    assert md.page_count == 120


def test_metadata_rejects_empty_title() -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(title="")


def test_metadata_rejects_negative_page_count() -> None:
    with pytest.raises(ValidationError):
        DocumentMetadata(title="x", page_count=-1)
