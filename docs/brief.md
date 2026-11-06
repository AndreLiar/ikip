# Project Brief: Industrial Knowledge Intelligence Platform (IKIP)

_BMAD artifact 1 of 3 — Analyst output. Feeds the PRD (`prd.md`)._

---

## Executive Summary

IKIP is an enterprise-grade, multi-tenant AI platform that transforms fragmented industrial documentation — equipment manuals, technical specifications, maintenance procedures, troubleshooting guides and parts catalogs — into a secure, searchable, continuously-updated knowledge system.

Industrial maintenance teams lose time hunting across scattered PDFs and portals to identify the correct equipment model and revision, locate fault codes, and verify procedures. IKIP converts that documentation into a governed knowledge base and answers natural-language questions with **evidence-grounded, version-aware, cited** responses — and refuses to answer when the evidence is insufficient.

The platform is designed **local-first and cloud-ready**: the full stack runs on a developer laptop with Docker, and migrates to Microsoft Azure for production without rewriting core business logic.

## Problem Statement

- **Documentation is fragmented and heterogeneous.** Manuals, SOPs, spare-parts catalogs, service bulletins and internal records live in different formats (PDF, HTML, CSV, Excel, scanned images) and systems.
- **Equipment identification is hard and high-stakes.** The same manufacturer ships many models and revisions; applying an obsolete procedure or the wrong revision has safety consequences.
- **Search is keyword-only and context-blind.** Technicians cannot ask natural-language questions, cannot filter by equipment model/revision, and get no traceable citation back to the source page.
- **Generic "chat with PDF" tools are unsafe here.** They hallucinate procedures, ignore document versions, leak across customers, and provide no evaluation, auditability or access control.

The core risks are **not primarily LLM accuracy** — they are poor source extraction, incorrect equipment identification, outdated documentation, unclear licensing, confidential customer data, access-control defects, and unsafe maintenance guidance.

## Proposed Solution

A vertical, production-oriented RAG platform built from two complementary orchestration systems:

- **Data Engineering pipeline (Dagster):** scheduled/event-driven ingestion → parsing + OCR → cleaning + validation → deduplication + versioning → metadata enrichment → chunking + embedding → indexing. Produces governed, lineage-tracked, reprocessable data assets.
- **AI / RAG orchestration (LangGraph + LangChain):** query analysis → equipment identification → hybrid retrieval (BM25 + vector) → reranking → evidence-sufficiency check → cited answer generation → abstention when evidence is missing.

Supporting capabilities: multi-tenant backend + web app, document viewer that opens the cited page, equipment catalog, evaluation harness with a gold dataset, tracing/monitoring dashboards, and documented security controls with a threat model.

The specific retrieval difficulties IKIP is designed around (permission-aware multi-tenancy, version-aware/temporal retrieval, scanned-PDF + table handling, conflicting sources, abstention, and measurable evaluation) — and the ones deliberately deferred (enterprise SaaS connectors, structured-data/XBRL querying, advanced drawing interpretation) — are enumerated and traced to requirements in [`rag-design-challenges.md`](./rag-design-challenges.md).

**Key differentiators vs. a chatbot:**
1. Version-aware retrieval that distinguishes applicable from obsolete instructions.
2. Precise, resolvable document + page + section citations.
3. Authorization enforced _before_ retrieval and source access (tenant + document level).
4. Measurable quality (Recall@K, citation correctness, groundedness, safety abstention) rather than demos.

## Target Users

**Primary:** industrial maintenance engineers and field technicians who need the correct, current procedure for a specific equipment model/revision — fast and traceable.

**Secondary:** OEM technical-support teams, equipment operators, industrial service providers, and enterprise knowledge managers / administrators who manage documents, tenants, users and quality.

### Example interaction
> "I have an equipment fault. Find the applicable maintenance procedure for this specific model and revision. Show the relevant warnings, required parts, and original manual pages."

Expected behavior: identify model + revision; retrieve official manuals and authorized internal procedures; distinguish applicable from obsolete; cite sources precisely; surface safety warnings and uncertainty; refuse to invent missing procedures.

## Goals & Success Metrics

Engineering targets for an initial production-oriented release (measured against a representative evaluation dataset defined _before_ measurement — these are targets, not performance claims):

| Category | Target |
|----------|--------|
| Ingestion quality | ≥ 98% successful processing for the supported clean-document corpus |
| Retrieval quality | Recall@5 ≥ 90% on a reviewed evaluation set |
| Citation quality | ≥ 98% of source references resolve to the correct document + location |
| Groundedness | ≥ 95% supported factual claims on the evaluation set |
| Safety | 100% pass on predefined critical safety-abstention tests |
| Authorization | Zero cross-tenant disclosure in automated security tests |
| Search performance | p95 retrieval latency < 1.5 s under defined test load |
| Answer performance | p95 time-to-first-token < 5 s under defined test load |
| Reliability | 99.5% monthly availability target for a deployed pilot |
| Recovery | Demonstrated restore from backup within an agreed RPO/RTO |

Dedicated evaluation datasets must exist for: exact equipment identifiers, outdated manuals, conflicting sources, unanswerable questions, tables, scanned PDFs, and malicious document content.

## MVP Scope

