# Industrial Knowledge Intelligence Platform (IKIP) — Product Requirements Document (PRD)

_BMAD artifact 2 of 3 — PM output. Builds on `brief.md`; feeds `architecture.md` and the sharded epics._

---

## Goals and Background Context

### Goals
- Enable industrial professionals to retrieve accurate, traceable, version-aware technical information via natural-language questions and hybrid search.
- Deliver evidence-grounded answers with resolvable document + page + section citations, and reliable abstention when evidence is insufficient.
- Provide a secure multi-tenant SaaS with document- and tenant-level access control enforced before retrieval.
- Build a reproducible raw-to-curated data engineering pipeline with data-quality reporting and lineage.
- Make retrieval and generation measurable, observable and safely updatable (LLMOps).
- Ship local-first and deploy to Azure without rewriting core business logic.

### Background Context
Industrial maintenance organizations manage documentation for thousands of equipment units across many manufacturers, models and revisions. The documentation is fragmented across formats and systems, and generic AI tools are unsafe for this domain because they hallucinate procedures, ignore versions, leak across tenants and provide no evaluation or auditability. IKIP addresses this with a vertical, governed, measurable RAG platform. Full problem framing is in `brief.md`.

### Change Log
| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-11-01 | 0.1 | Initial PRD drafted from project brief (BMAD structuring) | PM |

---

## Requirements

### Functional Requirements

- **FR1** The system shall ingest documents from PDF, HTML, CSV, JSON and Excel files, and via API/connector adapters.
- **FR2** The system shall support scheduled source synchronization and authorized crawling of configured sources.
- **FR3** The system shall extract text from native-digital PDFs and fall back to OCR for scanned pages, preserving page references and layout structure.
- **FR4** The system shall extract tables and diagram references with their originating page numbers.
- **FR5** The system shall detect exact and near-duplicate documents.
- **FR6** The system shall classify documents and normalize their metadata.
- **FR7** The system shall version documents and track source lineage from raw file to curated asset.
- **FR8** The system shall process ingestion incrementally with retries, dead-letter handling, and controlled reprocessing/backfill.
- **FR9** The system shall perform structure-aware and semantic chunking of document content.
- **FR10** The system shall generate embeddings and manage embedding-model versions.
- **FR11** The system shall support lexical (BM25/full-text) search and vector-similarity search.
- **FR12** The system shall combine lexical and vector results into hybrid retrieval with reranking.
- **FR13** The system shall support metadata and equipment-model/revision filters on retrieval.
- **FR14** The system shall perform version-aware retrieval that distinguishes applicable from obsolete content.
- **FR15** The system shall synthesize evidence across multiple documents and generate answers grounded only in retrieved evidence.
- **FR16** The system shall attach citations to generated answers resolving to document, version, page and section.
- **FR17** The system shall abstain (explicitly decline) when retrieved evidence is insufficient, rather than inventing content.
- **FR18** The system shall surface safety warnings and uncertainty present in or implied by the evidence.
- **FR19** The system shall provide organization, workspace and user management.
- **FR20** The system shall provide authentication and role-based authorization.
- **FR21** The system shall enforce tenant-level and document-level access control before retrieval and before source access.
- **FR22** The system shall provide file upload, document browsing, categorization and version viewing.
- **FR23** The system shall provide a document viewer that opens the cited source PDF at the referenced page.
- **FR24** The system shall provide an equipment catalog (manufacturer, model, revision, asset ID) with document associations.
- **FR25** The system shall run ingestion as asynchronous jobs with status tracking and job history.
- **FR26** The system shall record conversation history and allow users to give feedback on answers and sources.
- **FR27** The system shall expose versioned REST APIs with documented contracts.
- **FR28** The system shall support usage quotas, API rate limits and audit logging.
- **FR29** The system shall provide retrieval evaluation against a gold dataset with benchmarking and regression checks.
- **FR30** The system shall provide end-to-end tracing from user query → retrieved chunks → model call → answer.
- **FR31** The system shall track latency, token usage and cost per query, and expose monitoring dashboards and alerts.
- **FR32** The system shall version prompt and model configurations and gate changes through a regression-test suite.
- **FR33** The system shall provide data retention and deletion workflows, and track document licensing/provenance.

### Non-Functional Requirements

- **NFR1** p95 retrieval latency shall be < 1.5 s under the defined test load.
- **NFR2** p95 time-to-first-token for answers shall be < 5 s under the defined test load.
- **NFR3** The deployed pilot shall target 99.5% monthly availability.
- **NFR4** The system shall demonstrate restore from backup within the agreed RPO/RTO.
- **NFR5** Ingestion shall achieve ≥ 98% successful processing for the supported clean-document corpus.
- **NFR6** Retrieval shall achieve Recall@5 ≥ 90% on the reviewed evaluation set.
- **NFR7** ≥ 98% of generated citations shall resolve to the correct document and location.
- **NFR8** ≥ 95% of factual claims in answers shall be supported by cited evidence (groundedness).
- **NFR9** The system shall pass 100% of predefined critical safety-abstention tests.
- **NFR10** Automated security tests shall show zero cross-tenant data disclosure.
- **NFR11** Data shall be encrypted in transit and at rest.
- **NFR12** All infrastructure-dependent integrations shall sit behind interfaces with swappable local and Azure implementations, so core business logic is portable local↔cloud.
- **NFR13** The system shall be deployable via Infrastructure as Code (Terraform/Bicep) across dev, staging and prod.
- **NFR14** CI/CD shall enforce automated quality and security gates before deployment.
- **NFR15** Raw files, cleaned content, document versions, search indexes and embeddings shall be logically separable so documents can be reprocessed/reindexed without losing original evidence.
- **NFR16** Secrets and PII shall be protected; secrets managed via a secrets provider (local `.env` / Azure Key Vault).
- **NFR17** The platform shall run on a developer laptop (16 GB RAM min): the **app** (FastAPI/Next.js) runs locally while backends are **managed** (Neon Postgres+pgvector, Cloudflare R2, Redis Cloud, Langfuse Cloud, Azure OpenAI/Foundry). No local Docker Compose is shipped; a **fully-offline mode remains possible in principle** via the ports ([ADR 0003](adr/0003-local-first-ports-and-adapters.md)) by pointing adapters at local MinIO/Postgres/Redis, but is not provided out of the box. Hermetic DB tests use a CI Postgres service container. Azure is used for deployment and cloud learning at deploy time — see [ADR 0012](adr/0012-local-first-dev-cloud-models-only.md), [ADR 0014](adr/0014-cloudflare-r2-object-storage.md), [ADR 0015](adr/0015-neon-serverless-postgres.md).
- **NFR18** The system shall defend against prompt injection and malicious document content, and restrict tool access / safe-handle retrieved content.
- **NFR19** Caching shall never weaken tenant isolation or version-awareness: any answer/retrieval cache entry shall be tenant-partitioned, encode equipment model/revision and current document-version set, be invalidated on version supersession, and never alter the abstention decision (see [ADR 0009](adr/0009-caching-strategy.md)).

