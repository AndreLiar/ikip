# 0003. Local-first, cloud-ready via ports & adapters (interface-driven infrastructure)

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** NFR12, NFR16, NFR17 · FR... (all infra-dependent features) · Stories 1.2, 2.1, 3.2, 5.6, 6.4, 6.6 · `../architecture.md` (Architectural and Design Patterns, Infrastructure and Deployment)

## Context
IKIP must be developed and runnable entirely on a 16 GB laptop with only AI API calls remote (NFR17), yet deploy to Azure for production without rewriting core business logic. Each infrastructure dependency has a different local vs. cloud implementation:

| Capability | Local | Azure |
|---|---|---|
| Object storage | Cloudflare R2 (MinIO optional offline) | Cloudflare R2 ([ADR 0014](./0014-cloudflare-r2-object-storage.md)) |
| Job queue | Redis (Docker or Redis Cloud Free) | Service Bus |
| Vector store | Neon Postgres + pgvector (Docker optional offline) | Neon Postgres + pgvector ([ADR 0015](./0015-neon-serverless-postgres.md)) |
| LLM/embeddings | Azure OpenAI (API) | Azure OpenAI |
| Secrets | `.env` | Key Vault + managed identities |
| Telemetry | OpenTelemetry + Prometheus/Grafana | Azure Monitor + App Insights |
| Cache | Redis (Docker or Redis Cloud Free) | Azure Cache / paid Redis |
| PII detection | Presidio (self-hosted) | Presidio (self-hosted) |

If business logic imported cloud SDKs directly, the laptop story and local↔cloud portability would be lost, and testing would require cloud resources.

> **Controlled Cloudflare R2 (`ObjectStorage` adapter, S3-compatible — [ADR 0014](./0014-cloudflare-r2-object-storage.md)):** private buckets (no public access), scoped R2 API tokens via `SecretsProvider`/Key Vault (never committed), short-lived presigned URLs for the document viewer only, raw/cleaned/curated separation (NFR15), and lifecycle/retention. Specified in Story 6.4 (AC 5) and tied to Story 6.5. MinIO can back the same adapter for offline tests.

## Decision
Adopt **ports & adapters (hexagonal architecture)**: core logic depends only on interfaces defined in `packages/common` — `ObjectStorage`, `JobQueue`, `VectorStore`, `LLMClient`, `SecretsProvider`, `Telemetry`, `Cache` ([ADR 0009](./0009-caching-strategy.md)) and `PiiScrubber` (Presidio, Story 6.4). Each interface has a **local adapter** and an **Azure/prod adapter**; the concrete implementation is selected by configuration/environment. **No service may import an Azure SDK directly** — it goes through the interface. _(Note: some ports are backend-swappable rather than strictly local-vs-Azure — e.g., `PiiScrubber` is Presidio in both, `Cache` is Redis in both.)_

## Consequences
**Positive**
- Full stack runs locally in Docker Compose; only AI calls are remote (NFR17).
- Local↔cloud migration becomes an **infrastructure/operations exercise, not a code rewrite** (NFR12).
- Interfaces are trivially mockable → fast, hermetic unit/integration tests.
- Individual dependencies can be swapped independently (e.g., the `VectorStore` adapter swap in [ADR 0001](./0001-vector-store-pgvector.md)).

**Negative / risks**
- Up-front cost of defining and maintaining interfaces plus two adapters each.
- Risk of leaky abstractions if an adapter exposes provider-specific behavior; must be guarded in review (coding standards).
- Local and Azure adapters can drift in behavior; mitigated by a shared contract test suite per interface.

**Neutral**
- A thin amount of adapter boilerplate per capability.

## Alternatives Considered
- **Code directly against Azure SDKs:** simplest short-term, but breaks local-first dev, couples logic to one cloud, and forces cloud resources for tests. Rejected (violates NFR12, NFR17).
- **Run against Azure in dev too (no local stack):** ongoing cost, slower loop, network dependency, no offline work. Rejected.
- **A heavyweight abstraction framework / service mesh:** over-engineered for MVP; the six narrow interfaces suffice. Rejected.

## Revisit When
- An interface accumulates provider-specific leakage that can't be cleanly abstracted (reconsider that specific port), **or**
- The platform standardizes on a single environment such that dual adapters add no value, **or**
- A capability's local and cloud semantics diverge so much that a shared contract can't be maintained.
