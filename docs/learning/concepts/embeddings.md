# Concept — Embeddings (turning text into vectors for retrieval)

_Write-once concept note. First used by Story 3.2. Decision: [ADR 0020](../../adr/0020-embedding-model-text-embedding-3-small.md) (model + dimension), [ADR 0007](../../adr/0007-pluggable-llm-client-azure-openai.md) (pluggable client). Follows [chunking](./chunking.md)._

## What an embedding is
An **embedding** is a list of numbers (a **vector**) that represents the *meaning* of a piece of text. A model maps text → a point in a high-dimensional space so that **texts with similar meaning land close together**, even when they share no words. "The pump won't start" and "motor fails to spin up" end up near each other; "invoice overdue" ends up far away.

That is the whole trick behind semantic search: embed the chunks once, embed the query at request time, then find the **nearest vectors** (cosine / inner product) — see [why-rag](./why-rag.md) for why we retrieve instead of stuffing everything into the prompt.

## Why we need them (vs keyword search)
Keyword/full-text search matches **words**; it misses synonyms, paraphrases and cross-language matches. Embeddings match **meaning**, so a technician's phrasing finds the right manual section even when the manual uses different terms. IKIP combines both — lexical **and** vector — in hybrid retrieval ([ADR 0004](../../adr/0004-hybrid-retrieval-on-postgres.md)); embeddings are the "meaning" half.

## Dimensions: the size of the vector
A vector has a fixed length — its **dimension** (e.g. 512, 1536, 3072). More dimensions = more capacity to encode nuance, **but** more storage and a bigger/slower index. Every chunk's vector lives in pgvector on Neon, so dimension is a direct **storage + cost** knob ([ADR 0015](../../adr/0015-neon-serverless-postgres.md)). The pgvector column type bakes it in (`vector(512)`): all vectors in one index **must** share the same dimension.

## Matryoshka: why we can shrink the vector safely
The `text-embedding-3-*` models are trained with **Matryoshka Representation Learning**: the most important information is packed into the **leading dimensions**. So you can **truncate** a 1536-dim vector to its first 512 and it stays highly useful — like Russian nesting dolls, a smaller doll still holds the essentials. This is what lets IKIP use a **small, cheap model at a reduced 512 dimensions** and still get good retrieval, fitting Neon's budget. (Older `ada-002` lacks this — truncating it would break the vector.) See [ADR 0020](../../adr/0020-embedding-model-text-embedding-3-small.md).

## Model versioning: never destroy old vectors
An embedding only makes sense next to vectors from the **same model + dimension** — you cannot compare a `3-small@512` vector with a `3-large@1024` one. So each stored embedding records a **`model_version`** (e.g. `text-embedding-3-small@512`). Re-embedding with a new model is a **versioned, additive** operation (write new vectors alongside), never an in-place overwrite (FR14). That is how we upgrade the model later without losing the ability to serve or compare the old corpus.

## Cost shape
You pay per token, **twice**: once to embed the whole corpus at ingestion, and a little each time you embed a query. So model price/token and corpus size both matter. `text-embedding-3-small` (~$0.02 / 1M tokens) keeps this in the cents range for dev.

## How it plugs into IKIP (ports & adapters)
Embeddings are produced through the pluggable **`LLMClient.embed(texts, *, model_version)`** port ([ADR 0007](../../adr/0007-pluggable-llm-client-azure-openai.md)): the Azure OpenAI adapter calls the real API, while a **fake adapter** returns deterministic vectors so the generation + versioning logic is **CI-testable without a network call** — the same pattern as ObjectStorage/R2. The real Azure resource is provisioned as code (`infrastructure/terraform/environments/dev`).

## Rules to remember
1. Embeddings encode **meaning**, not words — that's why semantic search beats keyword-only.
2. **Dimension = storage/cost knob**; all vectors in one index share it (`vector(N)`).
3. `3-*` models can be **truncated** (Matryoshka) → small+cheap can still fit Neon without wrecking quality.
4. Tag every vector with **`model_version`**; re-embedding is **additive**, never destructive (FR14).
5. You embed the corpus **and** every query → cost scales with both.
6. Go through the `LLMClient.embed` **port**; test with a fake, verify the real adapter live.

## Related
- [ADR 0020](../../adr/0020-embedding-model-text-embedding-3-small.md) (model + dimension) · [ADR 0007](../../adr/0007-pluggable-llm-client-azure-openai.md) (pluggable client) · [ADR 0015](../../adr/0015-neon-serverless-postgres.md) (Neon storage budget) · [ADR 0001](../../adr/0001-vector-store-pgvector.md) (pgvector).
- Concepts: [chunking](./chunking.md) (what gets embedded) · [why-rag](./why-rag.md) (why retrieval) · [object-storage](./object-storage.md) (same port/adapter + fake pattern).
- Next: retrieval (Stories 3.3/3.4) searches these vectors; eval (3.6) decides if the model/dimension is good enough.
