# 0012. Local-first development, cloud for models only (supersedes ADR 0011)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** [ADR 0011](./0011-cloud-first-hybrid-dev-workflow.md)
- **Deciders:** Architect, PM
- **Related:** NFR12, NFR17 · [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0005](./0005-managed-containers-not-kubernetes.md)

## Context
[ADR 0011](./0011-cloud-first-hybrid-dev-workflow.md) chose a cloud-first hybrid dev workflow (Azure as the primary dev environment) to maximise cloud learning. On reflection — driven by cost (no budget for an always-on cloud dev footprint) and a hardware fact (no GPU to run a capable local model such as Ollama) — the developer separated two decisions that were being conflated:

- **Where the model runs** — depends on GPU/VRAM. A capable local LLM needs a GPU the developer does not have → the model is **cloud** (Azure OpenAI / Foundry). This was always the plan ([ADR 0007](./0007-pluggable-llm-client-azure-openai.md)).
- **Where development happens** — independent of the above. Everything *except* the model (PostgreSQL+pgvector, MinIO, Redis, FastAPI, Next.js, Dagster) runs fine on the laptop.

The "can't run Ollama" constraint only forces the **model** to the cloud; it does **not** require a cloud dev environment.

## Decision
Adopt **local-first development; cloud for models only**:

- The full stack runs locally via Docker Compose (Postgres+pgvector, MinIO, Redis, api, web, Dagster).
- **Only LLM + embedding calls are remote** (Azure OpenAI / Foundry via the `LLMClient` port, [ADR 0007](./0007-pluggable-llm-client-azure-openai.md)).
- Azure is used for **deployment** (staging/prod) and to **learn the cloud at deploy time** — Terraform, managed identity, Key Vault, Container Apps, Cost Management (Epic 6) — not for day-to-day inner-loop development.
- Ports & adapters ([ADR 0003](./0003-local-first-ports-and-adapters.md)) make the local↔Azure switch configuration, not code.

This restores the original intent of **NFR17** (local-first, only AI calls remote).

## Consequences
**Positive**
- Cheapest dev loop: **~$5–30/month**, essentially just LLM/embedding tokens — no always-on cloud Postgres bill.
- Fast, offline-capable, hermetic inner loop and tests.
- Cloud skills still learned, concentrated at the deployment phase (Epic 6: IaC, identity, secrets, Cost Management).
- No architecture change — the model was already remote.

**Negative / risks**
- Less *daily* hands-on cloud exposure than ADR 0011 (mitigated: Epic 6 is a dedicated, real cloud exercise with staging+prod).
- A local↔cloud parity gap can appear if adapters drift — mitigated by the shared contract tests per port ([ADR 0003](./0003-local-first-ports-and-adapters.md)).
- Requires network for the remote model calls (true of any option here).

## Alternatives Considered
- **Cloud-first hybrid (ADR 0011):** more daily cloud immersion, but ongoing spend (PostgreSQL always-on) and pay-to-debug — rejected on cost given no budget.
- **Fully local incl. a local model (Ollama):** removes model cost, but needs a GPU the developer lacks and would underperform vs Azure OpenAI — not feasible.

## Revisit When
- A GPU / budget appears and running a local model becomes worthwhile (reconsider the model location, not just dev).
- The developer wants more continuous cloud practice and the budget allows an always-on dev env (revert toward ADR 0011).
- A shared team dev environment is needed.

> **Cost note:** the Azure cost runbook ([`../runbooks/dev-on-azure-cost-control.md`](../runbooks/dev-on-azure-cost-control.md)) now applies to the **staging/prod (deployment) phase**, not daily development. Entra ID stays free (managed identity, app registration, OIDC) regardless.
