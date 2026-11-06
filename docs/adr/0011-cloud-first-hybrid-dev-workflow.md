# 0011. Cloud-first (hybrid) development workflow + cost strategy

- **Status:** Superseded by [ADR 0012](./0012-local-first-dev-cloud-models-only.md) (2026-11-06)
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** NFR12, NFR13, NFR16, NFR17 · Epic 6 (Stories 6.6, 6.7, 6.8) · builds on [ADR 0003](./0003-local-first-ports-and-adapters.md); relates to [ADR 0005](./0005-managed-containers-not-kubernetes.md)

> ⚠️ **Superseded.** This cloud-first hybrid workflow was reversed in favour of **local-first, cloud for models only** — see [ADR 0012](./0012-local-first-dev-cloud-models-only.md). Reason: cost (no always-on cloud dev budget) + the model must be cloud anyway (no GPU for a local model), so a cloud dev environment was not required. The cost-control content below still applies to the **deployment (staging/prod) phase**.

## Context
The original plan was **local-first** (NFR17): develop fully on a laptop with Docker, deploy to Azure later. The developer has chosen to **develop primarily on the cloud (Azure)** instead — an explicit learning objective: gain hands-on experience with managed identity, Key Vault, Terraform applied for real, deployment, and Azure Cost Management.

This is a workflow decision, not an architecture change: the ports & adapters design ([ADR 0003](./0003-local-first-ports-and-adapters.md)) was built so the same code runs local or on Azure. Developing on the cloud means selecting the Azure adapters earlier — not abandoning the interfaces.

Two forces to balance: (1) real cloud experience + cost-management practice (the learning goal); (2) not paying for every code iteration, and keeping tests fast and hermetic.

## Decision
Adopt a **hybrid cloud-first workflow**:

- **Azure is the primary development environment** — a dedicated, tagged dev resource group with a strict budget + alerts. Terraform provisions it ([ADR 0005](./0005-managed-containers-not-kubernetes.md), Story 6.6). This is where IaC, managed identity, Key Vault, deployment and Cost Management are learned.
- **Local Docker is kept as the fast, free inner loop** — unit tests, business logic and quick iteration run locally against mocked ports / local adapters, so debugging a typo never costs money and tests stay hermetic.
- **The ports & adapters boundary is non-negotiable:** services depend on interfaces, never on Azure SDKs directly ([ADR 0003](./0003-local-first-ports-and-adapters.md)). This is what keeps both loops working and tests mockable.

### Cost-control strategy (part of the decision, and itself the learning)
1. **Budgets + anomaly alerts + resource tags from day one** (Azure Cost Management) — the first exercise.
2. **Stop the dev PostgreSQL Flexible Server when not working** (the main always-on cost; stoppable up to 7 days) and use the cheapest burstable tier (e.g., B1ms).
3. **Container Apps on Consumption (scale-to-zero)** — pay per use.
4. **Azure for Students credit** (if eligible) covers most dev spend.
5. **Dedicated, destroyable dev environment** (Terraform) — tear down what is ephemeral; note persistent storage/DB still cost while they exist.
6. Watch **Azure Monitor log retention** (grows with volume).

Indicative dev-on-cloud cost, well managed: **~$30–70/month** (dominated by PostgreSQL if left running; Container Apps/Blob/Service Bus negligible; Azure OpenAI per-token) — consistent with the brief's "Stage 2 ~$50–200/month if resources run selectively."

## Consequences
**Positive**
- Real, continuous cloud experience; Cost Management practiced hands-on (a stated goal).
- No "works on my machine" gap with production; deployment/identity/networking exercised throughout.
- Ports kept intact → local inner loop still available; tests stay fast and free.

**Negative / risks**
- Ongoing dev spend (mainly PostgreSQL) vs. $0 local-only; requires discipline (stop/teardown, budgets).
- Risk of surprise cost from a left-on resource or a large OCR/LLM run — mitigated by budgets/alerts.
- Slightly more setup before first run (provision dev env) than pure local.

**Neutral**
- CI still runs against local/containerized dependencies (hermetic, free).

## Alternatives Considered
- **Pure local-first (original NFR17):** cheapest, but defers all cloud learning and leaves a local↔prod gap. Rejected per the learning objective.
- **Full cloud-first (no local loop):** maximal cloud immersion, but you pay to debug trivial changes and tests become slow/non-hermetic. Rejected in favour of the hybrid.

## Revisit When
- Dev cost exceeds the budget despite controls → shift more of the inner loop back to local.
- The learning objective is met and cost-efficiency dominates → reduce the always-on dev footprint.
- A shared team dev environment is needed → formalize environments/roles.

> **NFR17 is reframed, not removed:** staying runnable locally remains a capability (tests, CI, onboarding, cost fallback); the *default developer workflow* is now cloud-first per this ADR.
