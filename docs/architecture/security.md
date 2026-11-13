# Security

_Sharded from `../architecture.md`. Part of the [architecture index](./index.md)._

- **Tenant isolation:** `tenant_id` scoping + object-level permissions on chunks/sources; automated cross-tenant tests are a CI gate.
- **Authorize-before-retrieve:** access resolved prior to retrieval and source access (FR21).
- **AuthN/Z:** OIDC/Entra ID; role-based; reusable authorization dependency.
- **Encryption:** TLS in transit; encryption at rest; secrets via Key Vault + managed identities; secrets/PII never logged.
- **Prompt injection / malicious docs:** retrieved content untrusted; restricted tool access; adversarial CI tests.
- **Governance:** licensing/provenance tracking; per-tenant retention; consistent deletion across raw/curated/index/embedding stores; audit logging of sensitive actions.
- **Threat model** maintained in `docs/` with each threat mapped to a control and a test (Story 6.1).

## Tenant isolation & authorization — threat → control → test (Story 6.2)

Zero cross-tenant disclosure is a **required CI gate**, proved at two layers:

| Threat | Control | Test (gate) |
|---|---|---|
| A caller reads another tenant's data | tenant is bound from the **authenticated JWT Principal**, never from the request body/params; endpoints pass `principal.tenant_id` to every service | `apps/api/tests/test_security_isolation.py` — a smuggled `tenant_id` in the body is ignored; distinct JWTs → distinct bound tenants (**required, `validate`**) |
| Unauthenticated data/source access | authorize-before-retrieve / -source-access | same file — `/retrieve`, `/ask`, `/documents/{id}/source-url` return **401** without a token (**required, `validate`**) |
| Cross-tenant leak in the SQL retrieval | `WHERE tenant_id = :tenant` on `chunk`/`embedding`; citation joins stay within tenant | `packages/common/tests/test_security_isolation_db.py` — identical content in two tenants; tenant A's lexical + vector search never returns B's chunk (**`db-tests`, ephemeral Neon**) |
| A user reads a document they're not entitled to (object-level) | `DocumentPermission` ACL applied **on chunks** in both retrieval arms: no ACL rows = tenant-public; else direct-user or workspace-membership grant | same DB file — a restricted doc's chunks are excluded for a non-permitted user, included via direct/workspace ACL (AC4) |
| Cross-tenant source-file access | the presign service resolves `version ∈ tenant` before issuing a short-lived URL | same DB file — tenant B's `DocumentVersion` is not resolvable under tenant A |

The required gate is the hermetic suite in `validate`; the SQL-layer proof runs on the per-run ephemeral Neon branch in `db-tests`.

> Implemented by Epic 6 (Security, Governance & Cloud Operations) — see [`../prd/epic-6-security-governance-cloud-ops.md`](../prd/epic-6-security-governance-cloud-ops.md).
