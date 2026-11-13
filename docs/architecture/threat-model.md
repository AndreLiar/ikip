# Threat Model — IKIP

_Part of the [architecture index](./index.md). Companion to [`security.md`](./security.md). Story 6.1._

A reviewable threat model for the multi-tenant RAG platform: **each threat maps to a control and a test** (AC2). Status is `[implemented]` (control + passing test today) or `[planned: Story x.y]`. This document is version-controlled and reviewed in PRs (AC4).

## Scope & assets
- **Assets:** tenant documents (raw/curated/indexed), embeddings, conversation history + feedback, audit/query traces, secrets (Azure/Neon/R2/Langfuse tokens), PII in documents.
- **Actors:** technician / admin users (per tenant), platform operators, build-time pipeline, external attacker, a *malicious document author* (content supply chain).

## Trust boundaries
```
Browser ──(same-origin, server-held token, ADR 0023)──▶ Next.js BFF
       BFF ──(JWT principal)──▶ FastAPI ──▶ { Neon (pgvector) · Cloudflare R2 · Azure OpenAI · Langfuse }
```
Everything right of the API is trusted infra reached with scoped credentials; **retrieved document content is NOT trusted** (it may be attacker-authored).

---

## Threats → controls → tests

### T1 — Cross-tenant data disclosure (Spoofing/Info-disclosure) · NFR10
- **Control:** `tenant_id` is bound from the authenticated JWT Principal (never the request); retrieval SQL scopes `WHERE tenant_id = :tenant` on `chunk`/`embedding`; the source-presign service resolves `version ∈ tenant`.
- **Test:** `apps/api/tests/test_security_isolation.py` (smuggled `tenant_id` ignored; 401 unauth — **required `validate` gate**) + `packages/common/tests/test_security_isolation_db.py` (identical content in 2 tenants → A never sees B; source version not resolvable cross-tenant — `db-tests`) + `test_tenant_isolation.py`. **[implemented: Story 6.2]**

### T2 — Broken object-level authorization (a user reads a doc they're not entitled to) · FR21
- **Control:** `DocumentPermission` ACL enforced **on chunks** in both retrieval arms — no ACL rows = tenant-public; else direct-user or workspace-membership grant.
- **Test:** `test_security_isolation_db.py::test_object_level_acl_*` (restricted chunk excluded for non-permitted user; granted via direct + workspace ACL). **[implemented: Story 6.2]**

### T3 — Authorization bypass before retrieval / source access (Elevation) · FR21
- **Control:** authorize-before-retrieve; every data endpoint requires a valid token and resolves access before touching data.
- **Test:** `test_security_isolation.py` (401 on `/retrieve`, `/ask`, `/documents/{id}/source-url` without a token) + `apps/api/tests/test_auth.py`. **[implemented: Story 6.2]**

### T4 — Prompt injection via the user query (Tampering) · FR16
- **Control:** the model sees only **opaque evidence handles**; citations are resolved **server-side** from trusted retrieval metadata — the model cannot fabricate a reference. Unsupported safety-critical claims force abstention; unknown handles are treated unsupported.
- **Test:** `packages/common/tests/test_answer_graph.py` (fabricated handle → unsupported; unsupported safety claim → abstain) + `test_grounding.py`. **[implemented: Stories 3.5/5.3]**

### T5 — Malicious / poisoned documents (hostile instructions in retrieved content) · ties NFR16
- **Control:** retrieved content treated as untrusted; grounding-entailment validation drops/abstains on injected instructions not supported by trusted evidence; a critical **safety-abstention gate** runs adversarial cases. Defense-in-depth: Azure Prompt Shields blocks jailbreak/indirect-injection at the model (observed live — a poisoned seed doc was blocked, recorded as `error`, never a silent answer).
- **Test:** `packages/common/tests/test_safety_suite.py` + `fixtures/safety/v1.json` (`malicious_document` cases) and `packages/common/tests/test_injection.py` (retrieved content scanned for injection → detected, **logged**, surfaced as a warning, instructions not followed) — both run in the **required `safety-gate` CI job**. The `ChatClient` port exposes **no tools/function-calling**, so the model cannot act on an injected instruction. **[implemented: Stories 5.3 + 6.3]**

