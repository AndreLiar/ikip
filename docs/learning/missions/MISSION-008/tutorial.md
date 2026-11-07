# MISSION-008 — Reproduction tutorial

Add two-stage PDF extraction (native → OCR) with quality scoring.

## Prerequisites
- MISSIONs 001–007; `uv`; for real OCR: `brew install tesseract` (or apt `tesseract-ocr`).

## Steps

1. **Package** `services/document-processing/pyproject.toml` — `name = ikip-docproc`, dep `ikip-common`; `[project.optional-dependencies] extraction = ["pymupdf","pytesseract","pillow"]`, `docling = ["docling>=2.0"]`. Register in root workspace members, `dev` group, `[tool.uv.sources]`; add a root `extraction` dependency-group; add `services/document-processing` to pytest/CI.

2. **Models** `models.py` — `ExtractionMethod(StrEnum)`, `TableRef(page, bbox)`, `PageExtraction(page, text, method, needs_ocr, tables, quality_score, low_quality)`, `DocumentExtraction(pages)` with `.text/.needs_ocr_pages/.low_quality_pages`.

3. **Quality** `quality.py` — `score_page(text)` (length + printable ratio), `needs_ocr(text)` (sparse → True), `is_low_quality(score)`.

4. **Pipeline** `pipeline.py` — ports `NativeExtractor`/`OcrEngine`; `extract_document(pdf, *, native, ocr=None)`: stage-1 native; for `needs_ocr` pages call `ocr.ocr_page`; score + flag each page.

5. **Engines** `engines.py` (lazy imports) — `PyMuPDFExtractor` (`pymupdf.open(stream=...)`, `page.get_text("text")`, `page.find_tables()`), `TesseractOcrEngine` (render page `get_pixmap(dpi)` → PIL → `pytesseract.image_to_string`), `DoclingExtractor` (optional).

6. **Tests**
   ```bash
   uv run pytest apps packages services -q        # quality+pipeline run; engine tests skip
   uv run --group extraction pytest services/document-processing/tests/test_engines.py -q  # 2 passed
   ```

7. **See it two-stage** (optional, needs tesseract)
   ```python
   # build a 2-page PDF (native + image), then:
   from ikip_docproc import extract_document
   from ikip_docproc.engines import PyMuPDFExtractor, TesseractOcrEngine
   res = extract_document(pdf, native=PyMuPDFExtractor(), ocr=TesseractOcrEngine())
   # page 1 method=native, page 2 method=ocr
   ```

## Common mistakes
- **Pulling 1GB into CI** → keep engines in the `extraction`/`docling` extras; core logic must not import them.
- **OCR on every page** → only OCR `needs_ocr` pages (cost control).
- **Losing page numbers** → every `PageExtraction` carries its 1-based page.
- **No tesseract binary** → `pytesseract` needs the system `tesseract` installed.
- **Trusting empty extraction** → score quality + flag; route empties to OCR.

## Recovery
Additive; revert branch/commit. No data touched.
