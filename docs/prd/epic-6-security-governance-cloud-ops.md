# Epic 6 — Security, Governance & Cloud Operations

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Harden and operationalize the platform: a documented threat model, automated tenant-isolation and prompt-injection tests, encryption, audit logging, data retention/deletion and provenance tracking, Terraform IaC for dev/staging/prod, Azure deployment, and tested backup/recovery runbooks.

**Related requirements:** FR21, FR28, FR33 · NFR3, NFR4, NFR10, NFR11, NFR13, NFR14, NFR16, NFR18 · hardens Epics 1–5

---

## Story 6.1 Threat Model & Security Controls Documentation
As a security owner, I want a documented threat model and controls, so that security is explicit and reviewable.
**Acceptance Criteria:**
1. Threat model covers tenant isolation, authz-before-retrieval, prompt injection, malicious documents, secrets/PII.
2. Each threat maps to a control and a test.
3. Controls documented in `docs/`.
4. Reviewed and version-controlled.

## Story 6.2 Tenant Isolation & Authorization Security Tests
As a security engineer, I want automated isolation/authz tests, so that cross-tenant disclosure is provably prevented.
**Acceptance Criteria:**
1. Tests attempt cross-tenant reads across documents, retrieval and source access — all denied.
2. Authorization is verified before retrieval and before source file access.
3. Zero cross-tenant disclosure is a required CI gate.
4. Object-level permissions enforced on chunks/sources, not just documents.

## Story 6.3 Prompt-Injection & Malicious-Document Defenses
As a security engineer, I want defenses against injection and hostile content, so that retrieved content cannot subvert the system.
**Acceptance Criteria:**
1. Retrieved content is treated as untrusted; tool access is restricted.
2. Adversarial test cases (injection, hostile instructions in documents) are blocked/neutralized.
3. Failures are logged and surfaced.
4. Tests run in CI as a required gate.

## Story 6.4 Encryption, Secrets & PII Handling
As a security owner, I want encryption and managed secrets/PII handling, so that enterprise data is protected.
**Acceptance Criteria:**
1. Data encrypted in transit (TLS) and at rest.
2. `SecretsProvider` interface: `.env` locally, Azure Key Vault + managed identities in prod.
3. PII is identified and protected per policy; secrets never logged. **PII detection/anonymization uses Presidio** (open-source, self-hosted, local-first) behind a `PiiScrubber` port — no paid PII service required. _Presidio handles PII only; it is not a substitute for Content Safety (harm/injection moderation) — see [`../architecture/llmops-stack.md`](../architecture/llmops-stack.md)._
4. Dependency and security scanning run in CI.
5. **Controlled object storage (Cloudflare R2, S3-compatible):** buckets are private (no public access); access uses scoped R2 API tokens via the secrets provider / Key Vault (never committed); the document viewer uses short-lived presigned URLs only; raw/cleaned/curated are separated (NFR15); lifecycle/retention is configured (ties to Story 6.5). See [ADR 0014](../adr/0014-cloudflare-r2-object-storage.md).

## Story 6.5 Data Retention, Deletion & Provenance
As a governance owner, I want retention/deletion workflows and provenance tracking, so that we meet licensing and data-rights obligations.
**Acceptance Criteria:**
1. Document licensing/provenance tracked per source and version (see `../data-sources.md` licensing gate).
2. Retention policies configurable per tenant.
3. Deletion workflow removes data across raw/curated/index/embedding stores consistently.
4. Deletion and retention actions are audit-logged.

## Story 6.6 Infrastructure as Code & Environments
As a platform engineer, I want Terraform IaC for dev/staging/prod, so that environments are reproducible.
**Acceptance Criteria:**
1. Terraform modules provision the stack using multiple providers: **azurerm** (Container Apps, Service Bus, ACR, Key Vault, Azure Monitor), **Neon** (serverless Postgres + pgvector — [ADR 0015](../adr/0015-neon-serverless-postgres.md)), and **Cloudflare** (R2 buckets — [ADR 0014](../adr/0014-cloudflare-r2-object-storage.md)). _(Not Azure PostgreSQL Flexible Server / Blob Storage.)_
2. Separate dev/staging/prod environment configurations.
3. Secrets sourced from Key Vault via managed identities (no secrets in code); Neon/R2/Langfuse tokens stored in Key Vault.
4. `terraform plan/apply` documented in runbooks.

## Story 6.7 CI/CD with Quality & Security Gates and Safe Migrations
As a release manager, I want gated CI/CD with safe migrations and rollback, so that deployments are reliable.
**Acceptance Criteria:**
1. CI/CD builds, tests, scans and deploys to staging then production.
2. Deployment blocked unless quality + security + safety gates pass.
3. Database migrations are safe and reversible; rollback path documented.
4. Staging and production deploys are distinct and promotable.

## Story 6.8 Backup, Recovery & Operational Runbooks
As an operator, I want tested backups, recovery and runbooks, so that we meet reliability/recovery targets.
**Acceptance Criteria:**
1. Automated backups: **Neon** point-in-time recovery / branching for the database; **R2** object versioning (and/or cross-bucket copy) for object storage.
2. A restore is demonstrated within the agreed RPO/RTO (Neon PITR restore + R2 object restore).
3. Runbooks cover deployment, rollback, incident response and recovery.
4. Availability and recovery targets (99.5%, RPO/RTO) are documented and monitored.
