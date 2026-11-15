# Concept — Chunking (splitting documents for retrieval)

_Write-once concept note. First used by [MISSION-012](../missions/MISSION-012/mission.md). Decision: [ADR 0019](../../adr/0019-structure-aware-chunking.md). Opens Epic 3._

> 🇫🇷 Version française détaillée (exploration des 5 stratégies) : [`chunking-strategies.fr.md`](./chunking-strategies.fr.md)

## Why chunk at all
You can't embed a 100-page manual as one vector (it averages everything → meaningless) nor a single sentence (no context). Retrieval works on **chunks** — pieces big enough to carry meaning, small enough to be precise and citable. **Chunking decides retrieval quality more than the embedding model does**: bad chunks can't be rescued by good embeddings.

## Chunks vs embeddings — two views of the same passage
A **chunk** and its **embedding** are the same passage in two forms, and they do opposite jobs:

| | **Chunk** | **Embedding** |
|---|---|---|
| what | the **text** + metadata (section, page, ordinal) | a **vector** (512 numbers) capturing that text's *meaning* |
| made by | the chunker splitting a document | the embedding model reading the chunk |
| used to | **read + cite** (the answer's evidence) | **search** (cosine similarity in vector space) |
| stored in | `chunk` table | `embedding` table (vector + HNSW index) |

They are **1-to-1 per model version** (`embedding.chunk_id`; the unique key is `(chunk_id, model_version)` so re-embedding with a new model *adds* rows, additive — see [embeddings](./embeddings.md)). Deleting a chunk cascades to its embedding. At query time: **embed the question → nearest embeddings (HNSW) → fetch *those* chunks' text → feed the LLM + cite.** You *search* with the embedding but *answer* with the chunk — the embedding is how the machine finds the passage; the chunk is the passage. One practical consequence: the `embedding` table (vectors + ANN index) is ~¾ of the database, which is why vector storage, not chunk text, is the capacity constraint ([ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md)).

## The main strategies (and their trade-offs)
| Strategy | How | Coherence | Citable | Cost | Note |
|---|---|---|---|---|---|
| **Fixed-size** | every N tokens + overlap | ❌ cuts mid-sentence/table | medium | $ | simplest; bad for structured docs |
| **Sentence/paragraph** | split on natural boundaries | ✅ | medium | $ | uneven sizes |
| **Structure-aware** ⭐ | split by sections/headings | ✅✅ | ✅✅ | $ | needs document structure (we have it) |
| **Semantic** | split where meaning shifts (embed-then-split) | ✅✅ | medium | $$$ | costly, circular, non-deterministic |
| **Hierarchical** | small chunks to search, big parent for context | ✅✅ | ✅ | $$ | more complex; future extension |

## IKIP's choice: structure-aware + bounded sub-splitting (ADR 0019)
Industrial manuals are **highly structured** (numbered sections, fault-code tables) and precise **citations are mandatory** (FR16). So:
1. **Split by structure first** — headings open sections (reusing `iter_blocks` from Story 2.4); a procedure/table stays whole.
2. **Sub-split over-long sections** at sentence boundaries, with a small **overlap** so context carries across the cut.
3. **Carry metadata on every chunk** — section + page range → a resolvable back-reference to document/version/page/section.

Semantic chunking is avoided at MVP (it needs embeddings *before* embedding — costly and circular). Hierarchical parent/child is the planned next extension for more context — designed in [ADR 0029](../../adr/0029-hierarchical-parent-child-chunking.md) (see below).

## Overlap: why a little duplication is good
When you cut a long section, the sentence right after the cut loses the context before it. A small **token overlap** (e.g. 40 tokens) repeats the tail of one chunk at the head of the next, so a query matching text near a boundary still retrieves a chunk that contains the full thought. Cost: a little duplicated text — standard and worth it.

## Tokens, not characters (and the "real tokenizer")
Chunk sizes are in **tokens** — the subword units the model actually consumes (byte-pair encoding, e.g. OpenAI's `cl100k_base`), *not* characters. We currently **approximate** `tokens ≈ len(text) / 4` (`estimate_tokens` in `chunking.py`). That average is wrong for numbers, code, whitespace-heavy OCR text and **French** (accents + legal terms tokenize differently), so a "400-token" chunk might really be 320 or 500. Why wiring the **real tokenizer** (`tiktoken`) matters:
- **No silent truncation** — the embedding model caps input (8,191 tokens for `text-embedding-3-small`); an undercount lets a long passage be silently cut and embedded incomplete.
- **Even chunks** — consistent semantic density → better retrieval.
- **Honest cost** — tokens = $.

Impact is **correctness, not a quality leap** (ADR 0019 flags it as deferred, Story 3.2).

## Hierarchical (parent/child) — the planned next step
Flat chunking makes one size serve two opposite jobs: **small** = sharp match but little context; **big** = rich context but a *diluted* (fuzzy) embedding. **Parent/child** breaks the tie: **search on small children**, **return the larger parent** for context. This directly targets the measured NTRS weakness (big PDFs + detail questions, [MISSION-043](../missions/MISSION-043/mission.md)) and is the principled fix for the heading-only fragments we had to purge (attach a heading to its parent instead of emitting it alone).

IKIP's design ([ADR 0029](../../adr/0029-hierarchical-parent-child-chunking.md)) reuses the existing `section` as the parent (every `chunk` already has `section_id`; `section` already has `parent_section_id`), so **Stage 1 is retrieval-time auto-merging — storage-neutral, no re-embedding** (expand a child hit to its section's merged text, cite the precise child). **Stage 2** (shrink children for sharper matching) *increases the vector count* → gated on vector-store capacity (ADR 0027), because more embeddings is the exact pressure that caused our storage outage.

## Citations: the back-reference chain
Every chunk keeps `section_id` + page range, and a `Section` knows its `document_version_id`. So from any retrieved chunk you can walk **chunk → section → document_version** to answer "which document, which revision, which page" (FR16) — the chain is tested, not assumed.

## Rules to remember
1. Structure first; sub-split only when a section is too long.
2. Keep sections/tables/procedures coherent — don't cut mid-thought.
3. Overlap across sub-split boundaries for context.
4. Size in tokens; keep chunks bounded.
5. Every chunk resolves back to document/version/page/section (citations).
6. Chunking is pure + deterministic → unit-test it (boundaries, metadata, overlap).

## Related
- [ADR 0019](../../adr/0019-structure-aware-chunking.md) (flat structure-aware, the current default) · [ADR 0029](../../adr/0029-hierarchical-parent-child-chunking.md) (parent/child, the next step) · [ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md) (why vectors — not chunk text — are the storage constraint, and why a dedicated vector store at scale).
- [embeddings](./embeddings.md) (chunks → vectors) · [data-validation](./data-validation.md) (`iter_blocks` structure) · [why-rag](./why-rag.md) (why retrieval needs chunks) · [dedup-versioning](./dedup-versioning.md) (chunks belong to a version) · [retrieval](./retrieval.md) / [hybrid-retrieval](./hybrid-retrieval.md) (where Stage-1 auto-merging lands).
