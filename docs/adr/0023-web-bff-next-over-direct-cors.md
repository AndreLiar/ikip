# 0023. Web app talks to the API via a Next.js BFF (server route handlers), not direct browser→API CORS

- **Status:** Accepted
- **Date:** 2026-11-08
- **Deciders:** Architect, PM
- **Related:** FR19–FR24 · NFR10, NFR11 · Epic 4 (Story 4.4) · builds on [ADR 0008](./0008-nextjs-over-plain-react.md) (Next.js), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md); relates to auth (Story 1.6)

## Context
The technician assistant UI (Story 4.4) calls the Epic 3 service (`/api/v1/retrieve`, `/api/v1/ask`) which is **authenticated** (bearer JWT) and **tenant-scoped** (authorize-before-retrieve, FR21/NFR10). Two ways for the browser to reach the API:

1. **Direct browser → FastAPI** with CORS enabled and the JWT held in the browser (localStorage/cookie).
2. **BFF (backend-for-frontend):** the browser calls **same-origin Next.js route handlers** (`/api/ask`, `/api/retrieve`) which run server-side and **proxy** to FastAPI, attaching a server-held token.

## Decision
Use the **BFF pattern**: the browser only ever talks to **same-origin Next.js route handlers**; those forward to FastAPI (`IKIP_API_URL`) with a **server-side bearer token** (`IKIP_API_TOKEN`, from the server env — dev-token now, Entra ID service identity later). No token or API base URL reaches the browser; no CORS configuration on the API.

Implemented in `apps/web`: `lib/bff.ts` (`proxyPost`), `app/api/ask/route.ts`, `app/api/retrieve/route.ts`; the page (`app/page.tsx`) fetches the same-origin routes.

## Consequences
**Positive**
- **No token in the browser** → no XSS token theft, no token in JS bundles/network tab. Access control stays server-enforced (Story 4.4 AC4).
- **No CORS** to open/maintain on the API; the API surface isn't exposed cross-origin to arbitrary web origins.
- **Seam for future concerns** (per-user session, rate-limit headers, request shaping, caching) lives in one server layer.
- Fits Next.js App Router ([ADR 0008](./0008-nextjs-over-plain-react.md)); SSR-friendly.

**Negative / risks**
- **Extra hop** (browser → Next server → API) adds minor latency vs direct.
- The Next server needs the API token in its env — one more secret to manage server-side (acceptable; it's not in the browser).
- A single shared `IKIP_API_TOKEN` is a **dev shortcut**; real per-user auth (Entra ID → per-request token exchange) is a follow-up before multi-user prod.

**Neutral**
- The TS contract is hand-typed (`lib/types.ts`); a generated client from the OpenAPI schema (Story 4.1) can replace it later.

## Alternatives Considered
- **Direct browser → FastAPI + CORS:** fewer moving parts, no proxy hop; rejected because it puts the JWT in the browser (theft surface) and requires CORS + exposes the API cross-origin. Acceptable only for a public, unauthenticated API.
- **Next.js Server Actions instead of route handlers:** viable, but route handlers are a clearer HTTP boundary to proxy + test, and keep the client/server split explicit.

## Revisit When
- Real multi-user auth lands (Entra ID): the BFF exchanges the user session for a per-request API token (still server-side) — reinforces this decision.
- Measured BFF latency is a problem at scale → consider edge runtime for the handlers or a thin gateway, but keep tokens server-side.
