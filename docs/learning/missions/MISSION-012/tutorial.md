# MISSION-012 — Reproduction tutorial

Add structure-aware chunking + Section/Chunk models.

## Prerequisites
- MISSIONs 001–011; Neon dev branch; `uv`.

## Steps

1. **Models** (`db/models.py`) — `Section(UUIDPrimaryKey, Timestamped, Base)` with `document_version_id(FK)`, `parent_section_id(self FK)`, `heading`, `hierarchy_path`, `page_start/end`, `ordinal`. `Chunk(UUIDPrimaryKey, TenantScoped, Timestamped, Base)` with `section_id(FK)`, `content`, `page_start/end`, `token_count`, `chunk_metadata(JSONB)`. Export both.

2. **Chunking** (`ikip_docproc/chunking.py`) — `estimate_tokens` (≈chars/4); `ChunkSpec` dataclass; `chunk_document(text, max_tokens, overlap_tokens)`:
   - group `iter_blocks(text)` into sections (heading starts one; paragraphs attach);
   - section ≤ max_tokens → one chunk; else `_pack(sentences, ...)` with tail overlap;
   - tag each `ChunkSpec` with section heading/path + ordinal.

3. **Migration** (dev at head first — mind the enum trap)
   ```bash
   cd packages/common
   uv run --project ../.. alembic upgrade head
   uv run --project ../.. alembic revision --autogenerate -m "add section and chunk"
   uv run --project ../.. alembic upgrade head
   uv run --project ../.. alembic downgrade -1 && uv run --project ../.. alembic upgrade head
   ```

4. **Tests**
   ```bash
   uv run pytest apps packages services -q          # chunking runs; DB tests skip
   TEST_DATABASE_URL=<branch> uv run pytest packages/common/tests/test_chunk_models.py -q
   ```
   Cover: sections stay whole, long section sub-splits + overlap, ordinals, citation chain chunk→section→version, tenant scoping.

## Common mistakes
- **Autogenerate recreates all tables** → stale dev DB; reset drops tables **and** enum types, re-apply chain.
- **Cutting mid-sentence** → structure first, then sentence sub-split (not fixed-size).
- **Chunk can't be cited** → keep `section_id` + page on every chunk.
- **Sizing in characters** → size in tokens (what the model consumes).
- **DB in the chunker** → keep `chunk_document` pure; persist separately.

## Recovery
Additive; revert branch/commit. `alembic downgrade -1` removes the two tables.
