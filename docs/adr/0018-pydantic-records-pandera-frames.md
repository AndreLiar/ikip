# 0018. Validation: Pydantic for records, Pandera for frames

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR6 (classification/metadata), FR... (quality validation) · NFR5 · Epic 2 (Story 2.4) · relates to [ADR 0017](./0017-sqlalchemy-alembic.md)

## Context
The ingestion pipeline (Story 2.4) must validate two different *shapes* of data before content enters the knowledge base:

1. **A record** — the normalized metadata of **one** document (title, type, manufacturer, model, revision, page_count): a single object with typed fields.
2. **A frame** — the per-page extraction **table** (one row per page: page number, char_count, quality_score): tabular data with column-wise + row-wise rules over many rows.

These are not the same validation problem. A tool built for one is awkward for the other.

## Decision
Use **both, matched to the data shape**:

- **Pydantic** (`BaseModel`) validates **records** — e.g. `DocumentMetadata`. Typed fields + constraints (`Field(min_length=…, ge=…)`); building the object **validates** it and raises `ValidationError` on bad input. Already the project's model/config/API validator.
- **Pandera** (`DataFrameSchema`) validates **frames** — e.g. the per-page quality table: `page > 0`, `char_count >= 0`, `quality_score in [0,1]`, plus data-quality rules (e.g. "not every page empty"). Runs column/row checks over a pandas DataFrame and reports `SchemaErrors`.

Guideline for the codebase: **record → Pydantic; tabular (many rows) → Pandera. Never force one into the other's shape.** Validation results are returned as a **report** (not raised) where they must be attached to the `ingestion_job` (Story 2.4/2.6), so failures are recorded, not just thrown.

## Consequences
**Positive**
- Each validator does what it is designed for: Pydantic gives a clean typed **contract** for entities (fail-fast at construction); Pandera gives expressive **tabular** schema + data-quality checks over many rows.
- Pydantic is already used (config, API, ORM DTOs) — no new concept. Pandera is light (pandas) → stays in the fast CI job.
- Clear team rule removes "which validator?" ambiguity.

**Negative / risks**
- Two validation libraries to know.
- Pandera pulls pandas (acceptable; light vs the extraction engines).
- A contributor could reach for the wrong tool; mitigated by the record-vs-frame rule and the concept note.

**Neutral**
- Overlap is minimal: Pydantic can technically validate a list, and Pandera can validate a 1-row frame, but each is clumsy outside its shape — we don't do that.

## Alternatives Considered
- **Pydantic only:** fine for the metadata record, but validating a many-row page table means hand-looping/one-model-per-row — loses column-wise/data-quality expressiveness. Rejected for tabular data.
- **Pandera only:** great for frames, but wrapping a single metadata record in a 1-row DataFrame is artificial and loses the typed-model ergonomics (used across API/config/ORM). Rejected for records.
- **Hand-rolled assertions:** no schema, no structured failure cases, more bugs. Rejected.
- **Great Expectations / other DQ frameworks:** heavier; Pandera is enough at MVP scale and integrates as a library. Revisit if data-quality needs grow.

## Revisit When
- Tabular data-quality needs outgrow Pandera (complex expectations, profiling, data docs) → consider Great Expectations.
- A record validation needs features Pydantic lacks (unlikely) → reassess.
