# Security

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

- **Tenant isolation:** `tenant_id` scoping + object-level permissions on chunks/sources; automated cross-tenant tests are a CI gate.
- **Authorize-before-retrieve:** access resolved prior to retrieval and source access (FR21).
- **AuthN/Z:** OIDC/Entra ID; role-based; reusable authorization dependency.
- **Encryption:** TLS in transit; encryption at rest; secrets via Key Vault + managed identities; secrets/PII never logged.
- **Prompt injection / malicious docs:** retrieved content untrusted; restricted tool access; adversarial CI tests.
- **Governance:** licensing/provenance tracking; per-tenant retention; consistent deletion across raw/curated/index/embedding stores; audit logging of sensitive actions.
- **Threat model** maintained in `docs/` with each threat mapped to a control and a test (Story 6.1).

> Implemented by Epic 6 (Security, Governance & Cloud Operations) — see [`../prd/epic-6-security-governance-cloud-ops.md`](../prd/epic-6-security-governance-cloud-ops.md).
