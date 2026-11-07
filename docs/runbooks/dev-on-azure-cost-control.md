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

## Database: Neon serverless Postgres (scale-to-zero)
- The database is **Neon** (not Azure Flexible Server) — it **scales compute to zero** when idle, so there is **no always-on DB cost**; the free tier covers early usage ([ADR 0015](../adr/0015-neon-serverless-postgres.md)).
- Watch **free-tier storage vs vector volume** (~400k × 1536-dim vectors ≈ ~2.4 GB): reduce embedding dimensions (256–512) or use `halfvec`, else move to Neon's modest paid tier (still scale-to-zero).
- Mind **cold-start latency** vs NFR1 on the first query after idle — use a warm/min-compute setting on the hot path if needed.
- This removes the previous "stop the Postgres server" chore entirely.

## Keep everything else near-zero
- **Container Apps on Consumption** → scale-to-zero; pay per request/CPU-second.
- **Object storage (Cloudflare R2, not Azure Blob):** MVP corpus (~10 GB) fits R2's **free tier** (10 GB storage, 1M Class A + 10M Class B ops/month) with **zero egress** → ~$0 ([ADR 0014](../adr/0014-cloudflare-r2-object-storage.md)).
- **Service Bus / ACR / Key Vault:** a few $/month combined at dev volume.
- **Azure OpenAI:** per-token; use small models and bounded eval runs during dev (brief §5).
- **Azure Monitor:** watch **log retention/volume** — it grows silently; keep dev retention short.

## The hybrid habit (don't pay to debug typos)
- Run the **local Docker loop** (MinIO/Redis/local Postgres/mocked ports) for unit tests, logic and fast iteration.
- Use the **Azure dev env** for integration, deployment, identity/secret wiring and cost-management practice.
- Ports & adapters ([ADR 0003](../adr/0003-local-first-ports-and-adapters.md)) make both work from the same code — never hardcode Azure SDKs.

## Weekly hygiene
- Check the Cost Management dashboard; confirm the budget trend.
- Neon scales to zero automatically — nothing to stop; just watch storage usage.
- **Tear down** any ephemeral resources not needed (Terraform); remember persistent storage/DB keep costing while they exist.

## Indicative monthly dev cost (well managed)
| Item | Est. | Note |
|------|------|------|
| Neon Postgres (serverless) | ~$0 | scale-to-zero; free tier covers early usage |
| Container Apps (consumption) | $0–20 | scale-to-zero |
| Cloudflare R2 (object storage) | ~$0 | free tier covers MVP; zero egress |
| Service Bus / ACR / Key Vault | ~$2–5 | negligible |
| Azure OpenAI (tokens) | $5–20 | per use |
| Monitor/logs | $2–10 | retention-dependent |
| **Total** | **~$30–70/mo** | lower with student credit + stopped DB |

## Azure OpenAI rate limits (S0) — 429s during bulk ingestion
The default **S0** pricing tier has a low per-minute call/token rate. Embedding a large
document in one shot returns **429 (rate limit exceeded)**. Mitigations, in order:

1. **In code (already):** the embedding adapter batches inputs (`EMBEDDING_BATCH_SIZE`,
   default 16) and retries 429s with exponential backoff. Lower the batch size on very
   constrained tiers; raise it once you have more quota.
2. **Raise the deployment capacity (TPM):** bump `embedding_capacity` / `chat_capacity`
   in `infrastructure/terraform/environments/dev` and `terraform apply` (DataZoneStandard
   capacity = thousands of tokens/min). This is the real fix for sustained bulk ingestion.
3. **Request a quota increase:** Azure portal → the OpenAI resource → *Quotas* →
   request more RPM/TPM (https://aka.ms/oai/quotaincrease). Portal action, not IaC.

For a one-off backfill, option 1 (small batch + backoff) is enough; for a large corpus,
do option 2.
