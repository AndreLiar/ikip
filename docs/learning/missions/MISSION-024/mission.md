# MISSION-024 — Technician Assistant UI (Next.js BFF) + search modes (Epic 4, Story 4.4)

**Mode:** Guidé (BFF vs CORS + scope + PRD-adjustment) → Autonome (impl) + knowledge transfer.
**Objective:** ship the technician-facing assistant — ask grounded, cited questions and run keyword/semantic/hybrid search with filters — as a Next.js app that talks to the Epic 3 API through a BFF, tenant-scoped and access-controlled.
**Maps to:** Epic 4 / Story 4.4. Decisions: [ADR 0023](../../../adr/0023-web-bff-next-over-direct-cors.md) (BFF), [ADR 0008](../../../adr/0008-nextjs-over-plain-react.md) (Next.js).

## PRD adjustment (argued)
Story 4.4 AC1 requires **keyword, semantic AND hybrid** search. The API's `/retrieve` only exposed hybrid, so a `mode: lexical|vector|hybrid` parameter was **added** to `RetrieveRequest` + the retrieve service (the domain already had `lexical_search`/`vector_search`/`hybrid_retrieve`). Story 4.1 (versioned API + OpenAPI) is already satisfied by FastAPI's generated docs. Story 4.5 (open source PDF at the cited page via R2 presigned URL) is **deferred** — citations are shown as resolvable references (rev/§/page, FR16), not yet a PDF open.

## What was built
- **Backend:** `/api/v1/retrieve` gains `mode` (lexical/vector/hybrid); `_citation_from_hit` maps SearchHits to the wire Citation; endpoint test covers all modes + invalid-mode 422.
- **`apps/web` (Next.js 15, App Router, TS):**
  - **BFF** ([ADR 0023](../../../adr/0023-web-bff-next-over-direct-cors.md)): `lib/bff.ts` + route handlers `app/api/ask|retrieve/route.ts` proxy to FastAPI with a **server-held token** (`IKIP_API_TOKEN`); the browser calls only same-origin routes — no token in the browser, no CORS.
  - **Assistant page** `app/page.tsx` (client): question box, mode selector (keyword/semantic/hybrid), equipment-model/revision/current-only filters, Ask + Search actions.
  - **Components:** `AnswerPanel` (claims + citations + **safety-critical flags** + warnings + **abstention** state + not-certified notice), `SearchResults`, `CitationChip` (rev/§/page, obsolete badge).
  - **Types** `lib/types.ts` mirror the API contract.
- **Tooling/CI:** Vitest + Testing Library, ESLint (next flat config), Prettier; a new **`web` CI job** (install → prettier → lint → typecheck → vitest → next build).

## Acceptance (Story 4.4)
1. Keyword/semantic/hybrid search + equipment/version filters. — **[verified]** (mode param + filters; endpoint + page tests)
2. Grounded answers with clickable citations. — **[verified]** (AnswerPanel renders claims + resolvable citations; PDF-open deferred to 4.5)
3. Abstention + uncertainty/safety states clearly displayed. — **[verified]** (abstention panel, safety badge, warnings; tests)
4. UI calls the Epic 3 service through the versioned API with access control. — **[verified]** (BFF → `/api/v1/*` with server token; no token in browser, ADR 0023)

## Verification
- web: lint ✓ typecheck ✓ vitest (7) ✓ next build ✓ prettier ✓
- python: ruff ✓ pytest 159 passed / 32 skipped (retrieve mode added).

## Deliverables
- `apps/api/src/ikip_api/retrieval.py` (mode) + test.
- `apps/web/**` (app, components, lib, tests, config). `.github/workflows/ci.yml` web job. [ADR 0023](../../../adr/0023-web-bff-next-over-direct-cors.md).

## Done-now additions (folded into this slice)
- **OpenAPI-generated TS client (Story 4.1):** `ikip_api.openapi` dumps the schema → `apps/web/openapi.json`; `pnpm gen:api` (openapi-typescript) → `lib/api-schema.ts`; `lib/types.ts` now aliases the generated schema (no hand-maintained drift). A CI drift guard regenerates and fails on diff.
- **Story 4.5 (partial): source access.** `GET /api/v1/documents/{version_id}/source-url` authorizes the version∈tenant **then** issues a short-lived R2 presigned URL (authorize-before-serve, AC3). Citations are now **clickable** (`CitationChip` → BFF → presigned URL, opened at `#page=N`). Serves the stored artifact (curated text today).

## Source-key plumbing (done-now, unblocks full 4.5)
- `document_version.source_object_key` (nullable String + reversible migration `6dff50d415b4`) stores the **original** source artifact key (raw tier). Threaded: `ingest_version`/`_add_version` → `publish_document_version` → `curate_and_version(source_object_key=…)` → the `document_versions` asset passes `job.raw_object_key`. The source-url endpoint now **prefers `source_object_key`** (the original PDF/HTML) over the curated text, falling back to curated.

## Story 4.5 viewer (done) + live PDF validation
- **`SourceViewer`** modal: clicking a citation opens the source **in-app** via the presigned URL in an `<iframe>` jumped to `#page=N` (the browser's PDF engine honors the page anchor). `CitationChip` opens/closes it. Zero heavy dependency; CI-testable (12 web tests assert the iframe src + page). Chosen over bundling `pdfjs-dist` because the one thing it would add — **region highlight (AC2)** — needs **per-chunk bounding boxes captured at extraction time**, which we don't store; that's the only remaining 4.5 gap and it's a data/extraction change, not a UI one.
- **Live validation (real PDF):** seeded a 2-page PyMuPDF PDF through the pipeline on a throwaway tenant → `document_versions` (PdfExtractor read the text layer; revision "B" parsed; `source_object_key` = the raw PDF key) → `embedded_chunks` (1 chunk). The `source-url` service authorized the tenant and presigned the **raw PDF** key. Tenant + R2 objects torn down after.

## Follow-ups (still deferred, argued)
- **Region highlight (AC2):** store per-chunk bounding boxes during PDF extraction, then a PDF.js text-layer highlight. A data-plane + extraction change.
- **Real per-user auth (Entra ID)** — a distinct hardening story; the shared dev token behind the BFF suffices for the MVP/demo.
- **Real per-user auth (Entra ID)** — a distinct hardening story (app registration + OIDC in Next + JWKS validation on the API); the shared dev token behind the BFF suffices for the MVP/demo.
- Tailwind/design system.

## Concepts
Reuses [auth-rbac](../../concepts/auth-rbac.md), [grounded-answers](../../concepts/grounded-answers.md), [retrieval](../../concepts/retrieval.md), [multi-tenancy](../../concepts/multi-tenancy.md).
