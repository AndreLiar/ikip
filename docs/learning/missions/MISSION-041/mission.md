# MISSION-041 — Docling as a containerized, opt-in PDF extractor (behind the port)

- **Mode:** Autonome (knowledge transfer mandatory)
- **Date:** 2026-11-14
- **Branch:** `feat/docling-serve-extractor`

## Objective
The architecture listed "PyMuPDF + Docling" for PDF processing, but only PyMuPDF→Tesseract
was implemented. Add **Docling** as a real, selectable extractor **running as a Docker image
on the dev machine** — without coupling the app to Docling's ~1 GB of ML models and without
changing the default local-first path.

## Why this shape (not the `docling` python lib in-process)
- Docling in-process pulls heavy ML models into **every** app/worker process and into CI.
- The user explicitly wants a **Docker image running on the machine** → run the official
  **`docling-serve`** image; the app talks to it over HTTP. Models live in the container;
  the app only needs an HTTP client.
- The `TextExtractor` **port** (ADR 0021) already existed (PyMuPDF is one adapter) → Docling
  is a second adapter behind the same seam. **Default stays PyMuPDF** ($0, no container);
  Docling is opt-in via `IKIP_PDF_EXTRACTOR=docling`.

## What was built
- `infrastructure/docker/docker-compose.yml` — `docling` service (`docling-serve-cpu`,
  port 5001, UI enabled, healthcheck on `/health`).
- `services/document-processing/src/ikip_docproc/docling_client.py`
  - `DoclingRemoteExtractor` — `TextExtractor` that POSTs bytes to `POST /v1/convert/file`
    (`to_formats=json`) and maps the returned **DoclingDocument** onto `DocumentExtraction`.
  - `docling_document_to_extraction(doc)` — pure mapper: `texts[].prov[].bbox` → `TextRegion`
    grouped by page, `tables[].prov` → `TableRef`, `pages` → page list. Preserves page refs,
    boxes and table locations (the reason to use Docling for complex layouts).
  - `DoclingConversionError` for non-`success`/empty responses.
- `curate_document._default_pdf_extractor()` — selects Docling when `IKIP_PDF_EXTRACTOR=docling`
  (`IKIP_DOCLING_URL`, default `http://localhost:5001`); else PyMuPDF. Lazy imports both.
- `docling-serve` dependency group (root + package) = `httpx` only.
- Tests: `services/document-processing/tests/test_docling_client.py` + fixture captured from a
  real conversion (`tests/fixtures/docling_sample.json`).
- Docs: `docs/architecture.md` PDF-processing row reconciled (candidate → wired, opt-in).

## Acceptance — all [verified]
- `docker compose … up -d docling` → container healthy (`/health` 200 after ~5 s). [verified]
- OpenAPI probed live (`/v1/convert/file`, `ExportDocumentResponse.json_content`). [verified]
- `ruff` clean; adapter unit tests **5 passed, 1 skipped**; full docproc suite **46 passed,
  3 skipped** (default PyMuPDF path intact). [verified]
- **Live roundtrip** (`IKIP_DOCLING_LIVE=1`) against the container → text extracted, 11.7 s. [verified]
- **End-to-end via the seam**: `IKIP_PDF_EXTRACTOR=docling curate_document(pdf)` → 1 page,
  3 regions with real bboxes, curated text correct. [verified]

## See also
- Decisions → `decisions.md` · Reproduction → `tutorial.md`
- Concept: `docs/learning/concepts/pdf-extraction.md` (two-stage PyMuPDF→OCR — the default path)
- ADR 0021 (reuse libraries behind our ports) · ADR 0012 (local-first / cost control)
