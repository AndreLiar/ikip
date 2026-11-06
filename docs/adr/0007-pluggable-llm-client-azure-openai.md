# 0007. Azure OpenAI via a pluggable `LLMClient` adapter

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** FR10, FR15, FR16, FR31, FR32 · NFR2, NFR12 · Stories 3.2, 3.5, 5.4, 5.5 · `../architecture.md` (Tech Stack, Components) · relates to [ADR 0003](./0003-local-first-ports-and-adapters.md)

## Context
IKIP needs both **chat/generation** (grounded, cited answers; abstention) and **embeddings** (versioned, for pgvector). The provider choice affects cost, latency, data residency and the Azure production story, but the platform must not be hard-coded to one vendor: prompts and model configs are versioned and regression-gated (Story 5.5), embeddings are re-generated across model versions (Story 3.2), and per-query token/cost must be tracked (FR31). The brief's cost model is built on Azure OpenAI (e.g., GPT-4.1-mini-class rates) in France Central / West Europe.

## Decision
Use **Azure OpenAI** as the default provider for both generation and embeddings, accessed **only through an `LLMClient` adapter interface** (in `packages/ai-clients`, consistent with [ADR 0003](./0003-local-first-ports-and-adapters.md)). The interface abstracts completion/streaming and embedding calls, carries **model + prompt configuration as versioned inputs**, and surfaces **token usage/cost and latency** for tracing (FR31, Story 5.4). No service calls a provider SDK directly. The same adapter is used locally (API calls) and on Azure.

## Consequences
**Positive**
- Single Azure-native path for generation + embeddings → coherent cost model, data residency (EU region) and Entra/Key Vault integration for prod.
- Provider is swappable (other hosted or self-hosted models) without touching RAG logic — supports model-version management and controlled experiments (Stories 3.2, 5.5).
- Centralized place to enforce token/cost tracking, retries, timeouts and streaming (NFR2: p95 TTFT < 5 s).
- Keeps local-first dev simple: only AI calls are remote (NFR17), no GPU required.

**Negative / risks**
- Dependency on Azure OpenAI model lifecycle/availability and quota per region (must confirm model availability before relying on a specific model).
- Embedding-model changes force re-embedding and index rebuilds (handled by versioned embeddings, Story 3.2).
- Abstraction must expose streaming and token-usage uniformly across providers to avoid leaky differences.

**Neutral**
- Reranking may use a separate model/service; it sits behind its own step regardless.

## Alternatives Considered
- **OpenAI API (direct, non-Azure):** similar models, but weaker fit with the Azure prod story (Entra ID, Key Vault, data residency, one bill). Rejected as default; remains an easy adapter if needed.
- **Self-hosted / open-weight models (e.g., via a local runtime):** no per-token fee and full control, but needs GPU/ops investment that conflicts with the no-GPU, lean-budget MVP (NFR17). Deferred; reachable via the same interface.
- **Hard-coding the provider SDK (no interface):** simplest short-term, but blocks model experiments, provider switching and uniform cost/trace capture. Rejected (violates NFR12, undermines Stories 5.4/5.5).

## Revisit When
- Azure OpenAI cost, quota, latency or model availability no longer meets targets (swap adapter / add fallback), **or**
- A self-hosted or alternative-provider model demonstrably improves quality/cost and the ops cost is justified, **or**
- Multi-provider routing/fallback becomes a requirement (introduce a routing adapter behind `LLMClient`).
