# Epic 9 — Advanced Multimodal Retrieval  (Post-MVP)

_Sharded from `../prd.md`. Part of the [epic index](./index.md). **Post-MVP** — sequenced after Epics 1–6; not part of the initial production scope._

**Goal:** Extend extraction and retrieval to engineering drawings, schematics and visual tables, with multimodal embeddings and visual citations — the capability explicitly deferred from Story 2.3 and the brief's P2 list.

**Addresses:** RAG dimension B (visual/multimodal, advanced) in [`../rag-design-challenges.md`](../rag-design-challenges.md). Builds on Epic 2 (extraction), Epic 3 (retrieval).

---

## Story 9.1 Diagram & Visual-Table Extraction
As an engineer, I want drawings/schematics and complex visual tables extracted with page/region references, so that they become retrievable evidence.
**Acceptance Criteria:**
1. Diagram/schematic regions and visual tables are detected and extracted with page + bounding-region references.
2. Extracted elements are linked to `Section`/`Chunk` with resolvable back-references.
3. Extraction quality scored; low-confidence flagged for review.
4. Evaluation uses a visual gold set (e.g., DocVQA-style).

## Story 9.2 Multimodal Embeddings & Retrieval
As a technician, I want to retrieve answers grounded in diagrams/visual tables, so that visual information is usable.
**Acceptance Criteria:**
1. Multimodal embeddings generated and indexed (versioned, behind `VectorStore`/`LLMClient` interfaces).
2. Retrieval can return visual evidence with equipment/version filters.
3. Hybrid fusion includes visual results where relevant.
4. Latency targets re-validated for the multimodal path.

## Story 9.3 Visual Citations in the Viewer
As a technician, I want visual citations highlighted on the source page, so that I can verify diagram-based answers.
**Acceptance Criteria:**
1. Citations resolve to the exact page and visual region.
2. The document viewer highlights the cited region.
3. Groundedness/citation metrics extended to visual evidence.
4. Authorization enforced before visual source display.
