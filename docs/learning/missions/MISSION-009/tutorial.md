# MISSION-009 — Reproduction tutorial

Add cleaning, metadata and validation to the document-processing service.

## Prerequisites
- MISSIONs 001–008; `uv`.

## Steps

1. **Dep** — add `pandera[pandas]` to `services/document-processing/pyproject.toml` core deps; `uv sync`.

2. **cleaning.py** — `normalize_unicode` (NFC + strip control chars), `clean_text` (de-hyphenate `(\w)-\n(\w)`, CRLF→LF, collapse spaces, ≤1 blank line), `iter_blocks(text)` → `(kind, content)` with a heading heuristic.

3. **metadata.py** — `DocumentType(StrEnum)`; `DocumentMetadata(BaseModel)` (title required, page_count≥0, strip validator); `classify_document(text)` (keyword signals); `extract_revision(text)` (careful regex — see step 6); `build_metadata(...)`.

4. **validation.py** — Pandera `DataFrameSchema` (page>0, char_count≥0, quality_score in 0..1); `validate_pages(doc)` → `ValidationReport(ok, errors, empty_pages, low_quality_pages)` + `as_error_info()`. Never raise.

5. **Tests** (all pure, run in CI)
   ```bash
   uv run pytest services/document-processing -q
   ```
   Cover: de-hyphenation, heading/paragraph split; classification + Pydantic rejections; Pandera schema + all-empty failure + report.

6. **Regex negative cases** — test that `extract_revision("no revision marker")` is `None` (not "marker"). Require a separator + a token that is short-alpha (A, B2) or contains a digit.

## Common mistakes
- **Regex grabs the next word** → test negative inputs; constrain the token.
- **Flattening structure** → keep headings/paragraphs (`iter_blocks`) for chunking.
- **Pydantic for a DataFrame** (or Pandera for one record) → match the tool to the shape.
- **Raising on invalid content** → return a report so the job can record `error_info`.
- **Over-cleaning** → don't strip `\n`/`\t`; normalize noise only.

## Recovery
Additive; revert branch/commit. No data touched.
