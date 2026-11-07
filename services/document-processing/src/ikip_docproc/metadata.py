"""Document metadata schema + classification (Story 2.4 AC2). Pydantic = the schema
contract; classification is a pure heuristic over curated text.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class DocumentType(StrEnum):
    manual = "manual"
    maintenance_procedure = "maintenance_procedure"
    troubleshooting = "troubleshooting"
    parts_catalog = "parts_catalog"
    specification = "specification"
    unknown = "unknown"


class DocumentMetadata(BaseModel):
    """Normalized metadata attached to a curated document (validated contract)."""

    title: str = Field(min_length=1, max_length=512)
    doc_type: DocumentType = DocumentType.unknown
    manufacturer: str | None = Field(default=None, max_length=256)
    model: str | None = Field(default=None, max_length=256)
    revision: str | None = Field(default=None, max_length=64)
    language: str = Field(default="en", max_length=8)
    page_count: int = Field(ge=0, default=0)

    @field_validator("title", "manufacturer", "model", "revision")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


# Keyword signals per type (lowercased). First strong match wins; order matters.
_TYPE_SIGNALS: list[tuple[DocumentType, tuple[str, ...]]] = [
    (DocumentType.troubleshooting, ("fault code", "troubleshoot", "error code", "diagnostic")),
    (
        DocumentType.maintenance_procedure,
        ("maintenance procedure", "service procedure", "lubricat"),
    ),
    (DocumentType.parts_catalog, ("spare part", "parts list", "part number", "bill of materials")),
    (DocumentType.specification, ("technical specification", "rated voltage", "datasheet")),
    (DocumentType.manual, ("installation", "operating manual", "user manual", "operation")),
]

# Require "rev"/"revision" + separator, then a revision token that is EITHER
# short-alpha (e.g. "A", "B2"... up to 2 chars) OR contains a digit — so a
# following dictionary word like "marker" (long, all-alpha) does not match.
_REVISION_RE = re.compile(
    r"\brev(?:ision)?\.?\s+("
    r"(?:[A-Z]{1,2}\d*)"  # A, B, AB, A2, B12 ...
    r"|(?:[A-Z0-9][A-Z0-9.\-]*\d[A-Z0-9.\-]*)"  # anything containing a digit, e.g. 2.1
    r")\b",
    re.IGNORECASE,
)


def classify_document(text: str) -> DocumentType:
    """Heuristic document-type classification from curated text."""
    low = text.lower()
    for doc_type, signals in _TYPE_SIGNALS:
        if any(sig in low for sig in signals):
            return doc_type
    return DocumentType.unknown


def extract_revision(text: str) -> str | None:
    """Best-effort revision extraction (e.g. 'Rev. A', 'Revision 2.1')."""
    m = _REVISION_RE.search(text)
    return m.group(1) if m else None


def build_metadata(
    *,
    title: str,
    text: str,
    page_count: int,
    manufacturer: str | None = None,
    model: str | None = None,
    language: str = "en",
) -> DocumentMetadata:
    """Assemble + validate normalized metadata from curated text + known fields."""
    return DocumentMetadata(
        title=title,
        doc_type=classify_document(text),
        manufacturer=manufacturer,
        model=model,
        revision=extract_revision(text),
        language=language,
        page_count=page_count,
    )
