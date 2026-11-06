# Epic 7 — Enterprise Knowledge Connectors  (Post-MVP)

_Sharded from `../prd.md`. Part of the [epic index](./index.md). **Post-MVP** — sequenced after Epics 1–6; not part of the initial production scope._

**Goal:** Extend ingestion beyond file/API sources to live enterprise SaaS knowledge (SharePoint, Confluence, ticketing, email/transcripts) with per-source permission mapping, incremental synchronization and handling of contradictory knowledge — so a tenant's internal operational knowledge becomes retrievable under the same authorize-before-retrieve guarantees.

**Addresses:** RAG dimension A (enterprise internal knowledge) in [`../rag-design-challenges.md`](../rag-design-challenges.md). Builds on Epic 2 (ingestion), Epic 6 (permissions).

---

## Story 7.1 Connector Framework & Incremental Sync
As an admin, I want a connector framework with incremental synchronization, so that external SaaS sources stay current without full re-ingestion.
**Acceptance Criteria:**
1. A connector interface supports delta/incremental sync with watermarking and resumable runs.
2. Dagster schedules/sensors drive per-source sync; runs are observable with status/history.
3. Deletions/updates at the source are reflected (supersession, not duplication).
4. Connector failures route to dead-letter with retry.

## Story 7.2 SharePoint & Confluence Connectors
As a knowledge manager, I want SharePoint and Confluence connectors, so that internal SOPs and wiki knowledge are ingested.
**Acceptance Criteria:**
1. Authenticated ingestion from SharePoint document libraries and Confluence spaces.
2. Source-native metadata (space/site, author, labels, timestamps) is captured and normalized.
3. Native permissions are captured for mapping (Story 7.4).
4. Content is versioned and lineage-tracked like file sources.

## Story 7.3 Ticketing & Communication Connectors
As a support lead, I want ticketing and email/transcript ingestion, so that resolved-case knowledge is searchable.
**Acceptance Criteria:**
1. Connectors for a ticketing system and an email/transcript source (authorized).
2. PII handling and retention policy applied at ingestion (ties to Story 6.5).
3. Thread/conversation structure preserved for citation.
4. Opt-in per tenant; disabled by default.

## Story 7.4 Source-Permission Mapping & Contradiction Handling
As a security owner, I want source-native permissions mapped to IKIP object-level permissions, and contradictory knowledge surfaced, so that enterprise retrieval stays safe and trustworthy.
**Acceptance Criteria:**
1. Source ACLs map to IKIP document/chunk-level permissions; authorize-before-retrieve still holds.
2. Cross-tenant and cross-permission isolation tests extended to connector content (zero disclosure gate).
3. Contradictory statements across sources are detected and flagged in results (prefer authoritative/most-recent).
4. Evaluation includes a connector-content contradiction set.