### T6 — Answer fabrication / hallucination (Integrity of output) · NFR8
- **Control:** grounded-answer graph validates entailment and keeps only supported claims; abstains rather than inventing; every answer carries a not-certified notice.
- **Test:** `test_answer_graph.py`, `test_grounding.py`; eval harness `behavior_conformity` + Ragas `faithfulness` (Epic 5). **[implemented: Stories 3.5/5.2]**

### T7 — Secret leakage (committed secrets / secrets in logs) · NFR13
- **Control:** secrets typed as `SecretStr` (never in repr/logs); `.env` gitignored; CI secret-guard greps for committed key assignments / PEM blocks; traces store hashes + IDs, not raw content (NFR16).
- **Test:** `.github/workflows/ci.yml` "Guard against committed secrets" step (fails the build on a match); `test_secrets_pii.py` (env provider; Key Vault fallback). `SecretsProvider` port (`.env` locally ↔ Azure Key Vault + managed identity in prod, `ikip_common.secrets`). **[implemented: Story 6.4]** (Key Vault adapter [untested live] until deploy 6.6).

### T8 — PII exposure in documents/traces · NFR16
- **Control:** traces carry IDs + hashes, not raw prompts/content unless `TELEMETRY_CAPTURE_CONTENT` is explicitly on. A `PiiScrubber` port (Presidio, self-hosted) will detect/anonymize PII.
- **Test:** `test_query_trace.py` (query stored as sha256, not raw); `test_secrets_pii.py` (`RegexPiiScrubber` redacts email/phone/IP/IBAN/card; never leaks the raw value). `PiiScrubber` port — Presidio in prod, deterministic regex fallback in CI (`ikip_common.pii`); policy = hash/ID-only by default, scrub before any content capture. **[implemented: Story 6.4]** (Presidio adapter [untested live]).

### T9 — Supply-chain / dependency vulnerabilities
- **Control:** pinned dependencies (uv.lock / pnpm-lock); dependency + security scanning in CI.
- **Test:** `security-scan` CI job — `pip-audit` (Python) + `pnpm audit --audit-level high` (web), runs every PR (non-blocking, surfaced in logs). **[implemented: Story 6.4]**.

### T10 — Data-rights / retention violations (licensing, deletion) · FR33
- **Control:** per-source + per-version licensing/provenance (`document.rights` + a licensing gate); per-tenant retention (`tenant.policies["retention_days"]`); consistent deletion across raw/curated/index/embedding (DB cascade + explicit R2 key deletion); audit-logged (`data.delete` / `data.retention_sweep`). `ikip_common.db.retention`.
- **Test:** `test_retention.py` — license gate, provenance, delete-removes-all-stores + audits, tenant-scoped delete, retention sweep deletes only stale (DB-gated). **[implemented: Story 6.5]**.

### T11 — Object-storage exposure (public bucket / leaked URL) · NFR15
- **Control:** private R2 buckets; scoped API tokens via the secrets provider; the viewer uses **short-lived presigned URLs** only; raw/curated/source separated.
- **Test:** `apps/api/tests/test_documents_endpoint.py` (presign path authorizes version∈tenant). Bucket-policy/lifecycle hardening **[planned: Stories 6.4/6.5]** (ADR 0014).

---

## Residual risks & planned hardening
- **Non-determinism of prompt-level guards** (reasoning model @ temp 1): prompt mitigations are probabilistic — the deterministic guard is the server-side grounding policy + safety gate, not the prompt. (Measured; see [prompt-evaluation-workflow](../runbooks/prompt-evaluation-workflow.md).)
- **Judge-fooling poisoned docs**: a malicious doc the grounding judge is tricked into calling "supported" → defended by upcoming **document provenance/trust** (Story 6.5) so untrusted content isn't retrieved into the model.
- **RLS defense-in-depth**: application-layer tenant scoping is the current control; Postgres Row-Level Security is planned hardening (Story 6.2 note / Epic 6).
- **Required-gate coverage**: the hermetic isolation + safety suites are required gates (`validate`, `safety-gate`); the SQL-layer isolation proof runs in `db-tests` (not a branch-protection-required check on forks).

## Review
Changes to controls/tests are reviewed in PRs; this document is updated alongside the code it describes. Last reviewed: 2026-11-13 (Story 6.1).
