# Runbook — Developing on Azure at low cost

_Cost figures are planning estimates — verify on the Azure Pricing Calculator for your region/tier._

> **Scope note:** development is **local-first** ([ADR 0012](../adr/0012-local-first-dev-cloud-models-only.md)) — daily inner-loop dev runs on the laptop, with only LLM/embedding calls remote (~$5–30/mo, mostly tokens). This runbook therefore applies to the **Azure staging/prod (deployment) phase** (Epic 6), and to any optional cloud dev environment — not to day-to-day development.

## Goal
Use Azure as the primary development environment (to learn IaC, identity, Key Vault, deployment and Cost Management) while keeping monthly spend low and predictable.

## Day-0 setup (do this first — it *is* the cost-management learning)
1. **Dedicated dev resource group**, separate from staging/prod; tag everything (`env=dev`, `project=ikip`).
2. **Azure Cost Management:** create a **budget** for the dev RG + **anomaly/threshold alerts** (e.g., email at 50/80/100%).
3. **Azure for Students** credit (if eligible) — apply before spending real money.
4. Provision the dev env with **Terraform** (Story 6.6) so it is reproducible and destroyable.

## The one cost that matters: PostgreSQL
- PostgreSQL Flexible Server is the main **always-on** cost (~$12–15/mo on the cheapest burstable **B1ms**; more on larger tiers).
- **Stop the server when not working** (Flexible Server can be stopped up to 7 days; it auto-restarts after). Start it only during dev sessions.
- Use the smallest burstable tier for dev; size up only in staging/prod.

## Keep everything else near-zero
- **Container Apps on Consumption** → scale-to-zero; pay per request/CPU-second.
- **Blob / Service Bus / ACR / Key Vault:** a few $/month combined at dev volume (Blob < $1 — see the MVP estimate in `../brief.md`).
- **Azure OpenAI:** per-token; use small models and bounded eval runs during dev (brief §5).
- **Azure Monitor:** watch **log retention/volume** — it grows silently; keep dev retention short.

## The hybrid habit (don't pay to debug typos)
- Run the **local Docker loop** (MinIO/Redis/local Postgres/mocked ports) for unit tests, logic and fast iteration.
- Use the **Azure dev env** for integration, deployment, identity/secret wiring and cost-management practice.
- Ports & adapters ([ADR 0003](../adr/0003-local-first-ports-and-adapters.md)) make both work from the same code — never hardcode Azure SDKs.

## Weekly hygiene
- Check the Cost Management dashboard; confirm the budget trend.
- Ensure dev **PostgreSQL is stopped** when idle.
- **Tear down** any ephemeral resources not needed (Terraform); remember persistent storage/DB keep costing while they exist.

## Indicative monthly dev cost (well managed)
| Item | Est. | Note |
|------|------|------|
| PostgreSQL B1ms | $0–15 | ~$0 if stopped most of the time |
| Container Apps (consumption) | $0–20 | scale-to-zero |
| Blob / Service Bus / ACR / Key Vault | ~$2–5 | negligible |
| Azure OpenAI (tokens) | $5–20 | per use |
| Monitor/logs | $2–10 | retention-dependent |
| **Total** | **~$30–70/mo** | lower with student credit + stopped DB |
