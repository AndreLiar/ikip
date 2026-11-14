# MISSION-042 — Per-page extraction routing + Indra OCR, benchmarked on real manuals

- **Mode:** Guidé (architecture decision — routing granularity + OCR engine) → Autonome build
- **Date:** 2026-11-14
- **Branch:** `feat/docling-serve-extractor`
- **Decision record:** [ADR 0024](../../adr/0024-per-page-extraction-routing-and-indra-ocr.md)

## Objective
Make extraction **detect, per page, which engine it needs** — PyMuPDF for clean digital text,
OCR for scanned pages, Docling for tables/rich layout — and evaluate **Indra OCR** (Datalab)
as a faster replacement for Tesseract. Then benchmark all of it on real NTRS manuals.

## What was built
- `routing.py` — `classify_page` (tables→layout, sparse-text→OCR, else→native), `HybridPdfExtractor`
  (`TextExtractor`), `DoclingLayoutEngine` (per-page docling-serve), `extract_document_hybrid`
  (stage-1 once, re-route each page, graceful degradation).
- `engines.IndraOcrEngine` — `OcrEngine` seam (`ocr_page -> str`), ONNX CPU, lazy-loaded + cached.
- `curation._default_ocr_engine` (Indra default, Tesseract fallback) + `_default_pdf_extractor`
  gains `hybrid`/`auto`; `PdfExtractor` accepts an injected `ocr_engine`.
- Dep group `indra = ["indra-ocr>=1.1"]`.
- `scripts/compare_extractors.py` — 4-way benchmark (pymupdf+tesseract / pymupdf+indra / docling /
  hybrid) on real R2 docs, clipped to K pages; captures text yield, tables, OCR/layout pages,
  time, token agreement, and the hybrid route distribution.

## Indra OCR — grounded analysis (from the repo, not the blog)
- Code **Apache-2.0**; **weights modified OpenRAIL-M** (research/personal/<$20M, not competitive
  with their API) → **not** in `is_license_allowed`: fine for this thesis, **blocker for commercial
  SaaS**. ~1M-param recognizer, ~76 MB, ONNX **CPU-only**, 80+ languages, reads PDFs + images,
  outputs markdown/JSON with boxes/blocks/reading-order. `pip install indra-ocr`.

## Benchmark results (real NTRS manuals — full report: `eval-results/extractor_benchmark_report.md`)
Run A (4 digital docs, avg/doc): pymupdf **8258 c / 1.1 s** · indra **8258 c / 1.0 s** ·
docling **8342 c / 17.7 s** · hybrid **8246 c / 5.7 s**. Hybrid routes: **81% native / 18% layout /
0% OCR**. Run B (1 real scanned doc, 1 OCR page): tesseract **1511 c / 4.2 s** vs indra
**1411 c / 2.6 s** (≈1.1 s warm); docling 1343 c / 14.4 s.

**Findings (honest):** NTRS PDFs are mostly clean single-column digital text (even old scans have
text layers) → PyMuPDF already wins on quality-per-second; scanned pages are rare. Indra ≈ Tesseract
on accuracy (small sample) but **faster** → adopt for speed, not a proven accuracy gap. Docling is
5–20× slower and didn't clearly win on single-column prose. **The hybrid router is the right
default**: native speed on the common case, Docling/OCR only on the pages that need them. Docling/
Indra should matter much more on real industrial manuals (multi-column, dense tables, scans) — re-run
the benchmark there before locking thresholds.

## Acceptance — all [verified]
- `ruff` clean; docproc suite **53 passed / 4 skipped** (default PyMuPDF path intact).
- Routing unit tests (fake engines) + Indra adapter unit test green; **live Indra OCR** passed
  (`IKIP_INDRA_LIVE=1`, ~1.8 s). Benchmark ran end-to-end on real R2 docs (both runs).

## See also
- [ADR 0024](../../adr/0024-per-page-extraction-routing-and-indra-ocr.md) (decisions + license caveat)
- MISSION-041 (Docling container wiring) · concept `docs/learning/concepts/pdf-extraction.md`
