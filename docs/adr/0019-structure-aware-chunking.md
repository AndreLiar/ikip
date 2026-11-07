# 0019. Structure-aware chunking with bounded sub-splitting

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR9 (chunking), FR16 (citations), FR14 (version-aware) · NFR6 (Recall@5) · Epic 3 (Story 3.1) · builds on Story 2.4 (`iter_blocks`), [ADR 0001](./0001-vector-store-pgvector.md)

## Context
Retrieval quality is decided more by **how documents are chunked** than by the embedding model: bad chunks can't be rescued by good embeddings. A chunk must be large enough to carry meaning, small enough to be precise and citable, and must resolve back to document/version/page/section (FR16). Industrial manuals are **highly structured** (numbered sections, fault-code tables) and we already extract structure (`iter_blocks` → heading/paragraph, Story 2.4). The main chunking strategies:

1. **Fixed-size** (N tokens + overlap) — simple, but cuts mid-sentence/table, breaking meaning.
2. **Sentence/paragraph** — respects meaning, but very uneven sizes.
3. **Structure-aware** — chunk by section/heading; coherent + naturally citable; depends on having structure (we do).
4. **Semantic** — split where meaning shifts (embed-then-split); smart boundaries but costly and circular (needs embeddings before embedding).
5. **Hierarchical (parent/child)** — small chunks to search, larger parent returned for context; precise + contextual, but more complex.

## Decision
Use **structure-aware chunking with bounded sub-splitting**:

1. **Split by structure first** — use the document's sections/headings (`iter_blocks`) so a procedure/table stays whole; create a `Section` per structural unit.
2. **Sub-split over-long sections** — if a section exceeds the max chunk size, split it at **sentence/paragraph boundaries** with a small **overlap** (carry a little context across the cut).
3. **Carry metadata on every chunk** — `section_id`, page range, token count → a resolvable back-reference to document/version/page/section (FR16), tenant-scoped for retrieval (NFR10).

Tunable params (chunk size, overlap) live in config; sizes are in **tokens** (approximate, since embeddings are token-based). Semantic chunking is **not** used at MVP (cost/circularity); **hierarchical (parent/child)** is a **planned post-MVP extension** if retrieval quality needs it.

## Consequences
**Positive**
- Keeps sections/procedures/tables coherent → better retrieval of complete answers.
- **Natural, precise citations** ("page 142, section 3.2") — core IKIP value (FR16).
- Reuses existing structure extraction (`iter_blocks`) — no new heavy dependency.
- Bounded sizes → predictable embedding cost + index size; pure/deterministic → CI-testable.

**Negative / risks**
- Quality depends on extraction structure; poorly-structured/scanned docs fall back to paragraph sub-splitting (acceptable).
- Heading detection is heuristic (Story 2.4) → occasional mis-sectioning.
- Overlap duplicates a little text (small storage/embedding cost) — standard trade-off for boundary context.

**Neutral**
- Token counting is approximate until the embedding tokenizer is wired (Story 3.2).

## Alternatives Considered
- **Fixed-size + overlap:** simplest, but cuts mid-sentence/table and weakens citations — rejected as the primary strategy for structured manuals.
- **Semantic chunking:** smart boundaries, but needs embeddings up front (costly, circular, non-deterministic) — rejected at MVP; revisit if structure is poor.
- **Hierarchical parent/child:** precise + contextual, more storage/complexity — deferred to post-MVP (planned extension).
- **Sentence/paragraph only:** coherent but uneven sizes and weaker section-level citations — folded in as the *sub-split* step rather than the primary one.

## Revisit When
- Retrieval quality (NFR6, Recall@5) plateaus and analysis points at chunk context → adopt **hierarchical parent/child**.
- Documents are mostly unstructured/scanned → lean more on semantic/paragraph splitting.
- A tokenizer mismatch makes token-based sizing inaccurate → align with the embedding model's tokenizer (Story 3.2).