---

## User Interface Design Goals

### Overall UX Vision
A fast, trustworthy, evidence-first workspace for technicians under time pressure. Every answer is accompanied by its sources; the user can always jump from a claim to the exact manual page. Uncertainty and safety warnings are first-class, not hidden. Administration (documents, tenants, ingestion, quality, evaluation) is a separate, clean operational surface.

### Key Interaction Paradigms
- Equipment-scoped search and chat: pick/confirm manufacturer + model + revision, then ask.
- Answer → citation → source page: one click from a cited claim to the highlighted PDF page.
- Explicit "insufficient evidence" states instead of confident wrong answers.
- Async job feedback: ingestion and reprocessing show live status, not spinners that never resolve.

### Core Screens and Views
- Login / tenant selection
- Search & AI assistant (chat with citations, filters, abstention states)
- Document viewer (PDF at cited page, with highlights)
- Document management (upload, browse, categorize, versions)
- Equipment catalog (models, revisions, asset associations)
- Ingestion & job status / history
- Quality management (parse validation, duplicates, failed jobs)
- Admin: organizations, workspaces, users, roles
- Operations dashboard (latency, errors, pipeline health, token cost)
- Evaluation dashboard (Recall@K, citation correctness, groundedness, regressions)

### Accessibility
WCAG AA target for the technician-facing surfaces.

### Branding
Neutral, professional, industrial. Clear typographic hierarchy; high-contrast, legible-at-a-glance states for warnings/uncertainty. No decorative flourishes that compete with safety information.

### Target Device and Platforms
Web Responsive — desktop-first for admin/operations; tablet-friendly for field technicians.

---

## Technical Assumptions

### Repository Structure
**Monorepo.** `apps/` (web, api), `services/` (ingestion, document-processing, indexing, retrieval, evaluation), `packages/` (common, ai-clients), `infrastructure/` (docker, terraform), `tests/`, `datasets/`, `docs/`.

### Service Architecture
**Modular services within a monorepo**, deployed as containers. Data-engineering orchestration via **Dagster**; AI/RAG orchestration via **LangGraph + LangChain**. Async work via a job-queue interface (Redis locally → Azure Service Bus). Deliberately **not** Kubernetes/microservices at MVP; managed containers (Azure Container Apps) first.

### Testing Requirements
**Full testing pyramid plus specialized suites:** unit, integration, retrieval-quality (gold dataset), security (tenant isolation, prompt injection), and performance. CI enforces quality + security gates. Retrieval and safety are regression-gated.

### Additional Technical Assumptions
- Language: Python 3 (backend/services), TypeScript (frontend).
- Backend: FastAPI + Pydantic. Frontend: Next.js + React.
- Database: Neon serverless Postgres + pgvector (metadata, full-text, vectors; scale-to-zero; Docker Postgres optional offline — [ADR 0015](adr/0015-neon-serverless-postgres.md)).
- Object storage: Cloudflare R2 (S3-compatible, all envs; zero egress), one S3 adapter; MinIO optional for offline tests ([ADR 0014](adr/0014-cloudflare-r2-object-storage.md)).
- PDF/OCR: PyMuPDF + Docling; Tesseract (local) → Azure Document Intelligence for pages needing enhanced OCR.
- LLM + embeddings: Azure OpenAI via a pluggable `LLMClient` adapter.
- Tracing/LLMOps: OpenTelemetry (instrumentation) + Langfuse (self-hosted, LLM-native traces/prompts/eval/cost); pytest + custom gold dataset. See [ADR 0013](adr/0013-llmops-observability-otel-langfuse.md) and `architecture/llmops-stack.md`.
- Observability: OpenTelemetry + Prometheus/Grafana (local) → Azure Monitor + Application Insights.
- IaC: Terraform; CI/CD: GitHub Actions; Containerization: Docker.
- Interface-driven infra abstractions (`ObjectStorage`, `JobQueue`, `VectorStore`, `LLMClient`, `SecretsProvider`, `Telemetry`, `Cache`, `PiiScrubber`) with local + Azure/prod implementations.
- Two-stage document processing to control ingestion cost (local native extraction first; paid OCR only when needed).
- Candidate ingestion sources and evaluation datasets are cataloged in `data-sources.md`. The primary in-scope corpus is industrial equipment manuals (Category 1); all other categories are reference / future-vertical / evaluation only. Every source requires a license + provenance check (see Story 6.5) before ingestion.
- The RAG difficulty dimensions this PRD is designed around (permission-aware multi-tenancy, version-aware/temporal retrieval, visual/table handling, conflicting sources, abstention, evaluation) — and the ones deliberately deferred (enterprise SaaS connectors, structured-data/XBRL querying, advanced drawing interpretation) — are enumerated and traced to specific FR/NFR/stories in `rag-design-challenges.md`.

