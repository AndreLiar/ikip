# 0010. Microsoft Foundry as model platform; no dedicated AI gateway at MVP

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR28, FR31, FR32 · NFR2, NFR19 · Epic 4 (Story 4.8), Epic 5 (Stories 5.4, 5.5) · builds on [ADR 0007](./0007-pluggable-llm-client-azure-openai.md); relates to [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0009](./0009-caching-strategy.md)

## Context
IKIP uses Azure OpenAI for generation + embeddings ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md)). Two platform questions arose: (1) use **Microsoft Foundry** (Azure AI Foundry) as the model platform, and (2) whether a **dedicated AI gateway** (e.g., Azure API Management GenAI gateway, or a third-party like LiteLLM/Portkey) is needed in front of the models.

An "AI gateway" centralizes cross-cutting LLM concerns: unified multi-provider API, routing/fallback/load-balancing across deployments, per-consumer rate-limiting and quotas, token/cost tracking and budgets, caching, tracing, and key management. The question is whether IKIP needs that as a **separate product** at MVP.

IKIP is, at MVP, a **single application** talking to a **single provider** (Azure OpenAI via Foundry). It already routes all AI traffic through one `LLMClient` port, enforces per-tenant quotas/rate-limits at the API layer (Story 4.8), tracks token/cost per query (FR31, `query_trace`), versions model/prompt configs (Story 5.5), and caches at the app layer ([ADR 0009](./0009-caching-strategy.md)).

## Decision
1. **Use Microsoft Foundry as the model platform** — model deployment and versioning, the unified inference endpoint / Model Router, content safety, and tracing/evaluation integration.
2. **Do not add a dedicated AI gateway at MVP.** The `LLMClient` adapter ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md)) is the **logical gateway**: the single choke point where IKIP centralizes cost/token tracking, tracing, retries/timeouts, and model/prompt configuration. Per-tenant rate-limits/quotas stay at the application API layer (Story 4.8).

Because all AI traffic already flows through the `LLMClient` port, introducing a gateway later (e.g., Azure API Management in front of Foundry) is a configuration change — point the adapter's base URL at the gateway — not an application rewrite.

## Consequences
**Positive**
- No extra managed product, cost, or operational surface at MVP; fewer moving parts to deploy via Terraform.
- Foundry covers model lifecycle, unified endpoint/routing, content safety and observability out of the box.
- The `LLMClient` port already provides the single governance/instrumentation point an app of this size needs.
- A future gateway is a drop-in via the port — no lock-in, no rewrite.

**Negative / risks**
- No centralized cross-app token rate-limiting or multi-deployment load-balancing yet — fine for one app, a gap once capacity is shared.
- Governance/security enforcement lives in the app layer, not a separate independent tier.
- Relies on Foundry's quota/throughput behavior; heavy 429/capacity handling would later want gateway-level smarts.

**Neutral**
- Content safety and evaluation can be driven from Foundry and/or the app's own eval harness (Epic 5).

## Alternatives Considered
- **Azure API Management (GenAI gateway) now:** token-based rate-limiting, load-balancing across Azure OpenAI deployments, semantic caching, managed identity. Rejected at MVP — solves multi-app/multi-deployment problems IKIP does not yet have; adds a paid tier and ops. The prime candidate when the triggers below fire.
- **Third-party AI gateway (LiteLLM, Portkey, Kong AI Gateway, Cloudflare AI Gateway):** multi-provider routing/fallback and observability, but another component to run and secure, and redundant with the `LLMClient` port + Foundry at this scale. Deferred.
- **No Foundry, raw Azure OpenAI SDK only:** loses model-deployment/versioning, unified endpoint, content safety and eval integration. Rejected.

## Revisit When
Introduce a dedicated AI gateway (prefer **Azure API Management GenAI gateway** in front of Foundry) when **any** of:
- **Multiple apps/teams share** Azure OpenAI capacity and need centralized token rate-limiting / load-balancing (PTU + PAYG spillover).
- **Multiple endpoints/regions** require fallback and smart 429/retry handling.
- Governance/security must be enforced as a **separate tier**, independent of the application.
- Cross-app semantic caching or budget enforcement at the edge becomes a requirement.
