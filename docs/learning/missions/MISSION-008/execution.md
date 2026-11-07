# MISSION-008 — Execution log

Labels: `[verified]` = run with observed output · `[proposed]` = not run here.

## Steps
1. **Tool-choice decision** `[verified]` — clarified PyMuPDF vs Tesseract vs Docling; chose two-stage (user).
2. **Package `services/document-processing`** `[verified]` — core deps ikip-common; `extraction`/`docling` extras for the heavy engines. Registered in uv workspace + dev group + root `extraction` group; added to pytest/CI.
3. **Core (engine-free)** `[verified]` — `models.py` (PageExtraction/DocumentExtraction/TableRef/ExtractionMethod), `quality.py` (score_page, needs_ocr, is_low_quality), `pipeline.py` (`extract_document` two-stage).
4. **Engine adapters** `[verified-authored]` — `engines.py`: PyMuPDFExtractor (native + find_tables + needs_ocr), TesseractOcrEngine (render + OCR), DoclingExtractor (optional). Lazy imports.
5. **Tests** `[verified]` — quality (4) + pipeline (3) hermetic in CI; engines (2) real PyMuPDF via `--group extraction`.
6. **CI isolation of engines** `[verified]` — `pymupdf installed: False` in dev env; fast suite 34 passed, 11 skipped.
7. **Real PyMuPDF** `[verified]` — `--group extraction` → 2 passed (native text "E42" + page ref; empty page flagged needs_ocr).
8. **End-to-end two-stage** `[verified]` — built a 2-page PDF (native + image page); pipeline: page1 method=native, page2 method=ocr ("SCANNED LINE ABC123" recovered by Tesseract 5.5.1). Cost control confirmed: OCR ran only on the image page.
9. **ruff** `[verified]` — import-sort fix; lint+format green.

## Validation summary
- Quality + pipeline hermetic tests pass `[verified]`
- Real PyMuPDF native extraction + page refs `[verified]`
- Two-stage native→OCR end-to-end `[verified]`
- Engines excluded from fast CI (34 passed, 11 skipped) `[verified]`
- CI (validate + db-tests) → `[proposed]` (observed on PR)

## Rollback
Additive (new service package + extraction group). Revert branch/commit. No data touched (tests build in-memory PDFs).

## Follow-up
- Docling table-content extraction with page-accurate mapping.
- Azure Document Intelligence as a paid `OcrEngine` escalation for stubborn pages.
- Wire extraction as a Dagster asset downstream of ingestion (store curated text).
