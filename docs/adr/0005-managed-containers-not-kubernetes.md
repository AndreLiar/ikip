# 0005. Managed containers (Azure Container Apps) over Kubernetes at MVP

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** Architect, PM
- **Related:** NFR3, NFR13, NFR14, NFR17 · Stories 6.6, 6.7, 6.8 · `../architecture.md` (Tech Stack, Infrastructure and Deployment) · relates to [ADR 0003](./0003-local-first-ports-and-adapters.md)

## Context
IKIP is a modular set of containerized services (api, web, background/processing workers, Dagster-triggered batch) that must deploy to Azure with reproducible environments (dev/staging/prod), safe migrations, rollback, autoscaling where justified, and a 99.5% pilot availability target (NFR3, NFR13, NFR14; Epic 6). The runtime platform could be a managed container service (Azure Container Apps) or a Kubernetes cluster (AKS). A production deployment "is not complete simply because it runs on Kubernetes" — it must have tested quality, authorization, monitoring, ownership and recovery regardless of platform.

## Decision
Use **Azure Container Apps** (Consumption/serverless containers) as the MVP runtime for the API, web and workers, with **Container Apps Jobs** for Dagster-triggered batch processing. **Do not adopt Kubernetes/AKS at MVP.** Keep workloads as plain OCI containers (built locally via Docker Compose, [ADR 0003](./0003-local-first-ports-and-adapters.md)) so the runtime platform remains a deployment detail, not a code dependency.

## Consequences
**Positive**
- Minimal operational surface: no cluster to run, patch, secure or pay for when idle; Consumption has free monthly grants and scales to zero for low-traffic apps — fits the lean-pilot budget.
- Built-in ingress/TLS, revisions, scaling and rollback cover NFR3/NFR13/NFR14 needs without bespoke cluster tooling.
- Faster path to a running pilot; effort goes into quality/security/recovery rather than cluster plumbing.
- Containers stay portable — a later move to AKS is a deployment change, not an application rewrite.

**Negative / risks**
- Less control than raw Kubernetes (no arbitrary operators/CRDs, custom schedulers, service mesh, or fine-grained networking).
- Some advanced networking/isolation and multi-region HA patterns are more constrained than AKS.
- Dagster's long-running control plane (scheduler/UI) must be modeled as an always-on Container App rather than a cluster deployment.

**Neutral**
- Autoscaling is capacity/consumption-based rather than custom HPA rules.

## Alternatives Considered
- **AKS (managed Kubernetes):** maximum control and ecosystem, and a strong learning artifact — but always-on cluster cost, large operational/security burden, and premature complexity for MVP scale. Rejected now; a candidate later.
- **Plain VMs + Docker / docker-compose in prod:** cheap but poor on scaling, rollout, health and recovery; more undifferentiated ops. Rejected.
- **A PaaS that abstracts containers away (e.g., App Service):** viable for the web/api but weaker for mixed worker/batch and Dagster topology. Rejected as the primary platform.

## Revisit When
- Workloads need Kubernetes-specific capabilities (operators/CRDs, service mesh, custom scheduling, fine-grained network policy), **or**
- Scale/traffic or multi-region HA/DR requirements exceed what Container Apps provides economically, **or**
- The team wants Kubernetes as an explicit objective — in which case prototype on local `kind`/`k3d` first to contain cost (per the project's stated approach).
