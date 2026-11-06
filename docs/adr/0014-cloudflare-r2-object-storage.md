# 0014. Cloudflare R2 for object storage (S3-compatible), replacing MinIO + Azure Blob

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR22, FR23 · NFR11, NFR15, NFR16, NFR17 · Story 2.1, 6.4, 6.5 · supersedes the storage choice inside [ADR 0003](./0003-local-first-ports-and-adapters.md); relates to [ADR 0012](./0012-local-first-dev-cloud-models-only.md)

## Context
Object storage holds raw/cleaned/curated document artifacts behind the `ObjectStorage` port ([ADR 0003](./0003-local-first-ports-and-adapters.md)). The plan used **MinIO** locally and **Azure Blob** in prod. Both are reachable via the S3 API (MinIO is S3; Azure Blob natively differs). **Cloudflare R2** is S3-compatible with a generous free tier and **zero egress fees**:

- Storage: **10 GB/month free**, then $0.015/GB.
- Class A ops (writes/list): **1M/month free**, then $4.50/M.
- Class B ops (reads): **10M/month free**, then $0.36/M.
- **$0 egress** — unlike Azure Blob, which bills egress.

The MVP corpus is ~10 GB (≈100–500 manuals), i.e. within R2's free tier; and the document viewer serves PDFs (egress-heavy), where zero egress is a direct saving. The project is cost-conscious and local-first ([ADR 0012](./0012-local-first-dev-cloud-models-only.md)).

## Decision
Use **Cloudflare R2 as the object storage for all environments** (dev, staging, prod), behind the existing `ObjectStorage` port via a single **S3-compatible adapter** (e.g., boto3-style). This replaces Azure Blob in prod and MinIO as the default dev backend.

- **MinIO is retained as an optional, offline/hermetic backend** for local tests — same S3 API, so it is a config/env switch, not extra code. This keeps NFR17 satisfiable (fully-offline runnable).
- R2 credentials are **scoped API tokens** (access key id + secret, bucket-scoped), stored via the `SecretsProvider` (`.env` locally, Key Vault in prod) — never committed.
- Buckets are **private**; the document viewer uses **presigned URLs** (short-lived) for source access (FR23).
- Raw/cleaned/curated remain logically separated (NFR15); lifecycle/retention configured (Story 6.5).
- IaC via the **Cloudflare Terraform provider** (alongside azurerm for the rest).

## Consequences
**Positive**
- **Cheaper:** MVP fits R2's free tier; **zero egress** removes the main Blob cost driver (serving PDFs).
- **One S3 adapter** for dev, test and prod → simpler than MinIO-S3 + Azure-Blob-native; true local↔prod parity on the *same* service.
- No vendor lock to Azure for storage; R2 is portable S3.

**Negative / risks**
- **Cross-cloud:** Azure compute + Cloudflare storage — a second vendor/account, minor added latency; egress-free serving offsets this.
- **Data residency:** R2 location is not Azure France Central — acceptable for licensed sample/MVP data, but real EU-customer data may require revisiting (see below).
- R2 uses access-key/secret, not Azure managed identity — secrets must be managed (Key Vault) and rotated.

**Neutral**
- The `ObjectStorage` port is unchanged; only the adapter/config changes (the point of [ADR 0003](./0003-local-first-ports-and-adapters.md)).

## Alternatives Considered
- **MinIO (dev) + Azure Blob (prod), as originally planned:** native Azure integration + managed identity, but Blob bills egress and splits the adapter (MinIO-S3 vs Blob-native); no free serving. Rejected on cost.
- **MinIO everywhere (self-hosted in prod):** free software but you operate the storage + durability/backup yourself. Rejected — R2 free tier removes the ops burden.
- **Azure Blob everywhere incl. an S3-gateway:** keeps one cloud but adds egress cost and complexity. Rejected.

## Revisit When
- **Data residency / compliance** requires EU-pinned storage or an all-Azure footprint for real customer data → move the prod adapter to Azure Blob (France Central). The port makes this a config change.
- Usage exceeds R2's free tier materially and another provider is cheaper at that scale.
- Cross-cloud latency between Azure compute and R2 becomes a measured problem.
