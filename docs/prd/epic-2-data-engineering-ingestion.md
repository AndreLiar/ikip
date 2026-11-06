# Epic 2 — Data Engineering & Ingestion Pipeline

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Deliver a reproducible raw→curated document pipeline orchestrated by Dagster that ingests heterogeneous sources, extracts and cleans content (with OCR fallback), deduplicates and versions documents, enriches metadata, validates quality and tracks lineage — exposed as asynchronous jobs with status and reprocessing.

> **Source corpus:** the connectors in this epic target the candidate sources cataloged in `../data-sources.md`. MVP ingestion uses the **Category 1 industrial manuals** (licensed starter corpus); other categories are out of initial scope. Each source must pass a license + provenance check (Epic 6, Story 6.5) before being enabled.

**Related requirements:** FR1–FR8 · NFR5, NFR15 · depends on Epic 1 (object storage interface, tenant model)

> **Infra context:** object storage = **Cloudflare R2** (S3, [ADR 0014](../adr/0014-cloudflare-r2-object-storage.md); MinIO optional offline); database = **Neon** Postgres+pgvector ([ADR 0015](../adr/0015-neon-serverless-postgres.md)); async queue/DLQ = **Redis** (dev) → **Azure Service Bus** (prod, durable) ([ADR 0009](../adr/0009-caching-strategy.md), [ADR 0003](../adr/0003-local-first-ports-and-adapters.md)). **Dagster** is the one heavy component that runs **locally in Docker** during dev (web + daemon) and as **Container Apps Jobs** in prod ([ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md), [ADR 0005](../adr/0005-managed-containers-not-kubernetes.md)) — unlike the managed data backends. All infra access goes through the ports.

---

## Story 2.1 Object Storage & Ingestion Job Model
As an engineer, I want raw files stored in object storage and tracked by an ingestion-job record, so that every source file is traceable through processing.
**Acceptance Criteria:**
1. `ObjectStorage` port with a **Cloudflare R2** (S3) implementation stores raw files ([ADR 0014](../adr/0014-cloudflare-r2-object-storage.md)); MinIO backs the same port for offline tests.
2. `ingestion_job` table records source, state, timestamps and error info.
3. Raw, cleaned and curated artifacts are stored in logically separate locations (buckets/prefixes), per NFR15.
4. Tests cover upload/retrieve and job state transitions (storage port mockable so CI needs no live R2).

## Story 2.2 Source Connectors & Scheduled Sync
As an admin, I want connectors for file and API sources with scheduled synchronization, so that documentation stays current.
**Acceptance Criteria:**
1. Connectors ingest PDF, HTML, CSV, JSON, Excel and an API adapter.
2. Dagster schedules/sensors trigger synchronization for configured sources.
3. Authorized crawling respects source access rules and licensing metadata (see `../data-sources.md`).
4. New/changed documents are detected and queued for processing.

## Story 2.3 PDF Extraction with OCR Fallback & Layout/Table Capture
As an engineer, I want native-PDF extraction with OCR fallback that preserves page/layout/tables, so that downstream retrieval has accurate, locatable content.
**Acceptance Criteria:**
1. Native-digital PDFs extracted with PyMuPDF/Docling, preserving page references.
2. Scanned/low-quality pages routed to OCR via a two-stage, cost-controlled strategy: **stage 1 = local Tesseract ($0, default)**; **stage 2 = Azure Document Intelligence (paid, optional)** only for pages that need enhanced OCR/table/layout recognition.
3. Tables and diagram references extracted with originating page numbers.
4. Extraction quality is scored; low-quality extractions are flagged.

## Story 2.4 Cleaning, Normalization & Metadata Enrichment
As an engineer, I want extracted content cleaned, normalized and enriched with metadata, so that documents are consistent and classifiable.
**Acceptance Criteria:**
1. Cleaning/normalization produces consistent curated text with structure preserved.
2. Documents are classified and metadata normalized per schema.
3. Content validation uses schema/data-quality checks (e.g., Pandera/Pydantic).
4. Validation failures are recorded against the ingestion job.

## Story 2.5 Deduplication & Document Versioning
As an engineer, I want exact/near-duplicate detection and document versioning, so that we track revisions and avoid redundant content.
**Acceptance Criteria:**
1. Exact duplicates detected via checksum; near-duplicates via similarity.
2. `document` and `document_version` records capture revision, publication/effective dates and checksum.
3. A new version supersedes prior versions without deleting original evidence.
4. Tests cover duplicate detection and version supersession.

## Story 2.6 Lineage, Quality Reporting & Reprocessing
As an operator, I want lineage tracking, a data-quality report and controlled reprocessing/backfill, so that I can trust and maintain the knowledge base.
**Acceptance Criteria:**
1. Lineage links raw file → curated content → document version as Dagster assets.
2. A data-quality report summarizes success rate, failures and duplicates per run.
3. Failed jobs route to a dead-letter path with retry, via the `JobQueue` port (Redis in dev → Azure Service Bus in prod for durability).
4. Documents can be reprocessed/backfilled (e.g., after a parser change) via an asset-aware re-run without full rebuild.
