# MISSION-012 — Decisions

## D1 — Structure-aware + bounded sub-splitting (ADR 0019)
- **Choice:** split by section/heading first; sub-split over-long sections at sentence boundaries with overlap.
- **Why here:** structured manuals + mandatory citations (FR16); reuses `iter_blocks`; bounded cost; no semantic-chunking circularity.
- **Alternatives:** fixed-size (cuts meaning), semantic (costly/circular), hierarchical (deferred).
- **Full rationale:** [ADR 0019](../../../adr/0019-structure-aware-chunking.md).

## D2 — Chunk carries the citation back-reference
- **Choice:** `Chunk.section_id` + page range; `Section.document_version_id`.
- **Why here:** citations (FR16) resolve chunk → section → document_version; tested as a chain.

## D3 — Chunk is tenant-scoped (denormalized tenant_id)
- **Choice:** `Chunk` has `tenant_id` directly (not only via joins).
- **Why here:** retrieval filters by tenant without a multi-join (NFR10); same pattern as the LLD.

## D4 — Sizes in tokens (approximate for now)
- **Choice:** `estimate_tokens` ≈ chars/4 until the embedding tokenizer lands (Story 3.2).
- **Why here:** chunk sizing must track what the model consumes; exact tokenizer is a 3.2 follow-up.

## D5 — Chunking is pure/deterministic
- **Choice:** no DB, no engines in `chunk_document`; persistence is separate.
- **Why here:** unit-test boundaries/overlap/metadata in the fast CI job; same pattern as the rest of Epic 2/3.

## Ops note — enum-type migration trap (again)
Reconfirmed the Story 2.5 lesson: a stale dev DB (orphaned enum types from a prior broken downgrade) made autogenerate recreate all tables. Reset = drop tables **and** enum types, re-apply chain to the real baseline, then autogenerate (clean section+chunk-only migration).
