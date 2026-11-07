# Concept — PDF extraction & OCR (two-stage, cost-controlled)

_Write-once concept note. First used by [MISSION-008](../missions/MISSION-008/mission.md). Reused by any document-parsing work._

## The core problem: not all PDFs are the same
A PDF is either:
- **Native-digital** — the text is *encoded* in the file (a text layer). You just read it. Fast, exact, free.
- **Scanned** — the page is an *image* of text; there is no text layer. You must **OCR** it (recognize characters from pixels). Slower, imperfect, costs compute.

Industrial manuals are a mix, and full of **tables** (specs, fault codes, parts). So extraction has three concerns, handled by three tools — **they are not interchangeable**:

| Tool | Job |
|---|---|
| **PyMuPDF** (`fitz`) | read the **native text layer** + detect table locations; fast, $0 |
| **Tesseract** | **OCR** a page image → text; $0 (needs the `tesseract` system binary) |
| **Docling** | understand **rich structure** (sections, tables) via ML; heavy (~1GB models) |

## The two-stage strategy (why, and the cost win)
Running OCR (or Docling) on *every* page is slow and expensive. Instead:

1. **Stage 1 — PyMuPDF (default, $0):** read each page's native text. If a page has **no/sparse text**, it's (probably) scanned → flag `needs_ocr`.
2. **Stage 2 — OCR only the flagged pages:** Tesseract ($0) by default; a **paid engine (Azure Document Intelligence)** can be injected for pages that still fail — same `OcrEngine` port.

So the expensive path runs **only where needed**. This is IKIP's cost-control decision (Story 2.3 AC2) and why all three tools coexist rather than "just Docling everywhere".

## Keep engines optional; make the orchestration pure
The heavy engines (PyMuPDF/Tesseract/Docling) are an **optional dependency** (`extraction`/`docling` extras) and live behind ports (`NativeExtractor`, `OcrEngine`). The **orchestration + quality scoring are pure Python**, tested in CI with fakes — no 1GB install in the fast job (same pattern as Dagster). Real PyMuPDF/OCR are verified via `uv run --group extraction`.

```
models.py / pipeline.py / quality.py   # pure, CI-tested, engine-free
engines.py                             # PyMuPDF/Tesseract/Docling adapters (lazy imports)
```

## Quality scoring & flagging (AC4)
Each page gets a 0..1 score from *how much* text and *how clean* it is (ratio of printable, non-space chars). Garbled OCR / binary noise scores low → the page is **flagged** for review. A page with almost no native text is routed to OCR (the `needs_ocr` decision). Thresholds are tunable heuristics, not perfection.

## Page references & tables (AC1/AC3)
- Every `PageExtraction` keeps its **1-based page number** → citations resolve to the right page (FR16/FR23).
- Tables are recorded by **page (+ bbox)** via PyMuPDF `find_tables()`; Docling is the richer option for actual table *content*. At minimum we know *where* tables are.

## Rules to remember
1. Try native text first (PyMuPDF). OCR is the fallback, not the default.
2. OCR only pages that need it — that's the cost control.
3. Keep page numbers on everything (citations depend on them).
4. Score extraction quality and flag bad pages; don't trust silent empties.
5. Engines stay optional/behind ports so CI and the core stay light.

## Related
- [object-storage](./object-storage.md) (raw PDFs live in R2) · [dagster-orchestration](./dagster-orchestration.md) (extraction runs as a pipeline step).
- Story 2.3 (this) · two-stage cost strategy in the brief / [ADR 0014](../../adr/0014-cloudflare-r2-object-storage.md) context.
