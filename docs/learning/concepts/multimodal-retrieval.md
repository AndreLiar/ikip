# Concept — Multimodal retrieval: making a diagram findable

_Write-once concept note. First used by Epic 9 (Stories 9.1–9.3). Decision: [ADR 0031](../../adr/0031-multimodal-retrieval-caption-and-embed.md). Builds on [pdf-extraction](./pdf-extraction.md), [retrieval](./retrieval.md), [embeddings](./embeddings.md)._

## The problem: a diagram isn't text
Text retrieval embeds *words*. A wiring schematic, a chart, an exploded parts drawing — these carry meaning **visually and spatially** (how components connect), not as a line of text. To make one *searchable* you must first turn "what it shows" into something embeddable.

## The decision: caption-and-embed (ADR 0031)
Instead of a new image-vector model, we **describe the image in text** (a *caption*), embed that caption with the **existing** `text-embedding-3-small`, and index it in the **same** pgvector store. So visual evidence flows through the *same* hybrid retrieval, RRF, and citation chain as text — **no new embedding model, no storage blowup** (respects [ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md), written right after a storage outage). The caption *is* a `Chunk`; a hit on it resolves to the diagram's exact page region (the viewer highlights it, FR16). Honest trade-off: you retrieve on the *description*, not the pixels — lossy, measured by a visual gold, with native multimodal embeddings as the gated escape hatch.

## Three tools, three different jobs (the key mental model)
Making a diagram findable needs **three distinct capabilities**, and each tool does exactly one:

| Tool | What it does | What it gives you | What it CANNOT do |
|---|---|---|---|
| **OCR** (Tesseract / Indra) | reads **characters** from pixels | the stray labels: `K3  E42  24V  RESET` | no structure — a *bag of tokens*, meaning lost |
| **Docling** (layout) | **detects + classifies** regions; extracts table cells | "a figure at this bbox p.12"; a table's cell data | can't *describe* a diagram's meaning |
| **Vision LLM** (GPT-4o) | **understands + describes** the image | *"relay K3 controls the E42 fault-reset circuit, fed by 24V through a fuse"* | (it's the expensive one — gate its use) |

They are **complementary, not substitutes**. The pipeline uses all three:
- **Docling** answers *where* the diagram is (the region/bbox — Story 9.1, `DoclingLayoutEngine`).
- **OCR** optionally feeds the labels *into* the captioner.
- The **vision LLM** answers *what it means* (the caption — Story 9.2).

## Why OCR alone fails on a diagram
OCR reads text roughly left-to-right; a schematic's meaning is in the **connections**, which OCR discards.

| input: a wiring schematic | output | useful? |
|---|---|---|
| OCR | `"K3 E42 24V RESET FUSE"` | ❌ word-salad — can't answer "what resets the E42 fault?" |
| Vision LLM | *"relay K3 controls the E42 fault-reset circuit…"* | ✅ retrievable + answerable |

So ADR 0031 **rejects "OCR the diagram only"** as the primary path and treats OCR as a caption *input*, not the caption.

## Why Docling can't finish the job
Docling is a **localizer**, not an interpreter. For a **table** it extracts the cell structure — so a table is often captionable from its own text with **no vision LLM**. For a **diagram/schematic/chart** it gives the region + maybe OCR'd labels, never a description of the circuit. "Where + what kind" ≠ "what it means."

## Why we need the vision LLM (and when)
Only a **multimodal LLM** turns a *diagram's visual meaning* into searchable text. We built the `VisionCaptioner` **port** (+ `FakeVisionCaptioner` for CI) and deferred the **Azure GPT-4o vision adapter** — the concrete implementation — along with the Docling crop extraction that feeds it image bytes. Mainly needed for genuinely-visual elements (schematics/charts); **tables may not need it** (Docling gives their cells).

## Cost (honest)
- **Spent so far: $0** — the real adapter was never run; the pipeline is wired with fakes.
- *If* run: a **build-time, one-time** cost — one vision call per diagram at ingestion, **never on the per-query hot path**, so it doesn't scale with usage. Order-of-magnitude (estimate): GPT-4o-**mini** vision ≈ a tenth of a cent per caption → single-digit dollars for a few thousand diagrams, once; full GPT-4o ~10–20× that. Captioning only the visual elements (not tables) keeps the count down.

## Visual citations (Story 9.3)
A caption-chunk hit carries `visual_element_id` + region (page/bbox/kind). The existing `PdfRegionViewer` renders a visual region **distinctly** (dashed outline + a kind label) vs. a text highlight, so a diagram-grounded answer highlights the exact region on the page. Authz is unchanged — the viewer opens only with a `document_version_id`; the BFF gates the presigned source URL.

## Rules to remember
1. Retrieval embeds **text**; a diagram must become text (a caption) to be searchable.
2. **Three jobs, three tools**: OCR reads characters, Docling locates/classifies, the vision LLM describes. Don't expect one to do another's job.
3. OCR of a schematic = a bag of labels (structure lost) → a caption *input*, not the caption.
4. **Tables ≠ diagrams**: Docling extracts table cells (captionable for free); diagrams need the vision LLM.
5. Caption-and-embed **reuses the whole text stack** — no new vector model, no storage blowup; native multimodal is gated ([ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md)).
6. The vision-LLM cost is **build-time + one-time**, off the query path; caption only what's genuinely visual.

## Related
- [ADR 0031](../../adr/0031-multimodal-retrieval-caption-and-embed.md) (decision) · [pdf-extraction](./pdf-extraction.md) (native vs scanned, OCR, Docling LayoutEngine) · [retrieval](./retrieval.md) / [hybrid-retrieval](./hybrid-retrieval.md) (the stack a caption reuses) · [embeddings](./embeddings.md) · [ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md) (why native multimodal is storage-gated).
