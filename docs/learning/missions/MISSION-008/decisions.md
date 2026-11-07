# MISSION-008 — Decisions

## D1 — Two-stage extraction (PyMuPDF → Docling → Tesseract), not one tool
- **Problem:** "if Docling does PDFs, why also PyMuPDF + Tesseract?"
- **Answer:** different jobs. PyMuPDF = native text layer (fast, $0); Tesseract = OCR scanned images; Docling = rich ML structure/tables (heavy). They compose, they don't duplicate.
- **Choice:** two-stage — PyMuPDF default; OCR only pages with no native text; Docling as the optional richer path.
- **Why here:** industrial manuals are a mix of native + scanned + table-heavy; running OCR/Docling on every page is slow/costly. Stage-gating is the cost control (AC2).
- **Alternative:** Docling-only (simpler, but ~1GB ML on every page; less control).
- **Trade-off:** three tools / more code. Worth it for cost + speed on the common native case.
- **Switch when:** corpora are mostly scanned/complex → lean more on Docling; or if simplicity outweighs cost → Docling-only.

## D2 — Engines optional + behind ports; orchestration pure
- **Choice:** `NativeExtractor`/`OcrEngine` ports; PyMuPDF/Tesseract/Docling in an `extraction`/`docling` extra; pipeline+quality are engine-free.
- **Why here:** keeps the fast CI job engine-free (no 1GB install), logic unit-testable with fakes, engines swappable (e.g. Azure Document Intelligence as a paid `OcrEngine`). Same pattern as Dagster.

## D3 — Heuristic quality score; `needs_ocr` by sparse text
- **Choice:** score = f(amount of text, printable-char ratio); `needs_ocr` when native text < ~20 chars.
- **Why here:** a cheap, robust signal to (a) route to OCR and (b) flag garbage for review (AC4). Not ML; tunable thresholds.
- **Trade-off:** heuristics misjudge edge cases; acceptable as a first filter.

## D4 — Tables recorded by page/bbox (content later)
- **Choice:** `TableRef(page, bbox)` from PyMuPDF `find_tables()`; actual table *content* extraction is Docling's job (follow-up).
- **Why here:** satisfies "tables captured with page numbers" (AC3) cheaply now; richer parsing can layer on.

## D5 — Azure Document Intelligence as the paid OCR escalation
- Not implemented now, but the `OcrEngine` port is the seam: inject a paid engine for pages Tesseract still can't read. Keeps stage-2 cost opt-in.
