# MISSION-013 — Decisions

## D1 — Provision Azure OpenAI with Terraform (IaC), not the Foundry portal
**Problem:** we need a real Azure OpenAI embedding deployment for Story 3.2.
**Choice:** declare it in Terraform (`azurerm_cognitive_account` kind `OpenAI` + `azurerm_cognitive_deployment`).
**Why here:** the portal (Azure AI Foundry) and Terraform create the *same* underlying `Microsoft.CognitiveServices` resource; Terraform adds reproducibility (rej-playable), reviewability (in the repo, versioned) and clean teardown (`terraform destroy`). For a thesis, infra-as-code is a far stronger artifact than portal screenshots. It also opens Story 6.6 (full IaC).
**Alternative:** click-ops in the Foundry portal — faster for a one-off, but not reproducible, not reviewed, no code trace. Rejected.
**Trade-off:** Terraform has a learning curve + local state to manage (deferred remote backend). Worth it.
**Prefer the alternative when:** a true one-off throwaway resource with no intent to keep or document.

## D2 — Model `text-embedding-3-small` @ 512 dims
Full rationale in [ADR 0020](../../../adr/0020-embedding-model-text-embedding-3-small.md). Summary: cheapest model that beats legacy `ada-002`; Matryoshka lets us truncate to 512 dims to fit Neon ([ADR 0015](../../../adr/0015-neon-serverless-postgres.md)) with little quality loss; upgrade path to `3-large` is additive via `model_version` (FR14).

## D3 — Deployment SKU `DataZoneStandard` over `GlobalStandard`
**Problem:** `text-embedding-3-small` is only offered as `GlobalStandard` or `DataZoneStandard` (not `Standard` — found at apply time).
**Choice:** `DataZoneStandard`.
**Why here:** it confines model processing to the **EU data zone**, matching IKIP's EU-residency posture (a recurring theme / ADR 0015 revisit trigger), while staying in France Central. Billed ~ like the old Standard.
**Alternative:** `GlobalStandard` — cheapest and highest availability, but may process requests in any Azure region worldwide (weaker residency). Rejected for the residency posture; exposed as the `embedding_sku` variable so it's a one-line switch if cost/throughput ever outweighs residency.
**Prefer the alternative when:** residency is not a concern and you want the lowest price / highest global throughput.

## D4 — Account region France Central (fallback Sweden Central)
**Why:** EU residency + the model is available there. Sweden Central is the documented fallback (also EU) if a model/SKU is unavailable. The account was created once and kept; only the deployment SKU needed fixing, so no region change was required.
