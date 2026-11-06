# Tech Stack

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

> This is the definitive, single-source technology selection. Versions are pinned at implementation start (lockfiles in repo); use latest stable within the stated major unless a story says otherwise.

| Category            | Technology                                                   | Role / Notes                                        |
| ------------------- | ------------------------------------------------------------ | --------------------------------------------------- |
| Language (backend)  | Python 3.12+                                                 | Backend + services                                  |
| Language (frontend) | TypeScript                                                   | Web app                                             |
| Backend framework   | FastAPI + Pydantic v2                                        | REST APIs, validation                               |
| Frontend framework  | Next.js (App Router) + React                                 | Technician/admin UI                                 |
| Database            | **Neon** serverless Postgres 16 + pgvector (Docker optional offline) | Metadata, full-text, vectors; scale-to-zero ([ADR 0015](../adr/0015-neon-serverless-postgres.md)) |
| Migrations          | Alembic                                                      | Safe, reversible migrations (NFR13)                 |
| Data orchestration  | Dagster                                                      | Knowledge-base pipeline, assets, schedules, sensors |
| RAG orchestration   | LangGraph + LangChain                                        | Stateful technician-facing workflow                 |
| Async / queue       | Redis (Docker or Redis Cloud Free in dev) → Azure Service Bus | `JobQueue` port; durable prod queue on Service Bus ([ADR 0009](../adr/0009-caching-strategy.md) Redis note) |
| Cache               | Redis (Docker or Redis Cloud Free in dev) → Azure Cache      | `Cache` port ([ADR 0009](../adr/0009-caching-strategy.md))  |
| Object storage      | **Cloudflare R2** (S3-compatible, all envs; MinIO optional offline) | `ObjectStorage` port, one S3 adapter; zero egress ([ADR 0014](../adr/0014-cloudflare-r2-object-storage.md)) |
| PDF processing      | PyMuPDF + Docling                                            | Native extraction, layout, tables                   |
| OCR                 | Tesseract (local) → Azure Document Intelligence             | Two-stage (cost control)                            |
| Data validation     | Pydantic + Pandera                                           | Content/quality validation (Story 2.4)              |
| LLM + embeddings    | Azure OpenAI via `LLMClient` adapter                       | Pluggable provider                                  |
| Tracing / LLMOps    | OpenTelemetry + **Langfuse** (Cloud Hobby free for dev/MVP; self-host option); pytest | OTel instruments; Langfuse = LLM-native traces/prompts/eval/cost ([ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)) |
| Observability       | Prometheus + Grafana (local) → Azure Monitor + App Insights | `Telemetry` interface                             |
| PII detection       | **Presidio** (open-source, self-hosted)                      | PII detect/anonymize via `PiiScrubber` port (NFR16, Story 6.4); not Content Safety |
| Auth                | Local dev accounts / OIDC → Microsoft Entra ID              | Tenant + role in token                              |
| Secrets             | `.env` (local) → Azure Key Vault + managed identities     | `SecretsProvider` interface                       |
| Containerization    | Docker + Docker Compose                                      | Local dev (NFR17)                                   |
| Deployment target   | Azure Container Apps                                         | API, web, workers                                   |
| Container registry  | Azure Container Registry                                     | Images                                              |
| IaC                 | Terraform                                                    | dev/staging/prod (NFR13)                            |
| CI/CD               | GitHub Actions                                               | Quality + security + safety gates (NFR14)           |
| Testing             | pytest, Playwright, k6 (perf)                                | Unit/integration/retrieval/security/perf            |

> **Deliberately excluded at MVP (add only when justified):** Kubernetes/AKS, Azure AI Search, dedicated managed Redis, provisioned-throughput LLM, always-on GPU, large Document Intelligence bills. See [ADR 0005](../adr/0005-managed-containers-not-kubernetes.md). _"Dedicated managed Redis" means a separate paid Azure Cache tier — not caching itself: the MVP caches on the existing local Redis + Postgres behind a `Cache` port (see caching note below)._

> **Caching:** layered cache behind a `Cache` port — embedding reuse (Postgres), query-embedding + exact-match answer cache (Redis), with tenant/version-safe keys and invalidation on ingestion. Fuzzy/semantic caching deferred. See [ADR 0009](../adr/0009-caching-strategy.md).

> **Vector store rationale:** PostgreSQL + pgvector is chosen over a dedicated vector DB (Qdrant) or managed search (Azure AI Search) because IKIP's retrieval is hybrid-and-relational (vector + full-text + equipment/version filters + tenant/document ACL in one query), keeps tenant isolation and versioning/deletion transactional in one system, and preserves local↔cloud parity at MVP scale. Retrieval sits behind the `VectorStore` interface, so switching stores later is a planned adapter swap. Full decision, trade-offs and revisit triggers: [ADR 0001](../adr/0001-vector-store-pgvector.md) and [ADR 0004](../adr/0004-hybrid-retrieval-on-postgres.md).

> **Model platform & AI gateway:** Microsoft Foundry (Azure AI Foundry) is the model platform (deployment/versioning, unified endpoint, content safety, eval/tracing); **no dedicated AI gateway at MVP** — the `LLMClient` port is the logical gateway. See [ADR 0010](../adr/0010-foundry-model-platform-no-dedicated-ai-gateway.md).

> **Related decisions:** dual orchestration [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md) · ports & adapters [ADR 0003](../adr/0003-local-first-ports-and-adapters.md) · pluggable LLM provider [ADR 0007](../adr/0007-pluggable-llm-client-azure-openai.md) · Next.js over plain React [ADR 0008](../adr/0008-nextjs-over-plain-react.md) · caching [ADR 0009](../adr/0009-caching-strategy.md) · Foundry / no AI gateway [ADR 0010](../adr/0010-foundry-model-platform-no-dedicated-ai-gateway.md).
