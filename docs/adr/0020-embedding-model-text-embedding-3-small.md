# 0020. Embedding model: `text-embedding-3-small` with reduced dimensions (512)

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR13, FR14 · NFR1 · Story 3.2 · builds on [ADR 0007](./0007-pluggable-llm-client-azure-openai.md) (pluggable LLMClient), [ADR 0015](./0015-neon-serverless-postgres.md) (Neon storage budget); relates to [ADR 0001](./0001-vector-store-pgvector.md), [ADR 0010](./0010-foundry-model-platform-no-dedicated-ai-gateway.md)

## Context
Story 3.2 turns chunks into vectors for retrieval. We must pick a concrete **embedding model** and a **vector dimension**. The choice is constrained by several forces:

1. **Retrieval quality** — the embedding decides how good semantic search is; a weak model can't be rescued downstream (measured publicly by **MTEB** retrieval scores).
2. **Storage/index cost on Neon** — every vector lives in pgvector on Neon. [ADR 0015](./0015-neon-serverless-postgres.md) already flagged that ~400k × 1536-dim float32 ≈ ~2.4 GB + HNSW overhead can exceed Neon's free storage, and pointed at **256–512 dims** (or `halfvec`) as the mitigation.
3. **Cost per token** — the whole corpus is embedded at ingestion **and** every query is embedded at request time; $/1M tokens compounds.
4. **Availability on Azure OpenAI** — we are committed to Azure OpenAI / Foundry ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0010](./0010-foundry-model-platform-no-dedicated-ai-gateway.md)); a model not offered there is out of scope.
5. **Dimension reduction** — can we ask for fewer dimensions *without* retraining, to satisfy force 2 while keeping most quality?

The realistic Azure OpenAI candidates:

| Model | MTEB retrieval ~ | Default dims | Dim reduction | $/1M tokens ~ |
|---|---|---|---|---|
| `text-embedding-ada-002` (legacy) | ~61.0 | 1536 (fixed) | ❌ | ~0.10 |
| **`text-embedding-3-small`** | ~62.3 | 1536 (reducible) | ✅ | **~0.02** |
| `text-embedding-3-large` | ~64.6 | 3072 (reducible) | ✅ | ~0.13 |

_(figures are public, approximate orders of magnitude)_

## Decision
Use **`text-embedding-3-small`**, requested at a **reduced dimension of 512**, as the embedding model for the MVP.

- Deployed on Azure OpenAI as deployment `text-embedding-3-small` (provisioned via Terraform — `infrastructure/terraform/environments/dev`).
- The vector is stored in pgvector with **512 dimensions** (the `embedding` table / `vector(512)` column), respecting the Neon storage budget ([ADR 0015](./0015-neon-serverless-postgres.md)).
- The **model + dimension are recorded per embedding row as `model_version`** (e.g. `text-embedding-3-small@512`) so the corpus can be re-embedded with a different model/dimension **without destroying prior vectors** (FR14, Story 3.2 AC3). Mixing dimensions in one index is not allowed by pgvector, so a model/dimension change is a versioned re-embedding, not an in-place edit.

### Why reduced to 512 (the decisive factor)
`text-embedding-3-*` are trained with **Matryoshka Representation Learning**: the most important information is concentrated in the leading dimensions, so a prefix of the vector (e.g. the first 512 of 1536) is still highly useful. Truncating is a first-class, supported operation (the API `dimensions` parameter) — unlike `ada-002`, where truncation would wreck the vector. This is what lets a *small, cheap* model also be *storage-cheap* on Neon without a big quality loss. 512 is the balance point between 256 (cheapest, measurable quality drop) and 1536 (full quality, ~3× storage).

## Consequences
**Positive**
- **Cheapest option that also beats the legacy model**: `3-small` is ~5× cheaper than `ada-002` *and* scores higher. Corpus + query embedding stays in the cents range for dev.
- **Fits Neon** (force 2): 512-dim vectors are ~⅓ of 1536-dim → the ~2.4 GB projection in ADR 0015 drops to well under 1 GB for the same corpus, keeping us inside Neon's budget.
- **No architecture change**: it is still pgvector + the pluggable `LLMClient.embed` port ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md)); only a config value (deployment name + dimension).
- **Reversible by design**: `model_version` tagging means upgrading to `3-large` later is additive (re-embed into a new vector column/table), never destructive (FR14).

**Negative / risks**
- **Slightly below `3-large` on quality** (~2 MTEB points, plus the truncation to 512 gives up a little more). Accepted for MVP; the eval harness (Story 3.6 / Ragas, [ADR 0016](./0016-rag-evaluation-custom-plus-ragas.md)) is the objective gate that decides whether that gap hurts real retrieval.
- **Dimension is baked into the pgvector column type** (`vector(512)`): changing it is a migration + re-embedding, not a toggle. Mitigated by the `model_version` versioning plan.
- **Pay-as-you-go account** (no student credit on the gmail subscription) — real but negligible spend; tracked per `docs/runbooks/dev-on-azure-cost-control.md`.

**Neutral**
- The Azure endpoint + key are secrets in `.env` / `SecretsProvider`, never committed (consistent with ADR 0007).

## Alternatives Considered
- **`text-embedding-3-large` @ 1024/3072:** best quality, but ~6.5× cost and 2× storage for ~2 MTEB points. Not justified until eval proves the MVP model insufficient. This is the primary upgrade path.
- **`text-embedding-ada-002`:** legacy — worse quality, 5× cost, no dimension reduction. No reason to choose it today.
- **An open/self-hosted embedding model (e.g. BGE, E5) on our own compute:** removes per-token cost and keeps data on-prem, but adds serving/ops burden and GPU cost, and breaks the "cloud for models only" posture ([ADR 0012](./0012-local-first-dev-cloud-models-only.md)). Revisit if data residency or volume economics demand it.
- **Full 1536 dims (no reduction):** maximum quality for `3-small`, but ~3× Neon storage/index — rejected on ADR 0015 budget unless `halfvec` + paid tier is adopted.

## Revisit When
- **Eval (Ragas, Story 3.6) shows retrieval recall/precision below target** → bump to 512→1024 dims, or to `text-embedding-3-large` (one Terraform variable + a versioned re-embedding).
- **Data residency (EU)** becomes a hard requirement that Azure OpenAI's region can't satisfy → a self-hosted/EU-region embedding model.
- **Corpus grows** enough that even 512-dim vectors strain Neon → `halfvec`, a paid Neon tier, or a dedicated vector store (reopens [ADR 0001](./0001-vector-store-pgvector.md)).
