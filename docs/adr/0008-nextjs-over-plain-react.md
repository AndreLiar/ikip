# 0008. Next.js (framework) over plain React (SPA) for the web app

- **Status:** Accepted
- **Date:** 2026-11-03
- **Deciders:** Architect, PM
- **Related:** FR21, FR22, FR23, FR24, FR26 · NFR2, NFR10, NFR11 · Epic 4 (Stories 4.2, 4.4, 4.5, 4.7) · `../architecture.md` (Tech Stack, Components) · relates to [ADR 0005](./0005-managed-containers-not-kubernetes.md)

## Context
IKIP needs a web front end for a multi-tenant, authenticated SaaS: search + AI assistant, a document viewer that opens the cited PDF page, equipment catalog, document management and admin/operations dashboards (Epic 4). The choice is **not** "Next.js vs React" — Next.js *is* React. The real decision is **plain React as an SPA** (e.g., Vite + react-router, client-rendered) **vs the Next.js framework** (React + file-based routing, server rendering / React Server Components, streaming, and backend-for-frontend routes).

Forces specific to IKIP:
- Many routed screens (search, chat, viewer, catalog, admin, dashboards) — real routing, not a single page.
- Authentication (OIDC / Microsoft Entra ID) and **authorize-before-retrieval** (FR21, NFR10): sensitive logic and tokens should stay server-side, not be shipped to the browser.
- RAG answers **stream** token-by-token; progressive server→client rendering supports the p95 time-to-first-token target (NFR2).
- Deploys as a container on Azure Container Apps ([ADR 0005](./0005-managed-containers-not-kubernetes.md)); production conventions (bundling, code splitting, caching) are wanted out of the box.
- Stated project learning goal: demonstrate industry-standard tooling.

## Decision
Build the front end with **Next.js (App Router) + React**. Use server components / server-side rendering for data fetching and auth-gated pages, server actions / route handlers as a thin **backend-for-frontend (BFF)** in front of FastAPI (session, OIDC token handling, streaming), and file-based routing for the multi-screen app. The React component model is retained; Next.js supplies the framework around it. The app is packaged as an OCI container (no platform lock-in).

## Consequences
**Positive**
- **Routing, SSR/Server Components, streaming and a BFF layer are built-in** instead of assembled from separate libraries.
- Auth logic and tokens can execute **server-side**, reducing client exposure — aligns with tenant-isolation and authorize-before-retrieve posture (FR21, NFR10, NFR11).
- Native server→client **streaming** fits streamed RAG answers (NFR2).
- Production defaults (code splitting, caching, image optimization) for a heavy multi-screen app.
- Runs as a container on Azure Container Apps; a later platform change is a deployment concern, not a rewrite.

**Negative / risks**
- More opinionated; the App Router / Server Components model has a learning curve.
- SSR adds a **server runtime to operate** (a pure SPA could be served as static files).
- Framework version churn (Next.js moves fast); upgrades need attention.

**Neutral**
- Still React under the hood — component skills and libraries transfer.

## Alternatives Considered
- **Plain React SPA (Vite + react-router), client-rendered:** simplest runtime (static hosting), but you hand-build routing, any SSR, a separate BFF, and streaming plumbing; auth/tokens tend to live client-side. Legitimate for a static or single-screen app — rejected for a multi-screen, authenticated, streaming SaaS.
- **Another meta-framework (Remix, SvelteKit, Nuxt):** comparable capabilities, but Next.js is the de-facto React production framework with the strongest ecosystem/OIDC patterns and the clearest portfolio value. Rejected to avoid divergence from the React choice.
- **Server-rendered templates (no SPA framework):** too limited for the interactive search/chat/viewer UX. Rejected.

## Revisit When
- The UI collapses to a single static screen or a widget where SSR/BFF add no value (drop to a plain React SPA), **or**
- Operating the SSR server runtime becomes disproportionate to the benefit, **or**
- A different framework offers a decisive advantage for IKIP's specific UX/auth/streaming needs.

> **Honest framing (consistent with [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md) explainers):** nothing here *requires* Next.js — routing, SSR, a BFF and streaming can all be built in plain React + Python. This is **build vs. buy** (adopt the framework rather than re-implement its features) plus the stated learning/portfolio goal — not a claim that plain React is incapable.