---

## Epic List

1. **Epic 1 — Foundation & Platform Core:** Monorepo, CI/CD, Docker dev environment, FastAPI + PostgreSQL walking skeleton, authentication, and multi-tenant data foundation with a health-check endpoint and baseline tests.
2. **Epic 2 — Data Engineering & Ingestion Pipeline:** Dagster-orchestrated raw→curated pipeline: connectors, parsing + OCR, cleaning/normalization, deduplication, document versioning, metadata enrichment, quality validation, lineage — with job status and reprocessing.
3. **Epic 3 — Retrieval & RAG Engineering:** Chunking, embeddings (versioned), BM25 + vector + hybrid retrieval with reranking and equipment/version filters, and a LangGraph grounded-answer service with citations and abstention — all measurable.
4. **Epic 4 — Enterprise Application & SaaS:** Document management, equipment catalog, search + AI assistant UI, document viewer at cited page, admin (orgs/workspaces/users/roles), conversation history and feedback, versioned APIs, quotas/rate limits/audit logging — with access control enforced end-to-end.
5. **Epic 5 — LLMOps, Evaluation & Observability:** Gold evaluation datasets, retrieval + groundedness + citation + safety evaluation harness, end-to-end tracing, prompt/model config versioning with regression gates, and cost/latency/health dashboards with alerts.
6. **Epic 6 — Security, Governance & Cloud Operations:** Threat model, tenant-isolation and prompt-injection security tests, encryption, audit logging, data retention/deletion and provenance, Terraform IaC for dev/staging/prod, Azure deployment, and tested backup/recovery runbooks.

### Post-MVP Expansion Epics (sequenced after Epics 1–6; not part of the initial production scope)

7. **Epic 7 — Enterprise Knowledge Connectors:** Dedicated SaaS connectors (SharePoint, Confluence, ticketing, email/transcripts), per-source permission mapping, incremental synchronization and contradictory-knowledge handling.
8. **Epic 8 — Structured-Data & Financial Retrieval:** Ingest structured statements/XBRL, hybrid structured+unstructured retrieval, numerical-accuracy and table-to-value querying, and comparative analysis (finance vertical).
9. **Epic 9 — Advanced Multimodal Retrieval:** Engineering-drawing/schematic and visual-table extraction, multimodal embeddings/retrieval, and visual citations.

---

## Epic 1 — Foundation & Platform Core

**Goal:** Stand up a deployable walking skeleton: a monorepo with CI, a managed-services-first dev setup (app local; Neon/R2/Redis Cloud/Langfuse via `.env`, with optional local Docker backends for offline work), a FastAPI backend talking to Postgres, authentication, and the multi-tenant data foundation — so every later epic builds on a secure, tested base and can be run end-to-end from day one.

> **Infra context (decided after this epic was first drafted):** default dev backends are managed — Neon (Postgres+pgvector, ADR 0015), Cloudflare R2 (object storage, ADR 0014), Redis Cloud (ADR 0009), Langfuse Cloud (ADR 0013). No local Docker Compose is provided — the app (local) talks to managed services via `.env`. Offline/self-hosted backends remain possible via the ports (ADR 0003) but are not shipped; hermetic DB tests use a CI Postgres service container.

