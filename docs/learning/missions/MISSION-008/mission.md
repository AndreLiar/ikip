# MISSION-008 — PDF extraction with OCR fallback (Epic 2, Story 2.3)

**Mode:** Guidé (tool-choice decision: why PyMuPDF+Tesseract+Docling) → Autonome (impl) + knowledge transfer.
**Objective:** extract native PDF text with page references, route only scanned pages to OCR, detect tables, and score quality — cost-controlled and CI-fast.
**Maps to:** Epic 2 / Story 2.3.

## Tool-choice decision (user question: "why 3 tools if Docling does it all?")
They do **different jobs** — PyMuPDF reads the native text layer (fast, $0), Tesseract OCRs scanned pages, Docling understands rich structure/tables (heavy ML). Decision: **two-stage** (PyMuPDF default → Docling for structure → Tesseract for scanned), so the expensive path runs only when needed. See [decisions.md](./decisions.md) D1 and the concept [pdf-extraction](../../concepts/pdf-extraction.md).

## Acceptance criteria
1. Native PDFs extracted with page references (PyMuPDF). — **[verified]** (real PyMuPDF test: text + page 1 ref)
2. Scanned/low-quality pages routed to OCR, two-stage cost control. — **[verified]** (end-to-end: native page native, image page → Tesseract OCR)
3. Tables/diagrams captured with page numbers. — **[verified]** (`TableRef(page, bbox)` via PyMuPDF `find_tables`)
4. Extraction quality scored; low-quality flagged. — **[verified]** (quality heuristic; empty/garbled flagged)

## Deliverables
- `services/document-processing/` (uv member): `models.py`, `quality.py`, `pipeline.py` (pure, CI-tested); `engines.py` (PyMuPDF/Tesseract/Docling adapters, optional `extraction`/`docling` extras).
- Tests: `test_quality.py`, `test_pipeline.py` (hermetic, CI); `test_engines.py` (real PyMuPDF, `--group extraction`).
- Root `extraction` dependency-group; `services/document-processing` in workspace/CI.
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [pdf-extraction](../../concepts/pdf-extraction.md) (native vs scanned, two-stage, quality, keeping engines optional). Reuses [object-storage](../../concepts/object-storage.md), [dagster-orchestration](../../concepts/dagster-orchestration.md).
