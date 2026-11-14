# 0024. Per-page extraction routing (PyMuPDF / OCR / Docling) and Indra as the default OCR engine

- **Status:** Accepted
- **Date:** 2026-11-14
- **Deciders:** Architect, PM
- **Related:** Epic 2 (Story 2.3 extraction) · [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (reuse behind ports) · [ADR 0012] local-first/cost control · Story 6.5 (licensing gate) · MISSION-041, MISSION-042

## Context
Extraction was a two-stage `PdfExtractor`: PyMuPDF native text → Tesseract OCR on pages with no text layer. Docling was listed in the stack but unused; MISSION-041 wired it as an opt-in whole-document extractor behind the `TextExtractor` port. Two questions remained:

1. **Which engine per document?** Forcing one engine on a whole document is wrong: most pages are clean digital text (PyMuPDF is best + ~free), some are scanned (need OCR), some are dense tables/multi-column (Docling reconstructs them far better). The pipeline should **detect per page** what each page needs.
2. **Is Tesseract the right OCR engine?** Indra OCR (Datalab, 2026) — a ~1M-param ONNX CPU model — claims to be much faster and more accurate, with reading-order/table output.

We benchmarked all four pipelines on real public-domain NTRS manuals (see `eval-results/extractor_benchmark_report.md`).

## Decision
**1. Route each page to the engine that fits, behind the existing ports.** A `HybridPdfExtractor` (`routing.py`) runs PyMuPDF stage-1 once, then classifies each page from cheap signals and re-routes:
- **tables detected → Docling** (per-page, 1-page slice to docling-serve — cost is paid only for pages that need it);
- **no/sparse native text → OCR engine**;
- **else → native PyMuPDF text** (fast, ~free).
It is itself a `TextExtractor`, selected with `IKIP_PDF_EXTRACTOR=hybrid`. Graceful degradation: if an engine isn't provided/reachable, the page keeps its native result (never worse than native-only).

**2. Indra becomes the default OCR engine behind the `OcrEngine` seam** (`IndraOcrEngine`, `IKIP_OCR_ENGINE=indra`, default). It replaces Tesseract as stage-2 without touching the pipeline; Tesseract stays available (`IKIP_OCR_ENGINE=tesseract`) and is the automatic fallback if the `indra` group isn't installed.

**3. Docling handles rich layout/tables** (whole-doc via `IKIP_PDF_EXTRACTOR=docling`, or per-page inside the hybrid router).

## Licensing caveat (Story 6.5) — explicit
Indra's **code is Apache-2.0** but its **model weights are a modified OpenRAIL-M**: *free for research, personal use, and startups under $20M funding/revenue, and may not be used competitively with Datalab's API*. This is **not** in `is_license_allowed` (public-domain/cc0/cc-by[-sa]/mit/apache-2.0/manufacturer-authorized). **Acceptable for this thesis/portfolio; a blocker for a commercial SaaS** without a commercial license from Datalab. For a commercial launch, fall back to Tesseract (safe) or license Indra. This caveat is encoded in the `IndraOcrEngine` docstring and the dependency-group comments.

## What the benchmark showed (real NTRS manuals)
- NTRS PDFs are **mostly clean, single-column digital text with embedded text layers** — even most old scans. PyMuPDF native already extracts them fully and fast; OCR fired on only a small minority.
- **Indra vs Tesseract (on the one genuinely scanned doc):** comparable text yield (1411 vs 1511 chars on 1 OCR page), **Indra ~1.6× faster** (2.6 s vs 4.2 s cold, ~1.1 s warm). Indra's large accuracy advantage did **not** show on this small sample — adopt it for **speed**, not on a claimed accuracy gap.
- **Docling:** comparable char yield but **5–20× slower** (8–24 s/doc vs ~1 s), and did not clearly win on these single-column reports — its strength (complex tables/multi-column) wasn't stressed by this corpus.
- **Hybrid router:** near-native speed where no page needs OCR/layout (docs ran in ~1 s instead of Docling's 8–22 s) while still sending the table pages to Docling. On this corpus it routed **81% native / 18% layout / 0% OCR**.

## Consequences
**Positive**
- Each page gets the best-fit engine; cost (Docling CPU, OCR) is paid only where it helps.
- Everything stays behind `TextExtractor`/`OcrEngine`/`LayoutEngine` ports (ADR 0021) — engines are swappable by env, no pipeline change; `curate_document` only ever sees a `DocumentExtraction`.
- Faster OCR (Indra) and a documented, reversible OCR choice.

**Negative / watch**
- Indra weights carry a restricted license — flagged; not for commercial SaaS as-is.
- Per-page Docling = one HTTP call per table page; fine for the rare layout page, watch it on table-heavy corpora (batch/whole-doc Docling may then be cheaper).
- The benefit of Docling/Indra is **corpus-dependent**: marginal on clean NTRS text, expected to matter much more on real industrial manuals (multi-column, dense tables, scanned plates). Re-run the benchmark on that corpus before locking thresholds.

## Alternatives considered
- **One engine per document** (simpler) — rejected: wastes Docling cost on text pages, or loses tables on native-only.
- **Keep Tesseract** — viable and license-safe; kept as the fallback. Indra chosen as default for speed.
- **In-process `docling` lib / in-process Indra** — Docling stays containerized (MISSION-041); Indra is light enough (~76 MB ONNX, CPU) to run in-process.
