# Concept — Data cleaning, metadata & validation (Pydantic vs Pandera)

_Write-once concept note. First used by [MISSION-009](../missions/MISSION-009/mission.md). Reused wherever we validate data._

## The stage: raw extraction → curated, trustworthy content
After extraction (Story 2.3) the text is *there* but messy: PDF line-break hyphenation, stray control chars, inconsistent whitespace/unicode. Cleaning turns it into **consistent curated text** while **preserving structure** (headings/paragraphs) so downstream chunking (Epic 3) can respect sections. Then we attach **normalized metadata** and **validate** before anything enters the knowledge base.

## Cleaning: conservative normalization
- **De-hyphenate** `mainten-\nance` → `maintenance` (PDFs break words across lines).
- **Unicode NFC** + strip control chars (keep `\n`/`\t`).
- Collapse runs of spaces, trim lines, at most one blank line between blocks.
- Keep paragraph/heading structure (`iter_blocks` tags each block) — don't flatten to one blob.
Rule: normalize *noise*, never destroy *meaning/layout*.

## Metadata: a validated contract + heuristic classification
- **`DocumentMetadata` (Pydantic)** is the **contract**: title required, page_count ≥ 0, length bounds, fields stripped. Building it validates it — bad metadata fails *at construction*.
- **Classification** (`classify_document`) is a pure keyword heuristic → `manual / troubleshooting / parts_catalog / …`. Cheap, good enough as a first pass; ML can replace it later behind the same function.
- Revision extraction is a careful regex (lesson below).

## Pydantic vs Pandera — two validators, two shapes of data
This is the key distinction:

| | **Pydantic** | **Pandera** |
|---|---|---|
| Validates | **objects / records** (one document's metadata, an API body) | **tabular data** (a DataFrame of many rows) |
| Shape | fields of one thing | columns + row-wise checks across many |
| Use here | `DocumentMetadata` contract | per-page quality frame (page>0, char_count≥0, score in 0..1) |
| Failure | `ValidationError` at build | `SchemaErrors` with failure cases |

They're complementary: Pydantic guards the **metadata record**; Pandera guards the **page-quality table** (schema + data-quality checks like "no page number ≤ 0", "scores in range", "not every page empty").

## Report failures, don't just raise (AC4)
`validate_pages` **never raises** — it returns a `ValidationReport(ok, errors, empty_pages, low_quality_pages)`. Why: a pipeline needs to **record** the failure against the `ingestion_job` (`error_info`) and route the job to failed/dead-letter — not crash with an opaque traceback. One low-quality page ≠ invalid document; *all* pages empty = invalid.

## Lesson: regex that matches a *word* by accident
`extract_revision("no revision marker")` first returned `"marker"` — the pattern `revision\s*(\w+)` happily grabbed the next word. Fix: require a separator and a token that is **short-alpha (A, B2)** *or* **contains a digit** — so a long all-alpha dictionary word can't match. Moral: validate regexes against **negative** cases, not just the happy path.

## Rules to remember
1. Clean conservatively; preserve headings/paragraphs for chunking.
2. Metadata is a **Pydantic contract** — invalid metadata should fail to construct.
3. Use **Pandera for frames**, **Pydantic for records** — don't force one into the other.
4. Validation returns a **report** to attach to the job, not an exception.
5. Test heuristics/regexes with negative cases.

## Related
- **Decision:** [ADR 0018](../../adr/0018-pydantic-records-pandera-frames.md) (Pydantic for records, Pandera for frames).
- [pdf-extraction](./pdf-extraction.md) (produces the pages this cleans) · [config-12-factor](./config-12-factor.md).
- Story 2.4; feeds Story 2.5 (dedup/versioning) and Epic 3 (chunking).
