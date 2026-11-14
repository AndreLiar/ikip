"""Docling-as-a-service extractor (optional, richer PDF path — ADR 0021).

A `TextExtractor` adapter that talks to a **docling-serve** container over HTTP instead
of running Docling in-process. The container holds Docling's ~1 GB of ML models; this
adapter only needs an HTTP client, so the app process stays light and CI stays fast.

Why remote (vs the `docling` python lib): the user runs the engine as a Docker image
on their machine (`infrastructure/docker/docker-compose.yml`), so extraction scales/updates
independently of the app and can later move to a GPU host without touching this code.

It POSTs the raw bytes to `POST /v1/convert/file` asking for the structured
`json_content` (a DoclingDocument), then maps that onto our engine-free
`DocumentExtraction`, preserving **page references, bounding boxes and table locations** —
the whole reason to prefer Docling over the native PyMuPDF path for complex layouts.

Opt-in, behind the same seam as PyMuPDF (`curate_document`'s `_default_pdf_extractor`):
    IKIP_PDF_EXTRACTOR=docling  IKIP_DOCLING_URL=http://localhost:5001
"""

from __future__ import annotations

from typing import Any

from ikip_docproc.models import (
    DocumentExtraction,
    ExtractionMethod,
    PageExtraction,
    TableRef,
    TextRegion,
)

_SUCCESS = {"success", "partial_success"}


class DoclingConversionError(RuntimeError):
    """docling-serve reached but did not return a usable conversion."""


# OOXML office files are ZIP containers (PK\x03\x04) told apart by an internal folder.
_OFFICE_BY_MEMBER = (
    (
        "word/",
        "document.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    (
        "ppt/",
        "document.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    ("xl/", "document.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
)


def _upload_for(data: bytes) -> tuple[str, str]:
    """Pick the upload (filename, content-type) from the artifact's magic bytes so
    docling-serve selects the right parser (a .docx sent as application/pdf is misparsed).
    PDFs → pdf; ZIP-based Office → docx/pptx/xlsx by member; HTML → html; else best-effort pdf."""
    if data[:5].startswith(b"%PDF"):
        return "document.pdf", "application/pdf"
    if data[:4] == b"PK\x03\x04":
        import io
        import zipfile

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            names = []
        for prefix, filename, ctype in _OFFICE_BY_MEMBER:
            if any(n.startswith(prefix) for n in names):
                return filename, ctype
        return "document.zip", "application/zip"
    head = data[:64].lstrip().lower()
    if head.startswith((b"<!doctype html", b"<html")):
        return "document.html", "text/html"
    return "document.pdf", "application/pdf"


def _bbox(prov: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    """First provenance box as (l, t, r, b). Docling emits BOTTOMLEFT-origin PDF
    coordinates; we keep them verbatim — downstream only uses the box to locate a
    region/table on a page, not to re-render it."""
    if not prov:
        return None
    b = prov[0].get("bbox") or {}
    if not b:
        return None
    return (
        float(b.get("l", 0.0)),
        float(b.get("t", 0.0)),
        float(b.get("r", 0.0)),
        float(b.get("b", 0.0)),
    )


def _page_no(prov: list[dict[str, Any]]) -> int:
    return int(prov[0].get("page_no", 1)) if prov else 1


def docling_document_to_extraction(doc: dict[str, Any]) -> DocumentExtraction:
    """Map a DoclingDocument (the `json_content` payload) onto `DocumentExtraction`.

    Pure (no HTTP) so it is unit-testable against a captured fixture. Text items are
    grouped by page in reading order; each becomes a `TextRegion`; `tables` become
    `TableRef`s located by page + box."""
    # Text is captured per page regardless of provenance; a TextRegion is only added when the
    # item has a bbox. Paginated PDFs carry prov+bbox (→ regions); non-paginated Office docs
    # (docx/pptx/xlsx) carry text with prov=[] (→ text only, page 1), which must NOT be dropped.
    texts_by_page: dict[int, list[str]] = {}
    regions_by_page: dict[int, list[TextRegion]] = {}
    for item in doc.get("texts") or []:
        prov = item.get("prov") or []
        page = _page_no(prov)
        text = item.get("text", "")
        if text:
            texts_by_page.setdefault(page, []).append(text)
        box = _bbox(prov)
        if box is not None:
            regions_by_page.setdefault(page, []).append(TextRegion(page=page, text=text, bbox=box))

    tables_by_page: dict[int, list[TableRef]] = {}
    for table in doc.get("tables") or []:
        prov = table.get("prov") or []
        if not prov:
            continue
        page = _page_no(prov)
        tables_by_page.setdefault(page, []).append(TableRef(page=page, bbox=_bbox(prov)))

    page_meta = doc.get("pages") or {}
    page_numbers = sorted(
        {int(p) for p in page_meta}
        | set(texts_by_page)
        | set(regions_by_page)
        | set(tables_by_page)
    ) or [1]

    pages = [
        PageExtraction(
            page=page,
            text="\n".join(texts_by_page.get(page, [])),
            method=ExtractionMethod.docling,
            regions=regions_by_page.get(page, []),
            tables=tables_by_page.get(page, []),
        )
        for page in page_numbers
    ]
    return DocumentExtraction(pages=pages)


class DoclingRemoteExtractor:
    """`TextExtractor` backed by a docling-serve container."""

    def __init__(
        self,
        base_url: str = "http://localhost:5001",
        *,
        timeout: float = 300.0,
        do_ocr: bool = True,
        table_mode: str = "accurate",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._do_ocr = do_ocr
        self._table_mode = table_mode

    def extract(self, data: bytes) -> DocumentExtraction:
        import httpx  # lazy: only when Docling is actually selected (`--group docling-serve`)

        filename, content_type = _upload_for(data)
        resp = httpx.post(
            f"{self._base_url}/v1/convert/file",
            files={"files": (filename, data, content_type)},
            data={
                "to_formats": ["json"],  # httpx repeats the key for a list value
                "do_ocr": "true" if self._do_ocr else "false",
                "do_table_structure": "true",
                "table_mode": self._table_mode,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status not in _SUCCESS:
            errors = payload.get("errors")
            raise DoclingConversionError(f"docling-serve status={status!r}: {errors}")
        doc = (payload.get("document") or {}).get("json_content")
        if not doc:
            raise DoclingConversionError(
                "docling-serve returned no json_content (request to_formats=json)"
            )
        return docling_document_to_extraction(doc)
