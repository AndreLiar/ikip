# 0029. Hierarchical (parent/child) chunking via section-based auto-merging

- **Status:** Accepted — **Stage 1 implemented** (opt-in `make_hybrid_retrieve(auto_merge=True)`, `ikip_common.llm.automerge`); Stage 2 remains gated on vector-store capacity.
- **Date:** 2026-11-15
- **Deciders:** Architect, PM
- **Related:** [ADR 0019](./0019-structure-aware-chunking.md) (flat structure-aware chunking it extends) · [ADR 0027](./0027-vector-storage-halfvec-now-qdrant-later.md) (vector-store capacity gates Stage 2) · [ADR 0003](./0003-local-first-ports-and-adapters.md) (retriever port) · [ADR 0004](./0004-hybrid-retrieval-on-postgres.md) · FR16 (citations) · NFR6 (Recall@5) · [MISSION-043](../learning/missions/MISSION-043/mission.md) (NTRS detail-question weakness)

## Context
Flat chunking (ADR 0019) makes every chunk **both** the unit we embed/search **and** the unit we return. That forces a single size to serve two jobs that want opposite things:

- **small chunk** → sharp, precise vector match, but little surrounding context for the LLM to answer;
- **big chunk** → lots of context, but a *diluted* embedding (many ideas averaged → fuzzy match).

MISSION-043 measured exactly this failure on **NTRS** (large scientific PDFs, needle-in-haystack detail questions): retrieval is mediocre because a 400-token chunk is too coarse to match a specific detail yet too small to carry the surrounding procedure. It is also the principled fix for the over-fragmented heading scraps we had to purge in #82 (attach a heading to its parent instead of emitting it as a standalone chunk).

**Hard constraint from this project's reality:** we just hit a 100% Neon storage outage (ADR 0027). Any design that *multiplies the number of embeddings* (e.g. shrinking every chunk into many tiny children) or *stores a second copy of the text as parents* directly worsens the thing that just broke. The design must respect that.

The data model already helps us: `section` has `parent_section_id` + `hierarchy_path` (a real section hierarchy), and every `chunk` carries `section_id`. So a chunk's **parent already exists** — it is its section.

## Decision
Adopt **parent/child retrieval by section-based auto-merging**, in two separable stages so we take the storage-neutral win now and defer the storage-costly knob until the vector store can hold it.

### Stage 1 — retrieval-time parent expansion (now-ready, storage-neutral)
Keep producing and embedding **children exactly as today** (no re-chunk, no re-embed, works on the existing corpus). Change only the **retrieval boundary**:

1. Child hit — hybrid retrieval returns the top-k **child chunks** as now (sharp match on the small unit).
2. **Expand to parent** — for each hit, fetch its **parent context** by merging the sibling chunks that share its `section_id`, in `ordinal` order, bounded by `PARENT_MAX_TOKENS` (a window centered on the hit when the section is larger than the cap).
3. **Dedup** — when several children hit the same section, merge them into **one** parent context (no repeated text; keeps the k budget meaningful).
4. **Feed the parent to the LLM, cite the child** — the LLM reasons over the broader section context, but the citation still resolves to the **precise child** (`chunk → section → document_version → page`, FR16). Precision of the citation is unchanged; only the *context* widens.

This lives behind the existing retriever port (ADR 0003) as a post-retrieval transform in `make_hybrid_retrieve` / the `RetrievalResult` assembly — **no schema change, no new storage, no re-ingestion.** Tenant scoping is preserved (siblings are fetched within the same tenant/section).

### Stage 2 — smaller children for sharper matching (optional, GATED)
Independently, shrink the **child** chunk size (e.g. ~400 → ~150 tokens) so the embedded unit matches a specific detail more sharply, while Stage 1 restores the context. This is the classic "small-to-big".

**This increases the embedding count** (more, smaller children → more vectors) → more vector storage. Therefore Stage 2 is **gated on vector-store capacity**: do not enable it on free-tier pgvector/Neon. Turn it on only after the Qdrant move (ADR 0027) or a tier upgrade. Tunable via chunk-size config; the parent (section) is unchanged.

## Consequences
**Positive**
- Resolves the precision/context trade-off: sharp match on children, full context from the parent section.
- **Stage 1 is storage-neutral and corpus-ready** — ships on the existing 93k chunks with no re-embed, directly targeting the measured NTRS weakness.
- Citations stay precise (child-level, FR16); only the LLM's context widens.
- Reuses the existing `section`/`parent_section_id` hierarchy — no new table, contained behind the retriever port.

**Negative / risks**
- Retrieval logic grows: sibling fetch, bounded merge, parent dedup, and token accounting at request time (latency + a second query per hit; mitigate by batching the sibling fetch).
- Parent windows can **overlap** across neighbouring hits → must dedup to avoid feeding (and paying for) repeated text.
- Stage 2 trades storage for precision — must not be enabled before the vector store can hold the extra vectors (ties this ADR to ADR 0027's trigger).

**Neutral**
- Parent size (`PARENT_MAX_TOKENS`) is a tunable; start conservative to bound LLM context cost.

## Alternatives considered
- **Store explicit parent chunks** (a `parent_chunk_id` column + larger parent rows). Rejected: duplicates text in storage — the exact pressure that caused the outage (ADR 0027). Section-as-parent gives the same benefit for free.
- **Sentence-window / neighbour expansion** (expand a hit to its ±N neighbouring chunks regardless of section). Simpler but ignores structure and can cross section boundaries mid-thought; we already have a *better* boundary (the section). Keep as a fallback when structure is poor.
- **LlamaIndex `AutoMergingRetriever` / hierarchical node parser** — good prior art; adoptable later behind the retriever port (ADR 0021) if we want its tree-merging, but it implies its node store. Our section table already encodes the tree.
- **Semantic chunking** — orthogonal (it changes *where* we cut, not the parent/child structure); still rejected at MVP (cost/circularity, ADR 0019).

## Revisit when
- Stage 1 ships and Recall@5 / faithfulness on NTRS **detail** questions is re-measured (MISSION-043 harness) — if the context gap closes, Stage 2 may be unnecessary.
- The vector store gains capacity (Qdrant, ADR 0027, or a tier upgrade) → enable **Stage 2** smaller children and re-measure precision.
- Parent overlap/dedup or latency becomes material at scale → revisit batching or precompute section text.
