# 0031. Multimodal retrieval: caption-and-embed now → native multimodal later (Epic 9)

- **Status:** Proposed — architecture for Epic 9 (post-MVP visual/multimodal); no code until agreed.
- **Date:** 2026-11-16
- **Deciders:** Architect, PM
- **Related:** [Epic 9](../prd/epic-9-advanced-multimodal-retrieval.md) · RAG dimension B ([rag-design-challenges](../rag-design-challenges.md)) · [ADR 0024](./0024-per-page-extraction-routing-and-indra-ocr.md) (LayoutEngine/Docling) · [ADR 0020](./0020-embedding-model-text-embedding-3-small.md) (text embeddings) · [ADR 0027](./0027-vector-storage-halfvec-now-qdrant-later.md) (vector storage reality) · [ADR 0022](./0022-grounded-answer-langgraph-gpt5-mini.md) · FR16 (citations) · NFR10

## Context
Epic 9 makes **diagrams, schematics and visual tables** retrievable evidence with **visual citations** (highlight the cited region on the page). Two parts of the groundwork already exist and should be reused, not rebuilt:
- **Region extraction**: `LayoutEngine` / `DoclingLayoutEngine` already yield `TextRegion(page, text, bbox)` and `TableRef(page, bbox)`; `chunk_regions` carries page-normalized highlight regions (Story 2.3/3.1).
- **The viewer already highlights regions**: `apps/web` has a `PdfRegionViewer` — Story 9.3 extends it, not greenfield.

The open question is **how visual content becomes a searchable vector** (Story 9.2). The obvious answer — *native multimodal embeddings* (CLIP-style / a vision embedding model) — has two hard costs in **this** environment:
1. **New model infra + cost**: our stack is text-only (`text-embedding-3-small`, ADR 0020); a vision embedding model is a new dependency and spend.
2. **Storage**: image/multimodal vectors are larger, and we just recovered from a 100%-Neon outage (ADR 0027). Bigger vectors run straight into that wall.

## Decision
**Caption-and-embed now; native multimodal later (gated).**

1. **Visual element as evidence (Story 9.1).** Extend the existing `LayoutEngine` output to also detect **picture/diagram** regions (Docling already classifies pictures + tables) and persist each visual element as **retrievable evidence** linked to its `Section`/`Chunk` with **page + bbox** (the region the viewer highlights). Store the crop key in object storage (R2), not the DB. Quality-scored; low-confidence flagged (AC3).

2. **Caption-and-embed for retrieval (Story 9.2) — the key choice.** A **vision LLM describes** each diagram/visual table in text (a dense caption: what it shows, labels, fault codes, relations); we **embed the caption with the existing `text-embedding-3-small`** and index it in the **same** pgvector store, behind the same `VectorStore`/retrieval interfaces (ADR 0003). So:
   - **no new embedding model**, **no storage blowup** (text-size vectors — respects ADR 0027), **reuses hybrid retrieval + RRF + the citation chain** unchanged;
   - a visual result retrieves on its *description* but **cites the real region** (page + bbox), so grounding + the viewer highlight are exact (FR16).

3. **Native multimodal embeddings — deferred + gated.** True image-vector similarity (CLIP / a multimodal model) is a **triggered future option** behind the `VectorStore`/`LLMClient` ports: enable only when (a) caption-and-embed is measurably insufficient on the visual gold, **and** (b) the vector store can hold image vectors (Qdrant, ADR 0027) — never before.

4. **Visual citations (Story 9.3).** Reuse the `PdfRegionViewer`: a citation resolves `visual-element → page → bbox`; the viewer highlights it; authz is enforced before display (AC4). Grounding/citation metrics extend to visual evidence.

5. **Evaluation (Story 9.1 AC4 / 9.3 AC3).** A **DocVQA-style visual gold** (question → answer → the page+region that supports it); measure retrieval of the right visual region + citation correctness, wired into the Epic 5 harness. Deterministic region-hit + citation metrics gate; caption quality is the LLM-judged part.

## Consequences
**Positive**
- **Feasible in this environment**: reuses the text embedding stack, the pgvector store (no storage blowup — the ADR 0027 constraint is respected), hybrid retrieval, the citation chain, and the existing `PdfRegionViewer`.
- Visual content is **searchable + citable** with **no new embedding model**; the port boundary keeps native multimodal a clean, later swap.
- Captions are **inspectable** (unlike opaque image vectors) — easier to debug/eval and they double as accessibility text.

**Negative / risks**
- **Lossy**: retrieval is on the *description*, not the pixels — a diagram the captioner under-describes is under-retrieved. Mitigated by caption quality + the visual gold measuring it; native multimodal is the escape hatch.
- **Captioning cost/latency** (one vision-LLM call per visual element at build time) — a build-time cost, bounded by element count.
- Picture/diagram **detection quality** depends on Docling; low-confidence flagging (AC3) + human review backstop.

**Neutral**
- Visual crops live in R2 (like raw/curated tiers); only the caption vector + region metadata touch Postgres.

## Alternatives considered
- **Native multimodal embeddings now (CLIP / vision model)** — rejected at MVP: a new model + larger vectors immediately after a storage outage (ADR 0027); the port keeps it as the measured-trigger upgrade.
- **OCR the diagram text only** — rejected as the primary path: schematics are spatial/relational, not linear text; a caption captures relationships OCR misses (keep OCR as a caption input).
- **Skip visual retrieval; link diagrams to their surrounding text chunk only** — the cheapest, but fails diagram-specific questions (dimension B); caption-and-embed is the smallest step that actually makes a diagram findable.
- **Multimodal LLM at answer time over the page image (no index)** — strong for a known page, but can't *retrieve* the right page at scale; complementary later, not a retrieval substitute.

## Revisit when
- Visual-gold retrieval/citation plateaus and analysis attributes it to caption lossiness (not detection) → adopt **native multimodal embeddings** behind the `VectorStore` port, on a store that holds image vectors (Qdrant, ADR 0027).
- Picture/table detection quality is the limiter → upgrade the `LayoutEngine` (Docling model / a dedicated detector).
- Answer-time visual verification is needed on a selected page → add a multimodal-LLM read step (a complement to retrieval, ADR 0022 graph).
