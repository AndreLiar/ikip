# Epic 4 — Enterprise Application & SaaS

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Deliver the user-facing product and SaaS surface: document management, equipment catalog, search + AI assistant, document viewer at the cited page, admin for orgs/workspaces/users/roles, conversation history and feedback, versioned APIs, and quotas/rate-limits/audit logging — with tenant and document access control enforced before retrieval and source access.

**Related requirements:** FR19–FR28, FR33 · NFR2, NFR10, NFR11 · depends on Epics 1–3

---

## Story 4.1 Versioned REST API Contracts
As a client developer, I want versioned, documented REST APIs, so that integrations are stable.
**Acceptance Criteria:**
1. All endpoints under `/api/v1` with generated OpenAPI docs.
2. Request/response models validated via Pydantic.
3. Contract/integration tests cover the public surface.
4. Breaking changes require a new version.

## Story 4.2 Document Management UI & APIs
As a knowledge manager, I want to upload, browse, categorize and view versions of documents, so that I can manage the corpus.
**Acceptance Criteria:**
1. Upload triggers an asynchronous ingestion job (Epic 2) with visible status.
2. Browse/filter documents by metadata and equipment association.
3. View document version history.
4. All document access is tenant- and permission-scoped.

## Story 4.3 Equipment Catalog & Associations
As a user, I want an equipment catalog linked to documents, so that search can be equipment-aware.
**Acceptance Criteria:**
1. `equipment` records (manufacturer, model, version/revision, asset ID) are manageable via UI/API.
2. Documents can be associated with equipment models/revisions.
3. Catalog supports search/filter.
4. Associations drive retrieval filters in Epic 3.

## Story 4.4 Search & AI Assistant UI
As a technician, I want a search + chat interface with filters and citations, so that I can ask questions and verify sources.
**Acceptance Criteria:**
1. UI offers keyword, semantic and hybrid search with equipment/version filters.
2. AI assistant returns grounded answers with clickable citations.
3. Abstention and uncertainty/safety states are clearly displayed.
4. The UI calls the Epic 3 service through the versioned API with access control applied.

## Story 4.5 Document Viewer at Cited Page
As a technician, I want to open the source PDF at the exact cited page, so that I can confirm the evidence.
**Acceptance Criteria:**
1. Clicking a citation opens the source document at the referenced page.
2. The cited section/region is highlighted where available.
3. Access to the source is authorized before display.
4. Viewer works for the supported document types.

## Story 4.6 Conversation History & Feedback
As a user, I want my conversation history and the ability to rate answers/report issues, so that the system can improve.
**Acceptance Criteria:**
1. Conversations and their citations are stored per user/tenant.
2. Users can rate answers and flag incorrect answers/sources.
3. Feedback is retrievable for failure analysis (Epic 5).
4. History respects retention settings (Epic 6).

## Story 4.7 Admin: Organizations, Workspaces, Users & Roles
As an admin, I want to manage organizations, workspaces, users and roles, so that I can operate a multi-tenant deployment.
**Acceptance Criteria:**
1. CRUD for organizations, workspaces and users with role assignment.
2. Document-level and workspace-level permissions configurable.
3. Admin actions are audit-logged.
4. All actions enforce tenant isolation.

## Story 4.8 Quotas, Rate Limits & Audit Logging
As an operator, I want usage quotas, API rate limits and audit logging, so that the platform is safe and accountable.
**Acceptance Criteria:**
1. Per-tenant usage quotas enforced on relevant operations.
2. API rate limits enforced with clear error responses.
3. `audit_event` records actor, operation, resource and timestamp.
4. Tests cover quota/limit enforcement and audit completeness.
