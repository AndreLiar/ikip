# MISSION-022 — Real PDF extraction adapter (wire the TextExtractor seam)

**Mode:** Autonome (adapter behind an existing Protocol) + knowledge transfer.
**Objective:** swap the text-first curation path to **real PDF extraction** (PyMuPDF native → Tesseract OCR) for PDF artifacts, with zero change to the curation/versioning seam.
**Maps to:** Story 2.3 (two-stage extraction). Builds on MISSION-021 (`curate_document` + `TextExtractor` Protocol).

## What was built
- **`ikip_docproc/engines.py` `PdfExtractor(ocr=True)`** — a `TextExtractor` adapter wrapping the two-stage `extract_document` (PyMuPDF native layer → Tesseract OCR on empty/sparse pages). Returns a `DocumentExtraction` (`.text`, `.pages`). Heavy deps lazy-imported (the `extraction` group).
- **`ikip_docproc/curation.py` auto-detect** — when no extractor is injected and the artifact looks like a PDF (`%PDF-` magic bytes or a PDF content-type), curation builds `PdfExtractor()` lazily; text-first otherwise. An injected extractor always wins (tests inject fakes / native-only).

So `curate_document` / `curate_and_version` / the Dagster `document_versions` asset now read real PDFs with **no change** — the Protocol seam swapped the engine.

## Acceptance (self-set)
1. A real PDF is auto-detected and its text layer extracted via PyMuPDF. — **[verified]** (`test_pdf_extraction.py`, builds a real PDF with PyMuPDF; gated on the `extraction` group)
2. Native-only mode works without Tesseract. — **[verified]** (`PdfExtractor(ocr=False)`)
3. Heavy engines stay lazy; text-first unaffected; no regression. — **[verified]** (151 passed, 35 skipped; ruff/format OK)

## Scoped out
- OCR path exercised against a scanned (image-only) PDF needs an image fixture + the `tesseract` binary — deferred; the wiring is there (`ocr=True` default routes sparse pages to Tesseract).
- Docling richer-structure path (`DoclingExtractor`) remains optional/unused.

## Deliverables
- `services/document-processing/src/ikip_docproc/engines.py` (`PdfExtractor`).
- `services/document-processing/src/ikip_docproc/curation.py` (PDF auto-detect).
- `services/document-processing/tests/test_pdf_extraction.py`.

## Concepts
Reuses [pdf-extraction](../../concepts/pdf-extraction.md) (two-stage native→OCR, quality scoring). Follows [MISSION-021](../MISSION-021/mission.md) (curation seam).
