# MISSION-013 — Embeddings generation & version management (Epic 3, Story 3.2)

**Mode:** Guidé (Azure provisioning + model/dimension decision) → Autonome (impl) + knowledge transfer.
**Objective:** turn chunks into vectors via Azure OpenAI and store them in pgvector with per-row model versioning, so retrieval has a semantic index and re-embedding never destroys prior vectors.
**Maps to:** Epic 3 / Story 3.2. Builds on Story 3.1 (chunks) and [ADR 0007](../../../adr/0007-pluggable-llm-client-azure-openai.md).

## Decisions (user asked "why text-embedding-3-small?" + "why not Foundry?")
- **Model + dimension:** `text-embedding-3-small` @ **512 dims** (Matryoshka reduction) — [ADR 0020](../../../adr/0020-embedding-model-text-embedding-3-small.md). Cheapest option that still beats ada-002; 512 dims fit Neon ([ADR 0015](../../../adr/0015-neon-serverless-postgres.md)).
- **Provisioning via Terraform (IaC), not the Foundry portal:** same underlying `Microsoft.CognitiveServices` resource, but reproducible/reviewable/destroyable — see [decisions.md](./decisions.md).
- **Deployment SKU:** `DataZoneStandard` (EU data zone) over `GlobalStandard`, for EU residency posture. `Standard` is not offered for this model (discovered at apply time).

## Acceptance criteria
1. Embedding adapter via Azure OpenAI behind the pluggable `EmbeddingClient` port (LangChain's `AzureOpenAIEmbeddings` wrapped behind the port, ADR 0021). — **[verified]** (live Azure test: 2 passed, 512-dim)
2. Embedding records store chunk_id, model_version, vector in pgvector on Neon. — **[verified]** (`Embedding` model `vector(512)` + reversible migration; DB tests) — DB tests gated on TEST_DATABASE_URL (CI ephemeral Neon branch)
3. Model version tracked; re-embedding doesn't destroy prior vectors (FR14). — **[verified]** (unique `(chunk_id, model_version)`; additive + idempotent store; DB test `test_new_model_version_is_additive_not_destructive`)
4. Dimension chosen mindful of Neon storage (512 via Matryoshka). — **[verified]** (ADR 0020; live call returns 512-dim vector)
5. Tests cover generation + version tagging (fake client in CI; real Azure live). — **[verified]** (7 pure fake-client tests + 5 DB store tests + 2 live Azure tests)

Also honours ADR 0021 acceptance: cross-tenant isolation + citation integrity + model-version coexistence tests present. Ranking-regression + perf benchmark land with retrieval (Stories 3.3/3.4).

## Infra prerequisite (done)
Azure OpenAI provisioned as code (`infrastructure/terraform/environments/dev/`): resource group + OpenAI account + `text-embedding-3-small` deployment. `.env` filled. Live embedding verified (HTTP 200, 512 dims). — **[verified]**, see [execution.md](./execution.md).

## Deliverables (planned)
- `ikip_common/llm/` — `LLMClient` port (`embed`) + `AzureOpenAIClient` adapter + `FakeEmbeddingClient` (deterministic, CI).
- `ikip_common/db/models.py` — `Embedding` model (`vector(512)`, `model_version`) + reversible migration (pgvector column).
- `ikip_common/db/embeddings.py` — generation + versioned store (additive re-embedding).
- Tests: pure/fake-client (CI) + DB-gated (pgvector) + a live Azure test skipped when `AZURE_OPENAI_*` unset.
- [ADR 0020](../../../adr/0020-embedding-model-text-embedding-3-small.md) · [decisions.md](./decisions.md) · [execution.md](./execution.md) · [tutorial.md](./tutorial.md).

## Concepts
Introduces [embeddings](../../concepts/embeddings.md) (vectors, dimensions, Matryoshka, model_version, cost, port+fake). Reuses [chunking](../../concepts/chunking.md), [why-rag](../../concepts/why-rag.md), [object-storage](../../concepts/object-storage.md) (same port/adapter/fake pattern), [config-12-factor](../../concepts/config-12-factor.md).
