# MISSION-012 — Structure-aware chunking (Epic 3, Story 3.1)

**Mode:** Guidé (chunking-strategy decision) → Autonome (impl) + knowledge transfer.
**Objective:** split curated documents into coherent, citable retrieval units (chunks) with section/page back-references — the input to embeddings + retrieval.
**Maps to:** Epic 3 / Story 3.1. **Opens Epic 3.**

## Strategy decision (user: "explore chunking strategies")
Compared fixed-size / sentence / structure-aware / semantic / hierarchical. Chose **structure-aware + bounded sub-splitting** ([ADR 0019](../../../adr/0019-structure-aware-chunking.md)): best coherence + citations for structured manuals, no semantic-chunking cost. See [decisions.md](./decisions.md).

## Acceptance criteria
1. `section` + `chunk` records capture hierarchy, heading, page range, metadata. — **[verified]** (models + reversible migration)
2. Chunking respects structure (sections/headings) + semantic boundaries (sentence sub-split). — **[verified]** (sections stay whole; long sections sub-split)
3. Each chunk resolves back to document/version/page/section. — **[verified]** (chunk→section→document_version chain, DB test)
4. Tests validate chunk boundaries + metadata integrity. — **[verified]** (5 pure + 3 DB tests)

## Deliverables
- `ikip_docproc/chunking.py` — `chunk_document` (structure-first + sentence sub-split + overlap), `ChunkSpec`, `estimate_tokens`. Pure.
- `ikip_common/db/models.py` — `Section`, `Chunk` (tenant-scoped) + reversible migration.
- Tests: `test_chunking.py` (pure, CI), `test_chunk_models.py` (DB-gated).
- [ADR 0019](../../../adr/0019-structure-aware-chunking.md) · [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [chunking](../../concepts/chunking.md) (strategies, structure-aware, overlap, citation chain). Reuses [data-validation](../../concepts/data-validation.md) (`iter_blocks`), [why-rag](../../concepts/why-rag.md).
