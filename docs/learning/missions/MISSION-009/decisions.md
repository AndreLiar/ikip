# MISSION-009 — Decisions

## D1 — Pydantic for records, Pandera for frames (both, not either)
- **Choice:** `DocumentMetadata` (Pydantic) validates the metadata record; a Pandera `DataFrameSchema` validates the per-page quality frame.
- **Why here:** they validate different shapes — one object vs many tabular rows. Pydantic catches bad metadata at construction; Pandera runs row-wise schema+data-quality checks (page>0, score in 0..1, not all-empty).
- **Alternative:** force everything through Pydantic (awkward for row-wise/tabular checks) or hand-rolled asserts.
- **Trade-off:** two libraries; both are light and standard.

## D2 — Validation returns a report; never raises
- **Choice:** `validate_pages` → `ValidationReport(ok, errors, empty_pages, low_quality_pages)`; `as_error_info()` for the job.
- **Why here:** the pipeline must **record** failures on `ingestion_job.error_info` and route to failed/dead-letter (AC4, Story 2.6), not crash. A report is inspectable and storable.
- **Alternative:** raise exceptions.
- **Trade-off:** callers must check `.ok` (explicit, which we want).

## D3 — Conservative cleaning that preserves structure
- **Choice:** de-hyphenate line breaks, NFC + strip control chars, collapse whitespace, keep headings/paragraphs (`iter_blocks`).
- **Why here:** downstream chunking (Epic 3) needs section structure; flattening to one blob would destroy citations' context. Normalize noise, not meaning.
- **Trade-off:** heading detection is heuristic; can misclassify. Acceptable first pass.

## D4 — Heuristic classification (ML later, same seam)
- **Choice:** keyword signals → DocumentType.
- **Why here:** cheap, explainable, good enough for the MVP corpus; `classify_document` is the seam to swap in a model.

## D5 — Regex revision extraction: validate negative cases
- **Bug:** `rev(ision)?\s*(\w+)` matched "revision **marker**".
- **Fix:** require a separator + a token that is short-alpha (A, B2) OR contains a digit; reject long all-alpha words.
- **Lesson:** always test extraction regexes against inputs that should NOT match.
