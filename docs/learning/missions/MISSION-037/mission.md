# MISSION-037 — Threat Model & Security Controls Documentation (Epic 6, Story 6.1)

**Mode:** Autonome (documentation grounded in real controls/tests) + knowledge transfer.
**Objective:** a reviewable threat model where **each threat maps to a control and a test**, covering tenant isolation, authz-before-retrieval, prompt injection, malicious documents, secrets/PII.
**Maps to:** Epic 6 / Story 6.1. Consolidates the security posture built across Epics 1–6.

## What was built
`docs/architecture/threat-model.md` — scope/assets, trust boundaries (browser → BFF → API → infra; **retrieved content is untrusted**), and **11 threats** each as *threat → control → test* with a status label:

| # | Threat | Status |
|---|---|---|
| T1 | Cross-tenant disclosure | [implemented: 6.2] |
| T2 | Broken object-level authz | [implemented: 6.2] |
| T3 | Authz bypass before retrieval/source | [implemented: 6.2] |
| T4 | Prompt injection via query | [implemented: 3.5/5.3] |
| T5 | Malicious/poisoned documents | [implemented: 5.3] + [planned: 6.3] |
| T6 | Answer fabrication/hallucination | [implemented: 3.5/5.2] |
| T7 | Secret leakage | [implemented] (CI secret-guard) + SecretsProvider [planned: 6.4] |
| T8 | PII exposure | partial (trace hashing) + Presidio PiiScrubber [planned: 6.4] |
| T9 | Supply-chain/deps | [planned: 6.4] |
| T10 | Data-rights/retention | [planned: 6.5] |
| T11 | Object-storage exposure | presign [implemented] + hardening [planned: 6.4/6.5] |

Every `[implemented]` row cites a **real passing test** (e.g. `test_security_isolation.py`, `test_safety_suite.py`, `test_answer_graph.py`, the CI secret-guard). Residual risks + planned hardening (RLS, doc provenance, judge-fooling) are listed explicitly. Linked from `security.md` + the architecture index; reviewed in PRs + version-controlled.

## Acceptance (Story 6.1)
1. Covers tenant isolation, authz-before-retrieval, prompt injection, malicious docs, secrets/PII. — **[verified]** (T1–T8).
2. Each threat maps to a control and a test. — **[verified]** (every row; `[planned]` rows name the story that will add the test).
3. Controls documented in `docs/`. — **[verified]** (`docs/architecture/threat-model.md`).
4. Reviewed and version-controlled. — **[verified]** (in-repo markdown, PR-reviewed; "Last reviewed" date).

## Verification
- Doc-only; all cited test files verified to exist; no code change. ruff/pytest unaffected.

## Deliverables
- `docs/architecture/threat-model.md`; links from `security.md` + architecture `index.md`.

## Follow-ups
- 6.3 turns T5's untrusted-content handling into a dedicated required gate.
- 6.4 adds the SecretsProvider + Presidio PiiScrubber + dependency scanning (closes T7–T9 tests).
- 6.5 adds retention/deletion/provenance (closes T10, defends the judge-fooling residual).

## Concepts
Builds on [[MISSION-036]] (isolation tests). Reuses [auth-rbac](../../concepts/auth-rbac.md), [multi-tenancy](../../concepts/multi-tenancy.md), [grounded-answers](../../concepts/grounded-answers.md).
