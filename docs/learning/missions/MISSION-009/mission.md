# MISSION-009 — Cleaning, normalization, metadata & validation (Epic 2, Story 2.4)

**Mode:** Autonome + knowledge transfer.
**Objective:** turn raw extracted text into consistent curated text (structure preserved), attach validated normalized metadata, and validate content quality — recording failures for the ingestion job.
**Maps to:** Epic 2 / Story 2.4.

## Acceptance criteria
1. Cleaning/normalization → consistent curated text, structure preserved. — **[verified]** (de-hyphenation, unicode/whitespace, `iter_blocks` heading/paragraph)
2. Documents classified + metadata normalized per schema. — **[verified]** (`classify_document`, `DocumentMetadata` Pydantic contract)
3. Content validation via schema/data-quality checks (Pandera/Pydantic). — **[verified]** (Pandera page-quality frame + Pydantic metadata)
4. Validation failures recorded against the ingestion job. — **[verified]** (`ValidationReport.as_error_info()` → `ingestion_job.error_info`)

## Deliverables
- `services/document-processing/`: `cleaning.py`, `metadata.py`, `validation.py` (all pure, CI-tested); `pandera[pandas]` added to core deps (light).
- Tests: `test_cleaning.py`, `test_metadata.py`, `test_validation.py` (15, hermetic).
- [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [data-validation](../../concepts/data-validation.md) (cleaning, Pydantic-vs-Pandera, report-not-raise, regex negative cases). Reuses [pdf-extraction](../../concepts/pdf-extraction.md).

## Notable
- Pydantic validates the **metadata record**; Pandera validates the **tabular page-quality frame** — complementary.
- Regex bug caught: `extract_revision` matched the word "marker"; fixed with negative-case tests.
