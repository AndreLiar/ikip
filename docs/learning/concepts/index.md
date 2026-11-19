# Concept Map — AI, Data & Platform Engineering

The consolidated map of every concept this project exercised, grouped by domain, with links to the
write-once concept notes, the ADR that decided it, and — crucially — the **discoveries made by doing**
(what the measurements taught us). Part of the [learning log](../index.md); the big picture is in
[synthesis.md](../synthesis.md).

> Legend: 📄 concept note · 📐 ADR (decision) · 🔧 built/hardened in a mission · 💡 discovery.

---

## 1. AI / RAG Engineering

| Concept | Note / decision |
|---|---|
| Why RAG (context window isn't enough: cost/latency/quality/security/citations) | 📄 [why-rag](./why-rag.md) |
| Chunking (structure-aware, parent/child, overlap, tokens, citation chain) | 📄 [chunking](./chunking.md) · 🇫🇷 [strategies](./chunking-strategies.fr.md) · 📐 ADR 0019/0029 |
| Embeddings (vectors, dimensions, **Matryoshka** reduction, `model_version`, cost) | 📄 [embeddings](./embeddings.md) · 📐 [ADR 0020](../../adr/0020-embedding-model-text-embedding-3-small.md) |
| Lexical vs vector retrieval (tsvector/`ts_rank` vs pgvector/HNSW/cosine) | 📄 [retrieval](./retrieval.md) |
| Hybrid retrieval + **RRF** fusion + Reranker port (identity→cross-encoder) | 📄 [hybrid-retrieval](./hybrid-retrieval.md) |
| Grounded answers (LangGraph flow, opaque citation handles, server-resolved citations, grounding validation, abstention) | 📄 [grounded-answers](./grounded-answers.md) · 📐 ADR 0022 |
| Caching (answer + embedding cache, *key-as-correctness*) | 📄 [caching](./caching.md) · 📐 ADR 0009 |
| Memory (conversational L1 + long-term L2 → shapes *what we retrieve*) | 📐 [ADR 0032](../../adr/0032-memory-and-context-engineering.md) |
| Context engineering (dedup, lost-in-the-middle, token budget) — measured, mostly **rejected** | 📐 ADR 0032 §3 · 💡 [MISSION-047](../missions/MISSION-047/mission.md)/[053](../missions/MISSION-053/mission.md) |
| Multimodal retrieval (caption-and-embed; OCR vs Docling vs vision-LLM) | 📄 [multimodal-retrieval](./multimodal-retrieval.md) · 📐 ADR 0031 |
| How LangChain is used behind our ports (the 5 bricks) | 📄 [langchain-inventory](./langchain-inventory.md) · [rag-orchestration](./rag-orchestration.md) · 📐 [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) |

## 2. Agentic AI

| Concept | Note / decision |
|---|---|
| Flow vs agentic (who picks the steps) · Tool port + registry · cyclic **plan–act–observe** controller · deterministic guardrails (max_steps / loop / no-progress / cost / kill-switch) · grounding survives tool use | 📄 [agentic-rag](./agentic-rag.md) · 📐 [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) |
| Query **decomposition** (static fan-out) vs cyclic controller (dynamic loop) — distinct failure classes | 🔧 [MISSION-050](../missions/MISSION-050/mission.md)/[051](../missions/MISSION-051/mission.md)/[052](../missions/MISSION-052/mission.md) |
| **Bridge / conditional hop** (hop 2 needs hop 1's answer) · content-aware observations | 🔧 [MISSION-054](../missions/MISSION-054/mission.md)/[055](../missions/MISSION-055/mission.md) |
| Trajectory as audit trail · (discussed, not built) multi-agent = sub-agent-as-Tool, routing/detector | 📐 ADR 0033 · issue #142 |

## 3. LLMOps / Evaluation

| Concept | Note / decision |
|---|---|
| Gold datasets · deterministic metrics (Recall@K, citation resolution/coverage) | 📄 [rag-evaluation](./rag-evaluation.md) · [metrics](./rag-evaluation-metrics.md) |
| LLM-judged metrics (**Ragas**: faithfulness, answer_correctness, answer_relevancy, context_precision/recall) | 📄 rag-evaluation · 📐 ADR 0016 |
| A/B harness (fixed vs `--decompose` vs `--agent`) · per-corpus faithfulness regression gates in CI | 🔧 MISSION-044/047/050 |
| Prompt/model config versioning · tracing (Langfuse + OTel) · cost accounting | 📐 [ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md) |

## 4. Data Engineering

| Concept | Note / decision |
|---|---|
| **Dagster** orchestration — assets, schedules, **sensors**, `Definitions`, thin-wrapper pattern | 📄 [dagster-orchestration](./dagster-orchestration.md) |
| Dual orchestration — build-time plane (Dagster) vs request-time plane (LangGraph) | 📐 [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md) · trigger strategy 📐 ADR 0025 |
| PDF extraction — native vs scanned, two-stage PyMuPDF→OCR, quality scoring, per-page routing | 📄 [pdf-extraction](./pdf-extraction.md) · 📐 ADR 0024 |
| Data validation — Pydantic vs **Pandera**, report-not-raise | 📄 [data-validation](./data-validation.md) · 📐 ADR 0018 |
| Deduplication — exact (checksum) + near-dup (**SimHash**), supersede-not-delete · document versioning | 📄 [dedup-versioning](./dedup-versioning.md) |
| Lineage / provenance · reprocessing · retry · **dead-letter queue** | 📄 [lineage-reprocessing](./lineage-reprocessing.md) |
| Object storage — R2, blobs-vs-DB, tiers, presigned URLs | 📄 [object-storage](./object-storage.md) · 📐 ADR 0014 |
| Vector storage — pgvector, **halfvec** (16-bit → ½ storage), HNSW, Neon tier limits | 📐 [ADR 0027](../../adr/0027-vector-storage-halfvec-now-qdrant-later.md) |

## 5. Platform / Reliability / SaaS

| Concept | Note / decision |
|---|---|
| Ports & adapters (hexagonal) + **local-first** (fakes in CI, cloud-ready) | 📐 [ADR 0003](../../adr/0003-local-first-ports-and-adapters.md) |
| Multi-tenancy — `tenant_id` scoping, isolation **by construction**, RLS backstop | 📄 [multi-tenancy](./multi-tenancy.md) |
| Auth / RBAC — JWT, Principal, role hierarchy | 📄 [auth-rbac](./auth-rbac.md) |
| Config 12-factor — Pydantic Settings, SecretStr, fail-fast | 📄 [config-12-factor](./config-12-factor.md) |
| Health checks — liveness vs readiness, dependency probes | 📄 [health-checks](./health-checks.md) |
| Dev tooling — ruff, pytest, uv/pnpm workspaces | 📄 [dev-tooling](./dev-tooling.md) |
| **Circuit breaker** — fail-fast on sustained Azure outage (closed/open/half-open) | 🔧 📐 [ADR 0035](../../adr/0035-circuit-breaker-azure-llm.md) |
| **Per-tenant budget cap** — spend ledger, `/ask` 429 | 🔧 📐 [ADR 0034](../../adr/0034-per-tenant-budget-cap.md) |
| **Per-tenant rate limiting** — token bucket, 429 + Retry-After | 🔧 📐 [ADR 0036](../../adr/0036-per-tenant-rate-limiting.md) |
| Observability, IaC (Terraform), migrations (Alembic), PII scrubbing, backup/DR | 📄 see [PRODUCTION-READINESS.md](../../PRODUCTION-READINESS.md) |

---

## 💡 Discoveries — what the measurements taught (the part you can't read in a tutorial)

1. **A gain measured against one *sample* is not a gain.** litm passed a judge-averaged A/B (+0.076) then **reversed** (−0.056) under fresh *generation* — `--runs` averages the judge, not the generation. → [MISSION-053](../missions/MISSION-053/mission.md).
2. **The bridge hop is a retrieval-*coverage* failure, not a reasoning one** — invisible at small corpus / high k, where a single retrieval co-retrieves both hops. → [MISSION-055](../missions/MISSION-055/mission.md).
3. **Decomposition ≠ cyclic controller** — two *distinct* failure classes, proven (decompose ties fixed exactly on bridge hops). → MISSION-049/050/055.
4. **Metric traps** — recall@exact-id nearly produced a false negative; a small controlled corpus hid the bridge failure entirely. → MISSION-050/055.
5. **OpenAI/Azure structured output rejects open `dict` properties** (`additionalProperties` must be false) → use typed fields. (The controller had never worked live — caught by the probe.) → MISSION-055.
6. **Fake-tested ≠ live-validated** — a component green in unit tests was broken in production until the live probe ran it.
7. **The reliability-primitive template** — port → fake → local-first → process singleton → `/ask` guard → ADR → deferred distributed backend. Reproduced 3× (budget #146, breaker #145, rate-limit #144).
8. **Product-boundary invariants** — *knowledge platform*: "no claim without a citation"; an *action platform* would need "no irreversible action without approval + audit" — a different product, not an epic.
9. **Capability-before-measurement** — a *justified* inversion of measure-first (make the controller bridge-capable before measuring whether it earns its keep). → MISSION-054.
10. **Doc-vs-reality drift** — "not clean" was the source-tree doc lagging reality, not messy code.

## 🧭 The method (the meta over everything)

- **Measure-first** — gate every "improvement" against a baseline; keep only what wins (**6 rejected / 2 promoted**). The *rejections* are as considered as the features.
- **ADR-before-code** — 36 decisions recorded; the trigger that would un-defer each deferral is written down.
- **Local-first + default-off** — ports/fakes, opt-in knobs until a measured reason to turn them on.

See [synthesis.md](../synthesis.md) for the one-page thesis, and the [ADR index](../../adr/README.md) for all 36 decisions.
