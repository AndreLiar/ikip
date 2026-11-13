# MISSION-039 — Encryption, Secrets & PII Handling (Epic 6, Story 6.4)

**Mode:** Autonome (ports + CI now; cloud enforcement deferred to 6.6) + knowledge transfer.
**Objective:** managed secrets (`.env` local / Key Vault prod), PII detection/anonymization (Presidio, self-hosted), dependency/security scanning in CI, encryption + controlled object storage.
**Maps to:** Epic 6 / Story 6.4. Closes threats T7 (secrets), T8 (PII), T9 (supply chain); T11 (object storage) partial.

## What's enforceable now vs at deployment
Code/CI (this PR, zero cloud): the **ports + adapters + CI scanning**. Encryption-at-rest (AC1) and the R2 bucket-policy/lifecycle (AC5) are **managed-service + Terraform** concerns → documented here, enforced in Story 6.6. TLS-in-transit is provided by the managed endpoints (Neon/R2/Azure, all HTTPS).

## What was built
- **`SecretsProvider` port** (`ikip_common/secrets.py`): `EnvSecretsProvider` (process env / `.env`) + `KeyVaultSecretsProvider` (lazy `azure-identity` + `azure-keyvault-secrets`, managed identity; `A_B → a-b` name mapping) + `build_secrets_provider` (Key Vault when `AZURE_KEY_VAULT_URL` set + SDK present, else env fallback). `Settings` stays the typed local loader; this is the prod seam for 6.6. (AC2)
- **`PiiScrubber` port** (`ikip_common/pii.py`): `PresidioPiiScrubber` (lazy `pii` group — open-source, self-hosted, no paid service) + deterministic `RegexPiiScrubber` CI fallback (email/phone/IP/IBAN/card → typed placeholders, never echoes the raw value) + `NullPiiScrubber` + `build_pii_scrubber` (`PII_SCRUB` flag). Policy: content is **hash/ID-only by default** (NFR16, traces); scrub before any deliberate capture. Presidio does PII only — **not** harm/injection moderation (that's 5.3/6.3). (AC3)
- **CI `security-scan` job** (AC4): `pip-audit` (Python) + `pnpm audit --audit-level high` (web) on every PR, non-blocking (surfaced in logs; transitive CVEs don't block unrelated work).
- **Config:** `AZURE_KEY_VAULT_URL`, `PII_SCRUB`; dep groups `pii`, `keyvault`; `.env.example`.
- **Docs:** threat model T7/T8/T9 → `[implemented: 6.4]`.

## Acceptance (Story 6.4)
1. Encrypted in transit + at rest. — **[partial]** TLS everywhere (managed HTTPS endpoints); at-rest is Neon/R2 managed — **documented; verified/provisioned in 6.6**.
2. `SecretsProvider` (.env local / Key Vault prod). — **[verified]** (port + Env + KeyVault adapters + build + tests; live Key Vault at 6.6).
3. PII via Presidio behind `PiiScrubber`; secrets never logged. — **[verified]** (port + Presidio/Regex/Null + tests; `SecretStr` + CI secret-guard already prevent secret logging).
4. Dependency + security scanning in CI. — **[verified]** (`security-scan` job).
5. Controlled R2 (private, scoped tokens, presign-only, raw/curated separated, lifecycle). — **[partial]** presign-only + separation implemented; bucket policy/lifecycle in 6.6 (ADR 0014).

## Verification
- ruff + format ✓; `pytest apps packages services` → **267 passed / 48 skipped**. Secrets/PII suite = 10 tests (env provider, KeyVault fallback, regex redaction incl. no-raw-leak, Null/disabled, Presidio fallback).

## Deliverables
- `ikip_common/secrets.py`, `ikip_common/pii.py`; `config.py` (2 fields); `pyproject.toml` (`pii`, `keyvault` groups); `.env.example`.
- `.github/workflows/ci.yml` (`security-scan` job); `tests/test_secrets_pii.py`; threat-model updates.

## Follow-ups (noted)
- 6.6: live Key Vault + managed identity via Terraform; R2 bucket policy/lifecycle; verify encryption-at-rest.
- Optional: wire `PiiScrubber` into a content-capture path once `telemetry_capture_content` captures content (scrub-before-capture); a PII metric on the dashboard.

## Concepts
Realises [security.md](../../architecture/security.md) controls; closes threat-model T7–T9. Ports per ADR 0003.
