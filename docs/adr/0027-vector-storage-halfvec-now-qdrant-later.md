# 0027. Vector storage strategy: halfvec on pgvector/Neon now → dedicated vector store (Qdrant) later

- **Status:** Accepted — halfvec implemented now; Qdrant is a **triggered future option** behind the `VectorStore` port.
- **Date:** 2026-11-14
- **Deciders:** Architect, PM
- **Related:** [ADR 0001](./0001-vector-store-pgvector.md) (pgvector) · [ADR 0003](./0003-local-first-ports-and-adapters.md) (ports) · [ADR 0004](./0004-hybrid-retrieval-on-postgres.md) (hybrid in PG) · [ADR 0015](./0015-neon-serverless-postgres.md) (Neon tier) · [ADR 0020](./0020-embedding-model-text-embedding-3-small.md) (512-dim) · Epic 3

## Context
Ingesting multiple corpora/tenants pushed the **free Neon tier (1 GB)** to ~89%. Measured breakdown: the **`embedding` table = 655 MB** (125k × 512-dim **float32** vectors + HNSW index) — i.e. **the vectors are ~85% of the database**; `chunk` text = 105 MB; everything else < 2 MB. Big-PDF corpora (e.g. 500 DOE energy manuals) would add another ~130 MB and blow the tier.

So the question is **where and how vectors are stored**, without losing the invariants that put them in Postgres in the first place (ADR 0001): the `chunk → section → document_version` **citation chain** (FR16) and **tenant scoping** (NFR10), queried hybrid with BM25 in one place (ADR 0004).

## Decision
A **staged** strategy — cheap lever first, datastore move only when triggered:

1. **Now — `halfvec` (16-bit vectors).** Store the vector column as `halfvec(512)` instead of `vector(512)` float32 → **~half the storage** (655 MB → ~330 MB) with **negligible cosine-ANN recall loss**, **no re-embedding** (in-place `vector::halfvec` cast + HNSW rebuilt with `halfvec_cosine_ops`). Retrieval (`cosine_distance`), the dimension asset-check (`vector_dims`) and the citation chain are unchanged. (ADR 0015 anticipated exactly this: "512 dims and/or halfvec so the index fits the tier".)
2. **Now — cap the free tier.** Do **not** bulk-ingest the largest (big-PDF) corpora into the free Neon; keep their raw in R2 (10 GB free) + their `IngestionJob` rows seeded, and process them selectively or after a capacity move. Small text corpora (legal codes, decisions) are cheap and stay.
3. **Optional further halving — 256-dim Matryoshka.** `text-embedding-3-small` supports truncation to 256 dims (ADR 0020); combined with halfvec that is a **4× reduction** vs the original. Deferred unless needed (recall trade-off to eval first).
4. **Later (triggered) — move the vector arm to a dedicated vector DB behind the `VectorStore` port.** **Qdrant Cloud free tier (4 GB disk / 1 GB RAM, free forever)** is the target: vectors + a `chunk_id`/tenant payload live in Qdrant; **Postgres keeps the chunks, metadata and the citation chain**. Hybrid retrieval stays BM25-in-Postgres + vector-in-Qdrant, **fused in-app** (we already own RRF). This is a **clean swap** because retrieval already sits behind our port (ADR 0001/0003) — the domain does not change.

## Triggers for the Qdrant move (do it when the data says so, not before)
- vector storage would exceed the Postgres tier even with halfvec (+256-dim), **or**
- ANN latency/scale (many tenants × large corpora) outgrows pgvector-on-Neon, **or**
- we want vector-store features (quantization, named vectors, payload filtering at scale) Postgres doesn't give cheaply.

## Consequences
**halfvec now**
- + ~2× capacity, no data loss, **single datastore** kept (simplest; citations/tenant scoping untouched).
- − ~1 bit of recall precision (immaterial for cosine ANN at 512 dims); must rebuild the HNSW index once.

**Qdrant later**
- + Purpose-built ANN + much more vector capacity on a free tier; offloads the 85%-of-DB pressure from Postgres.
- − A **second datastore**: cross-store **consistency** (a chunk's vector in Qdrant must track its PG row), **tenant isolation enforced in Qdrant too** (payload filter on `tenant_id`, mirrored isolation tests), **citations resolved from PG after a Qdrant hit**, and 2-phase delete (Story 6.5) across both. The `VectorStore` port contains the blast radius, but the operational surface grows.

## Alternatives considered
- **Upgrade Neon (Launch ~$19/mo)** — buys headroom with zero code; a money decision, orthogonal to the engineering lever. Keep as the simplest escape hatch.
- **Keep float32 in Postgres** — rejected: it is the thing that filled the tier.
- **Go straight to Qdrant now** — rejected as premature: halfvec buys 2× for a one-line type change; a second datastore is justified by scale, not by the current demo.
