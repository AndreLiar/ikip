# Concept — Chunking (splitting documents for retrieval)

_Write-once concept note. First used by [MISSION-012](../missions/MISSION-012/mission.md). Decision: [ADR 0019](../../adr/0019-structure-aware-chunking.md). Opens Epic 3._

> 🇫🇷 Version française détaillée (exploration des 5 stratégies) : [`chunking-strategies.fr.md`](./chunking-strategies.fr.md)

## Why chunk at all
You can't embed a 100-page manual as one vector (it averages everything → meaningless) nor a single sentence (no context). Retrieval works on **chunks** — pieces big enough to carry meaning, small enough to be precise and citable. **Chunking decides retrieval quality more than the embedding model does**: bad chunks can't be rescued by good embeddings.

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

Semantic chunking is avoided at MVP (it needs embeddings *before* embedding — costly and circular). Hierarchical parent/child is a planned post-MVP extension if retrieval quality needs more context.

## Overlap: why a little duplication is good
When you cut a long section, the sentence right after the cut loses the context before it. A small **token overlap** (e.g. 40 tokens) repeats the tail of one chunk at the head of the next, so a query matching text near a boundary still retrieves a chunk that contains the full thought. Cost: a little duplicated text — standard and worth it.

## Tokens, not characters
Chunk sizes are in **tokens** (what the embedding model actually consumes), approximated as ~4 chars/token until the real tokenizer is wired (Story 3.2). Bounded token sizes → predictable embedding cost and index size.

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
- [ADR 0019](../../adr/0019-structure-aware-chunking.md) (decision) · [data-validation](./data-validation.md) (`iter_blocks` structure) · [why-rag](./why-rag.md) (why retrieval needs chunks) · [dedup-versioning](./dedup-versioning.md) (chunks belong to a version).
- Next: embeddings (Story 3.2) turn chunks into vectors; retrieval (3.3/3.4) finds the right ones.