**In scope (P0 — essential production core):**
- Organization management (tenants, users, roles, workspaces)
- Document management (upload, browse, categorize, version)
- Automated ingestion (connectors, sync schedules, job history)
- Quality management (parse validation, duplicates, failed jobs)
- Equipment catalog (manufacturer, model, revision, asset associations)
- Intelligent search (keyword, semantic, hybrid, filters)
- AI assistant (grounded answers, citations, uncertainty/abstention)
- Document viewer (open source PDF at cited page)
- Retrieval evaluation (gold dataset, benchmarking, regression checks)
- Security (tenant isolation, authorization, audit logs)
- Operations dashboard (latency, errors, pipeline health, token cost)

**Later (P1):** maintenance workflow (fault-code lookup), change monitoring (updated/obsolete manuals), feedback management.

**Advanced extensions (P2):** external integrations (CMMS, ERP, ticketing), advanced multimodal RAG (diagrams/visual tables/drawings).

**Out of scope (initial):** autonomous equipment control, certified repair approval, sensor-stream predictive maintenance, large-scale engineering-drawing interpretation.

**Starter corpus:** a bounded, licensed set of ~100–500 documents across a few equipment families. 10,000+ documents is a later scale-testing objective, not a prerequisite.

**MVP document-processing scale (ramp):**

| Phase | Document count | Purpose |
|-------|----------------|---------|
| First working slice | ~20–50 | get the pipeline + RAG + evaluation loop working end-to-end on one or two equipment families |
| **Evaluated MVP** | **~100–500** | across a few equipment families — representative *and* small enough for a human-reviewable gold set |
| Post-MVP | 10,000+ | explicit scale-testing objective, **not** a prerequisite |

Rationale: the quality targets (NFR5–NFR9 — ingestion success, Recall@5, citation/groundedness, safety abstention) can only be measured against a *reviewed* gold set, which is infeasible at 10k docs solo; 100–500 is representative yet reviewable. Scale implication: ~100–500 manuals (~100 pages each) ≈ 10k–50k pages ≈ ~30k–400k chunks/embeddings — comfortably within pgvector's range, so no dedicated vector DB is needed at MVP (see [ADR 0001](./adr/0001-vector-store-pgvector.md)). Ingestion cost is controlled via the two-stage OCR strategy (native extraction first; paid OCR only where needed).

**Candidate data sources:** the full catalog of candidate ingestion sources (51 sources across 9 categories, plus recommended evaluation datasets) is maintained in [`data-sources.md`](./data-sources.md). The **primary in-scope corpus is industrial equipment manuals** (Siemens, Schneider Electric, ManualLib, Metrology Manuals, Requip Market); the other categories (insurance, government, finance, banking, education, IT docs, cybersecurity) are retained as reference / future-vertical / evaluation sources only. Every source requires an explicit license + provenance check before ingestion.

## Post-MVP Vision

Vertical, industry-specific knowledge intelligence (not generic "chat with PDF"): deeper maintenance workflows, change monitoring for manufacturer updates, CMMS/ERP integrations, multimodal retrieval of diagrams and schematics, and scaled enterprise deployment with stronger network isolation, HA and disaster recovery.

## Technical Considerations

- **Local-first, cloud-ready, interface-driven.** Infrastructure-dependent services (object storage, job queue, vector store, LLM client, secrets, telemetry) sit behind interfaces. Object storage is **Cloudflare R2** (S3-compatible, all envs, zero egress; MinIO optional offline — see `data-sources.md` context and the architecture); the rest are local (Redis/local Postgres/.env) and Azure (Service Bus/Flexible Server/Key Vault/Monitor).
- **Hybrid retrieval on PostgreSQL first** (full-text + pgvector) — Azure AI Search only when managed search justifies the cost.
- **Dual orchestration:** Dagster for the data/knowledge-base pipeline; LangGraph+LangChain for the technician-facing AI workflow. They are complementary, not interchangeable.
- **Monorepo** so local and Azure versions share source.
- Full stack and cost/stack rationale are detailed in `architecture.md`.

## Constraints & Assumptions

- **Budget (planning estimates, USD, excl. tax/labor):** local development $5–$30/mo; Azure lean pilot ~$68–$290/mo; small production ~$270–$790/mo. Document ingestion (OCR/parsing of large corpora) is the hidden cost driver — use a two-stage strategy (local native-PDF extraction first; paid OCR only for pages that need it).
- **Hardware:** no GPU/Kubernetes needed to start; 16 GB RAM minimum, 32 GB recommended.
- **Legal:** only legally usable / authorized / licensed sample documents; track licensing and provenance per source.
- **Human-in-the-loop:** technicians remain responsible for applying official safety procedures and verifying the correct revision; the platform must never present AI advice as certified manufacturer instruction.

## Risks & Open Questions

- Poor-quality source extraction (scanned PDFs, complex tables, drawings).
- Incorrect equipment identification; outdated documentation presented as current.
- Access-control defects causing cross-tenant disclosure.
- Prompt injection / malicious document content.
- Unclear licensing or confidential customer data in the corpus.
- Ingestion cost blowups on large corpora.

_Open questions to resolve during PRD/architecture refinement:_ which starter equipment families and sources; which LLM/embedding models and region (France Central vs. West Europe); exact RPO/RTO for the pilot; evaluation-dataset ownership and review process.

## Next Steps

1. Approve this brief.
2. Produce/refine the **PRD** (`prd.md`) — functional & non-functional requirements and ordered epics with stories.
3. Produce/refine the **Architecture** (`architecture.md`).
4. Shard PRD + Architecture and begin story-driven implementation starting with Epic 1 (Foundation).
