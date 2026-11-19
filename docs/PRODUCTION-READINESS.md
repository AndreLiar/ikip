# IKIP — Production-Readiness Audit & Roadmap

> What the AI/RAG pipeline needs to be **production-grade and reliable**. Grounded in a code + CI +
> IaC audit (2026-11-19), then **each "missing" item verified against the repo** before listing —
> several items an initial pass flagged as missing actually exist (noted below). Legend:
> **✅ EXISTS** (verified in code) · **🟡 PARTIAL** (exists but incomplete/not enforced) · **🔴 MISSING**.

## Verdict in one line
The pipeline is **strong on correctness/safety** (grounding, citations, abstention, tenant isolation
are *structural*) and **good on eval + observability plumbing**. The real work left is **runtime
reliability & ops**: resource isolation (quotas), failure containment (circuit breaker), spend
ceilings, and turning *measured* SLOs into *enforced* gates. The 5 blockers below gate go-live.

## 🔴 The 5 blockers (tracked)
| # | Blocker | Why it gates prod | Issue |
|---|---------|-------------------|-------|
| 1 | **Per-tenant rate limiting / quota** | only a *global* `rate_limit_per_minute` exists (`config.py:54`) → one tenant can starve all others | [#144](https://github.com/AndreLiar/ikip/issues/144) |
| 2 | **Circuit breaker on the Azure LLM/embedding path** | `llm/azure.py` is retry+backoff only → sustained 429s add latency to *every* request (cascade) | [#145](https://github.com/AndreLiar/ikip/issues/145) |
| 3 | **Hard budget cap (global + per-tenant)** | the only cap is the agent loop's `max_cost_usd`, default **0.0 = off** → runaway spend | [#146](https://github.com/AndreLiar/ikip/issues/146) |
| 4 | **Wire the existing k6 load test as a CI perf gate** | `load/k6/ask_load.js` exists but isn't asserted → p95/TTFT (NFR1/2) can regress undetected | [#147](https://github.com/AndreLiar/ikip/issues/147) |
| 5 | **DR: documented + *tested* backup/restore (RPO/RTO)** | runbooks exist but none for rollback/restore; PITR is a capability, not a drill (Story 6.8) | [#148](https://github.com/AndreLiar/ikip/issues/148) |

---

## By dimension (verified)

### 1. Grounding & correctness safety — ✅ strong
- ✅ Server-resolved citations (opaque handles; `llm/answer.py`), grounding validator + abstention (ADR 0022), prompt-injection suite (`llm/injection.py`, `test_injection.py`) in the **blocking** safety gate (`ci.yml`).
- 🔴 **Cross-claim contradiction detection** — a self-contradicting answer ("X=10V" … "X=20V") is accepted.
- 🟡 Hallucination guard is itself an LLM judge (cross-encoder NLI deferred, ADR 0032 §3); no deterministic backstop.

### 2. Observability — 🟡 good plumbing, incomplete surfacing
- ✅ Tracing (Langfuse/OTel, ADR 0013), per-request latency/cost metrics (`telemetry/metrics.py`), cache hit/miss, Ragas→Langfuse.
- 🟡 Grafana dashboards/alerts present as config but thresholds not firing (no SLA/error-budget alert on p95>1.5s or error-rate).
- 🔴 **Dead-letter queue alerting** (jobs enter `dead_letter` silently — no metric/alert), **cost-anomaly alerting**, **per-tenant usage/cost view**.

### 3. Evaluation in CI — 🟡 safety gated, quality + perf not
- ✅ Safety gate **blocks PRs** (100% required, `ci.yml`). ✅ **config-regression gate runs on PR** (`config-regression.yml`). ✅ deterministic retrieval metrics.
- 🟡 **Ragas faithfulness is nightly + manual** (`ragas-eval.yml`: cron + workflow_dispatch) — **not a PR merge-blocker** (stochastic/LLM-cost). Decide: promote a bounded-sample Ragas gate to PR, or keep nightly-with-alert.
- 🔴 **No perf/throughput gate** (blocker #4), **no cost regression gate**, **no agent run-averaging** (a non-deterministic arm scored on 1 run — see MISSION-055 / issue #142).

### 4. Reliability / resilience — 🟡 the core gap
- ✅ Retry+backoff (`llm/azure.py`), bounded timeouts (R2/DB/Redis), dead-letter + state-machine for ingestion.
- 🔴 **Circuit breaker on the LLM path** (blocker #2). 🔴 **Idempotency keys on ingestion** (a DLQ re-run can index a doc twice — only an `attempts` counter today). 🔴 Graceful degradation under quota (serve stale cache / abstain vs back off every call).

### 5. Scalability / performance — 🟡
- ✅ halfvec+Matryoshka vectors (ADR 0020/0027), hybrid retrieval in SQL, answer + embedding caches.
- 🟡 pgvector HNSW tuning params not set; connection-pool sizing on SQLAlchemy defaults (Neon compute-unit risk).
- 🔴 No ingestion concurrency/batch ceiling (QoS across tenants); no per-request query timeout (slow-query DoS).

### 6. Security & governance — ✅ mostly
- ✅ Tenant isolation by construction (`db/repository.py`, `db/retrieval.py`), authorize-before-retrieve, PII scrubbing (`pii.py`, Presidio+regex), SecretsProvider/Key Vault, **`docs/architecture/threat-model.md` exists**, retention/deletion (Epic 6).
- 🟡 Document-level ACL only (no chunk-level); audit-event schema exists, retention policy of the audit log itself unclear.
- 🔴 **Per-tenant rate limiting** (blocker #1), **soft-delete audit trail** (what/who/when archived), **key rotation** (API + encryption) policy.

### 7. Cost controls — 🟡
- ✅ Token accounting (`metrics.record_cost`), batch controls, two-stage extraction (paid OCR only on demand), agent `AgentBudget`.
- 🔴 **Hard budget cap** (blocker #3), **cost-anomaly alert**, per-tenant cost attribution/chargeback.

### 8. Data quality — ✅ strong
- ✅ **Extraction quality scoring exists** (`services/document-processing/src/ikip_docproc/quality.py` — printable-ratio heuristic, low-quality flag + OCR routing), Pydantic/Pandera validation, dedup (checksum+SimHash), versioning/supersession, lineage.
- 🔴 Dead-letter *content* review/replay workflow (operator must query DB + re-upload); stale-document detection.

### 9. Deployment / ops — 🟡
- ✅ Terraform dev/staging/prod, reversible Alembic migrations, CI (lint/test/security/db-tests), health endpoint (`doctor.py`), **5 runbooks** (`docs/runbooks/`).
- 🔴 **No rollback/backup-restore/DR runbook** (blocker #5), no blue-green/canary, no feature-flag infra (changes are all-or-nothing), no staging→prod promotion gate visible in CI.

### 10. Agentic-specific reliability — 🟡 (new surface, Epic 10)
- ✅ Deterministic loop guardrails (max_steps / loop / no-progress / cost / kill-switch), controller-as-port, evidence dedup, trajectory audit (`agent/controller.py`).
- 🟡 Checkpointing deferred (ADR 0033) — a crash mid-loop loses progress.
- 🔴 **Agent arm not run-averaged** (non-deterministic; see #142), observation-growth token-blowup guard, bridge/conditional **routing** to confine per-step cost (issue #142).

---

## Honest caveats
- This is a **static audit** (code/CI/IaC read on 2026-11-19), not a live load/chaos test. SLO numbers
  (p95, error budget) are *goals in the PRD*, not measured production figures.
- "🔴 MISSING" means *not found in the repo* — a few may be partially handled at the platform layer
  (Neon/Azure defaults) or in infra not in this repo; confirm per item before building.
- Correctness/safety scored highest **because the measure-first discipline already stress-tested it**
  (grounding, injection, abstention all have gold sets + gates). The gaps cluster where there is **no
  gate yet** — which is exactly the next thing to build.

## Priority order (recommended)
Blockers **#144 → #148** first (resource isolation, failure containment, spend ceiling, perf gate,
DR drill). Then observability surfacing (dead-letter + cost-anomaly + SLA alerts) and the agentic
reliability items (#142: run-averaging + routing). Everything else is hardening.

## See also
`docs/architecture.md` · `docs/architecture/threat-model.md` · `docs/learning/synthesis.md` ·
issues [#144](https://github.com/AndreLiar/ikip/issues/144)–[#148](https://github.com/AndreLiar/ikip/issues/148), [#142](https://github.com/AndreLiar/ikip/issues/142) (agentic reliability).