### Story 1.1 Monorepo & Repository Conventions
As a developer, I want a monorepo scaffold with documented conventions, so that all services share source and contributors follow one structure.
**Acceptance Criteria:**
1. Monorepo created with `apps/`, `services/`, `packages/`, `infrastructure/`, `tests/`, `datasets/`, `docs/`.
2. README documents structure, setup, and contribution/branching conventions.
3. Linting/formatting configured for Python and TypeScript.
4. Architecture Decision Record (ADR) location and template exist. _(Already in place: `docs/adr/` with README + template — verify, don't recreate.)_

### Story 1.2 Configuration & Connectivity (managed-services-first)
As a developer, I want a typed configuration layer that loads all backend connections from `.env`, plus a connectivity "doctor", so that the app is configured 12-factor-style and I can verify each managed service before running anything.
**Acceptance Criteria:**
1. A shared, typed settings module (Pydantic `BaseSettings`) in `packages/common` loads all backend config from environment / `.env`; required values missing → fail fast with a clear error; no hard-coded secrets.
2. A connectivity check command (`doctor`) verifies each configured backend (Neon/Postgres, R2, Redis, Langfuse) and reports pass/fail per service without printing secrets.
3. Unit tests cover config loading/validation and are hermetic (no live services; env monkey-patched) so they run in CI.
4. No local Docker Compose is provided (dev uses managed services). Offline/self-hosted backends remain possible via the ports (ADR 0003) but are not shipped; DB-touching integration tests use an ephemeral Postgres service container in CI (Story 1.3/1.5).

### Story 1.3 FastAPI Backend Skeleton with Health Check
As a developer, I want a FastAPI service with a versioned health endpoint, so that we have a deployable backend baseline.
**Acceptance Criteria:**
1. FastAPI app exposes `GET /api/v1/health` returning service status plus the status of each configured dependency (Neon/Postgres, R2/object storage, Redis) — whichever the `.env` points at (managed or local).
2. Pydantic settings load configuration from environment (`.env`); invalid/missing required config fails fast with a clear error.
3. Structured logging is configured (no secrets in logs).
4. A unit test and an integration test for the health endpoint pass in CI (dependency checks mockable so CI needs no live managed services).

### Story 1.4 CI Pipeline & Baseline Testing
As a developer, I want GitHub Actions CI running lint and tests on every push, so that quality is enforced from the start.
**Acceptance Criteria:**
1. CI runs lint + unit/integration tests for backend (and frontend once present).
2. CI fails the build on lint or test failure.
3. Test coverage is reported.
4. CI status is required before merge.

### Story 1.5 Multi-Tenant Data Foundation
As an architect, I want the core tenant/user schema and tenant-scoping mechanism, so that isolation is built in from the first data model.
**Acceptance Criteria:**
1. Migrations create `tenant` and `user` tables with the fields in the data model.
2. Every tenant-owned table carries a tenant identifier and queries are tenant-scoped by default.
3. A migration tool (safe, reversible) is configured.
4. Tests prove a query in tenant A cannot read tenant B rows.

### Story 1.6 Authentication & Role-Based Authorization
As a user, I want to authenticate and receive a role, so that access is controlled from the foundation up.
**Acceptance Criteria:**
1. Authentication issues a session/token carrying tenant + role (local dev accounts/OIDC; Entra ID in prod).
2. Roles (e.g., admin, manager, technician) are defined and enforced by a reusable authorization dependency.
3. Protected endpoints reject unauthenticated/unauthorized requests.
4. Unit + security tests cover role enforcement and tenant binding.

---

## Epic 2 — Data Engineering & Ingestion Pipeline

**Goal:** Deliver a reproducible raw→curated document pipeline orchestrated by Dagster that ingests heterogeneous sources, extracts and cleans content (with OCR fallback), deduplicates and versions documents, enriches metadata, validates quality and tracks lineage — exposed as asynchronous jobs with status and reprocessing.

> **Source corpus:** the connectors in this epic target the candidate sources cataloged in `data-sources.md`. MVP ingestion uses the **Category 1 industrial manuals** (licensed starter corpus); other categories are out of initial scope. Each source must pass a license + provenance check (Story 6.5) before being enabled.

> **Infra context:** object storage = Cloudflare R2 (S3, ADR 0014; MinIO optional offline); database = Neon Postgres+pgvector (ADR 0015); async queue/DLQ = Redis (dev) → Azure Service Bus (prod, durable). **Dagster** runs locally in Docker during dev and as Container Apps Jobs in prod (ADR 0002/0005) — the one heavy local component vs the managed data backends.

### Story 2.1 Object Storage & Ingestion Job Model
As an engineer, I want raw files stored in object storage and tracked by an ingestion-job record, so that every source file is traceable through processing.
**Acceptance Criteria:**
1. `ObjectStorage` port with a Cloudflare R2 (S3) implementation stores raw files (ADR 0014); MinIO backs the same port for offline tests.
2. `ingestion_job` table records source, state, timestamps and error info.
3. Raw, cleaned and curated artifacts are stored in logically separate locations (buckets/prefixes), per NFR15.
4. Tests cover upload/retrieve and job state transitions (storage port mockable so CI needs no live R2).

### Story 2.2 Source Connectors & Scheduled Sync
As an admin, I want connectors for file and API sources with scheduled synchronization, so that documentation stays current.
**Acceptance Criteria:**
1. Connectors ingest PDF, HTML, CSV, JSON, Excel and an API adapter.
2. Dagster schedules/sensors trigger synchronization for configured sources.
3. Authorized crawling respects source access rules and licensing metadata.
4. New/changed documents are detected and queued for processing.

### Story 2.3 PDF Extraction with OCR Fallback & Layout/Table Capture
As an engineer, I want native-PDF extraction with OCR fallback that preserves page/layout/tables, so that downstream retrieval has accurate, locatable content.
**Acceptance Criteria:**
1. Native-digital PDFs extracted with PyMuPDF/Docling, preserving page references.
2. Scanned/low-quality pages routed to OCR via a two-stage, cost-controlled strategy: stage 1 = local Tesseract ($0, default); stage 2 = Azure Document Intelligence (paid, optional) only for pages needing enhanced OCR/table/layout recognition.
3. Tables and diagram references extracted with originating page numbers.
4. Extraction quality is scored; low-quality extractions are flagged.

### Story 2.4 Cleaning, Normalization & Metadata Enrichment
As an engineer, I want extracted content cleaned, normalized and enriched with metadata, so that documents are consistent and classifiable.
**Acceptance Criteria:**
1. Cleaning/normalization produces consistent curated text with structure preserved.
2. Documents are classified and metadata normalized per schema.
3. Content validation uses schema/data-quality checks (e.g., Pandera/Pydantic).
4. Validation failures are recorded against the ingestion job.

### Story 2.5 Deduplication & Document Versioning
As an engineer, I want exact/near-duplicate detection and document versioning, so that we track revisions and avoid redundant content.
**Acceptance Criteria:**
1. Exact duplicates detected via checksum; near-duplicates via similarity.
2. `document` and `document_version` records capture revision, publication/effective dates and checksum.
3. A new version supersedes prior versions without deleting original evidence.
4. Tests cover duplicate detection and version supersession.

### Story 2.6 Lineage, Quality Reporting & Reprocessing
As an operator, I want lineage tracking, a data-quality report and controlled reprocessing/backfill, so that I can trust and maintain the knowledge base.
**Acceptance Criteria:**
1. Lineage links raw file → curated content → document version as Dagster assets.
2. A data-quality report summarizes success rate, failures and duplicates per run.
3. Failed jobs route to a dead-letter path with retry, via the `JobQueue` port (Redis in dev → Azure Service Bus in prod for durability).
4. Documents can be reprocessed/backfilled (e.g., after a parser change) via an asset-aware re-run without full rebuild.

---

## Epic 3 — Retrieval & RAG Engineering

**Goal:** Turn curated documents into a measurable retrieval + grounded-answer service: structure-aware chunking, versioned embeddings, BM25 + vector + hybrid retrieval with reranking and equipment/version filters, and a LangGraph workflow that synthesizes cited answers and abstains when evidence is missing.

### Story 3.1 Structure-Aware & Semantic Chunking
As an engineer, I want documents chunked by structure and semantics with section/page metadata, so that retrieval units are coherent and citable.
**Acceptance Criteria:**
1. `section` and `chunk` records capture hierarchy, heading, page range and metadata.
2. Chunking respects document structure (sections/headings) and semantic boundaries.
3. Each chunk retains a resolvable back-reference to document, version, page and section.
4. Tests validate chunk boundaries and metadata integrity.

### Story 3.2 Embedding Generation & Version Management
As an engineer, I want versioned embeddings via a pluggable client, so that we can re-embed and compare models safely.
**Acceptance Criteria:**
1. `LLMClient`/embedding adapter generates embeddings via Azure OpenAI (pluggable).
2. `embedding` records store chunk ID, model version and vector in pgvector (on Neon).
3. Embedding-model version is tracked; re-embedding does not destroy prior vectors needed for comparison.
4. Embedding dimension is chosen mindful of Neon storage (e.g., 256–512 dims and/or `halfvec`) so the vector index fits the tier — see ADR 0015.
5. Tests cover embedding generation and version tagging.

### Story 3.3 Lexical & Vector Search
As a user, I want both keyword and semantic search, so that I can find content by terms or meaning.
**Acceptance Criteria:**
1. BM25/full-text search over curated content via Postgres (Neon) `tsvector`/GIN.
2. Vector similarity search via pgvector (HNSW).
3. Both return results with document/version/page/section references.
4. Retrieval latency is measured and logged.

### Story 3.4 Hybrid Retrieval, Reranking & Filters
As a user, I want hybrid retrieval with reranking and equipment/version filters, so that results are precise and applicable.
**Acceptance Criteria:**
1. Lexical + vector results are fused into a hybrid result set.
2. A reranking step orders results by relevance.
3. Metadata filters support equipment model/revision and version-awareness (applicable vs. obsolete).
4. Abstention path returns "insufficient evidence" when no result passes thresholds.

### Story 3.5 LangGraph Grounded-Answer Service with Citations
As a technician, I want a grounded answer with precise citations and surfaced warnings, so that I can trust and verify it.
**Acceptance Criteria:**
1. LangGraph workflow: query analysis → equipment identification → retrieval → rerank → sufficiency check → cited generation.
2. Answers are grounded only in retrieved evidence; each claim carries a citation to document/version/page/section.
3. Safety warnings and uncertainty present in evidence are surfaced.
4. The workflow abstains rather than inventing content when evidence is insufficient.
5. The service never presents output as certified manufacturer instruction.

### Story 3.6 Retrieval & Answer Quality Baseline
As an engineer, I want an initial gold dataset and retrieval/answer metrics, so that quality is measurable before building the UI.
**Acceptance Criteria:**
1. `evaluation_case` records capture question, relevant evidence and expected behavior.
2. Recall@K and citation-resolution are computed over the gold set.
3. A groundedness check flags unsupported claims.
4. Results are reproducible via a documented command and stored for regression comparison.

### Story 3.7 Caching (deterministic + exact-match answer)
As an engineer, I want layered caching behind a `Cache` port, so that cost and latency drop without compromising tenant isolation or version-awareness ([ADR 0009](adr/0009-caching-strategy.md)).
**Acceptance Criteria:**
1. Embedding reuse: embeddings are not regenerated when `(chunk_id, model_version)` already exists (Postgres-backed); re-index/backfill reuses them.
2. Query-embedding cache and an exact-match answer cache are implemented behind a `Cache` port (Redis — Cloud or Docker).
3. Answer/retrieval cache keys are tenant-partitioned and encode equipment model + revision + current document-version set; a cache hit never crosses tenants and never serves a superseded version.
4. Cache entries are invalidated when a new/superseded `document_version` is published by ingestion.
5. A cache hit does not change the abstention decision vs. a cold run; security tests cover cross-tenant cache isolation (extends Story 6.2).
6. Fuzzy/semantic "similar question" caching is explicitly **out of scope** here (deferred per ADR 0009).

---

## Epic 4 — Enterprise Application & SaaS

**Goal:** Deliver the user-facing product and SaaS surface: document management, equipment catalog, search + AI assistant, document viewer at the cited page, admin for orgs/workspaces/users/roles, conversation history and feedback, versioned APIs, and quotas/rate-limits/audit logging — with tenant and document access control enforced before retrieval and source access.

### Story 4.1 Versioned REST API Contracts
As a client developer, I want versioned, documented REST APIs, so that integrations are stable.
**Acceptance Criteria:**
1. All endpoints under `/api/v1` with generated OpenAPI docs.
2. Request/response models validated via Pydantic.
3. Contract/integration tests cover the public surface.
4. Breaking changes require a new version.

### Story 4.2 Document Management UI & APIs
As a knowledge manager, I want to upload, browse, categorize and view versions of documents, so that I can manage the corpus.
**Acceptance Criteria:**
1. Upload triggers an asynchronous ingestion job (Epic 2) with visible status.
2. Browse/filter documents by metadata and equipment association.
3. View document version history.
4. All document access is tenant- and permission-scoped.

### Story 4.3 Equipment Catalog & Associations
As a user, I want an equipment catalog linked to documents, so that search can be equipment-aware.
**Acceptance Criteria:**
1. `equipment` records (manufacturer, model, version/revision, asset ID) are manageable via UI/API.
2. Documents can be associated with equipment models/revisions.
3. Catalog supports search/filter.
4. Associations drive retrieval filters in Epic 3.

### Story 4.4 Search & AI Assistant UI
As a technician, I want a search + chat interface with filters and citations, so that I can ask questions and verify sources.
**Acceptance Criteria:**
1. UI offers keyword, semantic and hybrid search with equipment/version filters.
2. AI assistant returns grounded answers with clickable citations.
3. Abstention and uncertainty/safety states are clearly displayed.
4. The UI calls the Epic 3 service through the versioned API with access control applied.

### Story 4.5 Document Viewer at Cited Page
As a technician, I want to open the source PDF at the exact cited page, so that I can confirm the evidence.
**Acceptance Criteria:**
1. Clicking a citation opens the source document at the referenced page, served via a short-lived R2 presigned URL (ADR 0014).
2. The cited section/region is highlighted where available.
3. Access to the source is authorized before issuing the presigned URL / display.
4. Viewer works for the supported document types.

### Story 4.6 Conversation History & Feedback
As a user, I want my conversation history and the ability to rate answers/report issues, so that the system can improve.
**Acceptance Criteria:**
1. Conversations and their citations are stored per user/tenant.
2. Users can rate answers and flag incorrect answers/sources.
3. Feedback is retrievable for failure analysis (Epic 5).
4. History respects retention settings (Epic 6).

### Story 4.7 Admin: Organizations, Workspaces, Users & Roles
As an admin, I want to manage organizations, workspaces, users and roles, so that I can operate a multi-tenant deployment.
**Acceptance Criteria:**
1. CRUD for organizations, workspaces and users with role assignment.
2. Document-level and workspace-level permissions configurable.
3. Admin actions are audit-logged.
4. All actions enforce tenant isolation.

### Story 4.8 Quotas, Rate Limits & Audit Logging
As an operator, I want usage quotas, API rate limits and audit logging, so that the platform is safe and accountable.
**Acceptance Criteria:**
1. Per-tenant usage quotas enforced on relevant operations.
2. API rate limits enforced with clear error responses.
3. `audit_event` records actor, operation, resource and timestamp.
4. Tests cover quota/limit enforcement and audit completeness.

---

## Epic 5 — LLMOps, Evaluation & Observability

**Goal:** Make retrieval and generation observable, measurable and safe to update: comprehensive gold datasets, an evaluation harness (retrieval, citation, groundedness, safety), end-to-end tracing, prompt/model-config versioning with regression gates, and dashboards for latency/cost/health with alerts.

### Story 5.1 Gold Evaluation Datasets
As an evaluator, I want dedicated gold datasets for key failure modes, so that evaluation is representative.
**Acceptance Criteria:**
1. Datasets exist for: exact equipment identifiers, outdated manuals, conflicting sources, unanswerable questions, tables, scanned PDFs, malicious documents.
2. Each case specifies question, relevant evidence and expected behavior (incl. abstention).
3. Datasets are versioned and reviewable.
4. A documented command runs evaluation against any dataset.

### Story 5.2 Retrieval, Citation & Groundedness Evaluation Harness
As an evaluator, I want automated quality metrics, so that improvements are measured, not demoed.
**Acceptance Criteria:**
1. Recall@K and ranking metrics computed on the retrieval datasets.
2. Citation-correctness (resolution to correct document/location) measured.
3. Groundedness/faithfulness measured against evidence.
4. Results stored and comparable across runs (regression baseline).

### Story 5.3 Safety-Abstention Evaluation
As a safety owner, I want critical safety-abstention tests, so that the system refuses unsafe/unsupported guidance.
**Acceptance Criteria:**
1. A predefined critical safety test set runs in CI.
2. 100% pass required; failures block release.
3. Reports show which cases abstained vs. answered.
4. Malicious-document cases confirm safe handling (ties to Epic 6).

### Story 5.4 End-to-End Tracing
As an engineer, I want tracing from query → chunks → model → answer, so that I can debug and audit behavior.
**Acceptance Criteria:**
1. `query_trace` records user, retrieval IDs, model, latency and cost.
2. Traces are correlatable end-to-end (OpenTelemetry instrumentation → Langfuse for LLM/RAG traces).
3. Traces are queryable for a given query/conversation.
4. Sensitive content handling in traces respects security policy.

### Story 5.5 Prompt/Model Config Versioning & Regression Gates
As an AI engineer, I want versioned prompts/model configs gated by regression tests, so that changes are controlled.
**Acceptance Criteria:**
1. Prompt and model configurations are versioned artifacts (prompts managed via Langfuse prompt management and/or repo artifacts — ADR 0013).
2. Changing a config triggers the evaluation regression suite.
3. Promotion requires passing retrieval, groundedness and safety gates.
4. Rollback to a prior config version is supported.

### Story 5.6 Operations & Evaluation Dashboards with Alerts
As an operator, I want dashboards and alerts for latency, cost, pipeline health and quality, so that I can run the platform.
**Acceptance Criteria:**
1. Dashboards show p95 latencies, error rates, pipeline health and token cost.
2. Evaluation dashboard shows Recall@K, citation correctness, groundedness and regressions.
3. Alerts fire on defined thresholds (latency, errors, cost, quality regressions).
4. Observability backends via the `Telemetry` port: Langfuse (LLM/RAG traces + eval), Azure Monitor/App Insights (infra), Prometheus/Grafana optional (local infra dashboards) — OTel is in-app instrumentation, nothing to host (ADR 0013).

---

## Epic 6 — Security, Governance & Cloud Operations

**Goal:** Harden and operationalize the platform: a documented threat model, automated tenant-isolation and prompt-injection tests, encryption, audit logging, data retention/deletion and provenance tracking, Terraform IaC for dev/staging/prod, Azure deployment, and tested backup/recovery runbooks.

### Story 6.1 Threat Model & Security Controls Documentation
As a security owner, I want a documented threat model and controls, so that security is explicit and reviewable.
**Acceptance Criteria:**
1. Threat model covers tenant isolation, authz-before-retrieval, prompt injection, malicious documents, secrets/PII.
2. Each threat maps to a control and a test.
3. Controls documented in `docs/`.
4. Reviewed and version-controlled.

### Story 6.2 Tenant Isolation & Authorization Security Tests
As a security engineer, I want automated isolation/authz tests, so that cross-tenant disclosure is provably prevented.
**Acceptance Criteria:**
1. Tests attempt cross-tenant reads across documents, retrieval and source access — all denied.
2. Authorization is verified before retrieval and before source file access.
3. Zero cross-tenant disclosure is a required CI gate.
4. Object-level permissions enforced on chunks/sources, not just documents.

### Story 6.3 Prompt-Injection & Malicious-Document Defenses
As a security engineer, I want defenses against injection and hostile content, so that retrieved content cannot subvert the system.
**Acceptance Criteria:**
1. Retrieved content is treated as untrusted; tool access is restricted.
2. Adversarial test cases (injection, hostile instructions in documents) are blocked/neutralized.
3. Failures are logged and surfaced.
4. Tests run in CI as a required gate.

### Story 6.4 Encryption, Secrets & PII Handling
As a security owner, I want encryption and managed secrets/PII handling, so that enterprise data is protected.
**Acceptance Criteria:**
1. Data encrypted in transit (TLS) and at rest.
2. `SecretsProvider` interface: `.env` locally, Azure Key Vault + managed identities in prod.
3. PII is identified and protected per policy; secrets never logged. **PII detection/anonymization uses Presidio** (open-source, self-hosted, local-first) behind a `PiiScrubber` port — no paid PII service required.
4. Dependency and security scanning run in CI.
5. **Controlled object storage (Cloudflare R2, S3-compatible):** buckets are private (no public access); access uses scoped R2 API tokens via the secrets provider / Key Vault (never committed); the document viewer uses short-lived presigned URLs only; raw/cleaned/curated are separated (NFR15); lifecycle/retention is configured (ties to Story 6.5). See [ADR 0014](adr/0014-cloudflare-r2-object-storage.md).

### Story 6.5 Data Retention, Deletion & Provenance
As a governance owner, I want retention/deletion workflows and provenance tracking, so that we meet licensing and data-rights obligations.
**Acceptance Criteria:**
1. Document licensing/provenance tracked per source and version.
2. Retention policies configurable per tenant.
3. Deletion workflow removes data across raw/curated/index/embedding stores consistently.
4. Deletion and retention actions are audit-logged.

### Story 6.6 Infrastructure as Code & Environments
As a platform engineer, I want Terraform IaC for dev/staging/prod, so that environments are reproducible.
**Acceptance Criteria:**
1. Terraform modules provision the stack using multiple providers: azurerm (Container Apps, Service Bus, ACR, Key Vault, Azure Monitor), Neon (serverless Postgres + pgvector — ADR 0015), and Cloudflare (R2 buckets — ADR 0014). _(Not Azure PostgreSQL Flexible Server / Blob Storage.)_
2. Separate dev/staging/prod environment configurations.
3. Secrets sourced from Key Vault via managed identities (no secrets in code); Neon/R2/Langfuse tokens stored in Key Vault.
4. `terraform plan/apply` documented in runbooks.

### Story 6.7 CI/CD with Quality & Security Gates and Safe Migrations
As a release manager, I want gated CI/CD with safe migrations and rollback, so that deployments are reliable.
**Acceptance Criteria:**
1. CI/CD builds, tests, scans and deploys to staging then production.
2. Deployment blocked unless quality + security + safety gates pass.
3. Database migrations are safe and reversible; rollback path documented.
4. Staging and production deploys are distinct and promotable.

### Story 6.8 Backup, Recovery & Operational Runbooks
As an operator, I want tested backups, recovery and runbooks, so that we meet reliability/recovery targets.
**Acceptance Criteria:**
1. Automated backups: Neon point-in-time recovery / branching for the database; R2 object versioning (and/or cross-bucket copy) for object storage.
2. A restore is demonstrated within the agreed RPO/RTO (Neon PITR restore + R2 object restore).
3. Runbooks cover deployment, rollback, incident response and recovery.
4. Availability and recovery targets (99.5%, RPO/RTO) are documented and monitored.

---

---

# Post-MVP Expansion Epics

> These epics are **not part of the initial production scope** (Epics 1–6). They are committed, planned work sequenced afterward, promoted from the deferred list in `rag-design-challenges.md`. Each reuses the existing platform (ports & adapters, multi-tenant model, retrieval interfaces, evaluation harness) rather than introducing a parallel system. Requirements here extend the FR/NFR set and should be numbered when an epic is activated.

## Epic 7 — Enterprise Knowledge Connectors

**Goal:** Extend ingestion beyond file/API sources to live enterprise SaaS knowledge (SharePoint, Confluence, ticketing, email/transcripts) with per-source permission mapping, incremental synchronization and handling of contradictory knowledge — so a tenant's internal operational knowledge becomes retrievable under the same authorize-before-retrieve guarantees.

**Addresses:** RAG dimension A (enterprise internal knowledge) in `rag-design-challenges.md`. Builds on Epic 2 (ingestion), Epic 6 (permissions).

### Story 7.1 Connector Framework & Incremental Sync
As an admin, I want a connector framework with incremental synchronization, so that external SaaS sources stay current without full re-ingestion.
**Acceptance Criteria:**
1. A connector interface supports delta/incremental sync with watermarking and resumable runs.
2. Dagster schedules/sensors drive per-source sync; runs are observable with status/history.
3. Deletions/updates at the source are reflected (supersession, not duplication).
4. Connector failures route to dead-letter with retry.

### Story 7.2 SharePoint & Confluence Connectors
As a knowledge manager, I want SharePoint and Confluence connectors, so that internal SOPs and wiki knowledge are ingested.
**Acceptance Criteria:**
1. Authenticated ingestion from SharePoint document libraries and Confluence spaces.
2. Source-native metadata (space/site, author, labels, timestamps) is captured and normalized.
3. Native permissions are captured for mapping (Story 7.4).
4. Content is versioned and lineage-tracked like file sources.

### Story 7.3 Ticketing & Communication Connectors
As a support lead, I want ticketing and email/transcript ingestion, so that resolved-case knowledge is searchable.
**Acceptance Criteria:**
1. Connectors for a ticketing system and an email/transcript source (authorized).
2. PII handling and retention policy applied at ingestion (ties to Story 6.5).
3. Thread/conversation structure preserved for citation.
4. Opt-in per tenant; disabled by default.

### Story 7.4 Source-Permission Mapping & Contradiction Handling
As a security owner, I want source-native permissions mapped to IKIP object-level permissions, and contradictory knowledge surfaced, so that enterprise retrieval stays safe and trustworthy.
**Acceptance Criteria:**
1. Source ACLs map to IKIP document/chunk-level permissions; authorize-before-retrieve still holds.
2. Cross-tenant and cross-permission isolation tests extended to connector content (zero disclosure gate).
3. Contradictory statements across sources are detected and flagged in results (prefer authoritative/most-recent).
4. Evaluation includes a connector-content contradiction set.

## Epic 8 — Structured-Data & Financial Retrieval

**Goal:** Add the ability to retrieve and reason over structured data (financial statements/XBRL) alongside documents — hybrid structured+unstructured retrieval with numerical accuracy and comparative analysis — establishing the finance vertical.

**Addresses:** RAG dimension C (documents + structured data). Builds on Epic 3 (retrieval), data model.

### Story 8.1 Structured-Data Ingestion (statements / XBRL)
As an engineer, I want structured financial data ingested and modeled, so that exact figures are queryable.
**Acceptance Criteria:**
1. Ingest structured statements (e.g., XBRL) into a typed, queryable schema with provenance.
2. Linkage between a figure and its source document/version/page is preserved.
3. Period/effective-date semantics captured (ties to version-awareness).
4. Validation rejects malformed/ambiguous structured inputs.

### Story 8.2 Hybrid Structured + Unstructured Retrieval
As an analyst, I want queries that combine narrative documents and exact figures, so that answers are both contextual and numerically correct.
**Acceptance Criteria:**
1. Retrieval can join document evidence with structured values in one answer.
2. Numeric answers cite the exact structured source and period.
3. Abstention applies when the figure is unavailable/ambiguous.
4. Comparative queries (period-over-period, entity-vs-entity) supported.

### Story 8.3 Numerical-Accuracy Evaluation
As an evaluator, I want numerical-accuracy metrics, so that figure answers are measured, not assumed.
**Acceptance Criteria:**
1. Gold set of figure questions with known values.
2. Exact-match / tolerance metrics computed and regression-gated.
3. Citation correctness measured for figures (source + period).
4. Results stored alongside existing evaluation runs (Epic 5).

## Epic 9 — Advanced Multimodal Retrieval

**Goal:** Extend extraction and retrieval to engineering drawings, schematics and visual tables, with multimodal embeddings and visual citations — the capability explicitly deferred from Story 2.3 / brief P2.

**Addresses:** RAG dimension B (visual/multimodal, advanced). Builds on Epic 2 (extraction), Epic 3 (retrieval).

### Story 9.1 Diagram & Visual-Table Extraction
As an engineer, I want drawings/schematics and complex visual tables extracted with page/region references, so that they become retrievable evidence.
**Acceptance Criteria:**
1. Diagram/schematic regions and visual tables are detected and extracted with page + bounding-region references.
2. Extracted elements are linked to `Section`/`Chunk` with resolvable back-references.
3. Extraction quality scored; low-confidence flagged for review.
4. Evaluation uses a visual gold set (e.g., DocVQA-style).

### Story 9.2 Multimodal Embeddings & Retrieval
As a technician, I want to retrieve answers grounded in diagrams/visual tables, so that visual information is usable.
**Acceptance Criteria:**
1. Multimodal embeddings generated and indexed (versioned, behind `VectorStore`/`LLMClient` interfaces).
2. Retrieval can return visual evidence with equipment/version filters.
3. Hybrid fusion includes visual results where relevant.
4. Latency targets re-validated for the multimodal path.

### Story 9.3 Visual Citations in the Viewer
As a technician, I want visual citations highlighted on the source page, so that I can verify diagram-based answers.
**Acceptance Criteria:**
1. Citations resolve to the exact page and visual region.
2. The document viewer highlights the cited region.
3. Groundedness/citation metrics extended to visual evidence.
4. Authorization enforced before visual source display.

---

## Checklist Results Report
_To be completed when the PRD is validated against the BMAD PM checklist (pm-checklist) before architecture handoff._

## Next Steps

### Architect Prompt
Using this PRD and `brief.md`, produce `architecture.md`: a fullstack/backend-centric architecture covering high-level design, the full tech stack with versions, the data models (from the entity list), API surface, components/services, the dual-orchestration workflows (Dagster + LangGraph), database schema (incl. pgvector), source tree, infrastructure/deployment (local→Azure via Terraform), error handling, coding standards, test strategy and security. Honor NFR12 (interface-driven infra), NFR15 (separable stores), NFR17 (laptop-runnable) and the P0 scope.
