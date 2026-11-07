"""Content validation (Story 2.4 AC3/AC4).

Two kinds of validation:
  - Pydantic (`DocumentMetadata`) already validates the metadata contract on build.
  - Pandera validates the **tabular** per-page quality frame (schema + data-quality
    checks over the extracted pages), e.g. page numbers present/positive, no page
    is entirely empty, quality scores in range.

`validate_pages` returns a structured `ValidationReport` so failures can be
recorded against the ingestion job (AC4) rather than raising opaque errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pandera.pandas as pa

from ikip_docproc.models import DocumentExtraction

# Schema for the per-page quality frame.
_PAGE_SCHEMA = pa.DataFrameSchema(
    {
        "page": pa.Column(int, checks=pa.Check.gt(0), nullable=False),
        "char_count": pa.Column(int, checks=pa.Check.ge(0), nullable=False),
        "quality_score": pa.Column(float, checks=pa.Check.in_range(0.0, 1.0), nullable=False),
    },
    strict=False,
    coerce=True,
)


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    # Quick quality summary to store on the ingestion job / data-quality report.
    page_count: int = 0
    low_quality_pages: list[int] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)

    def as_error_info(self) -> dict:
        return {
            "errors": self.errors,
            "low_quality_pages": self.low_quality_pages,
            "empty_pages": self.empty_pages,
        }


def _frame(doc: DocumentExtraction) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "page": [p.page for p in doc.pages],
            "char_count": [len(p.text) for p in doc.pages],
            "quality_score": [p.quality_score for p in doc.pages],
        }
    )


def validate_pages(doc: DocumentExtraction) -> ValidationReport:
    """Validate the extracted pages; never raises — returns a report."""
    errors: list[str] = []
    empty_pages = [p.page for p in doc.pages if not p.text.strip()]
    low_quality = list(doc.low_quality_pages)

    if not doc.pages:
        errors.append("document has no pages")

    try:
        _PAGE_SCHEMA.validate(_frame(doc), lazy=True)
    except pa.errors.SchemaErrors as e:
        errors.append(f"schema validation failed: {len(e.failure_cases)} case(s)")

    # Data-quality rule: a document that is *entirely* empty/low-quality is invalid.
    if doc.pages and len(empty_pages) == len(doc.pages):
        errors.append("all pages are empty")

    return ValidationReport(
        ok=not errors,
        errors=errors,
        page_count=len(doc.pages),
        low_quality_pages=low_quality,
        empty_pages=empty_pages,
    )
