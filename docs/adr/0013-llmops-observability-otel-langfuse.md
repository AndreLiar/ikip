# 0013. LLMOps observability: OpenTelemetry + Langfuse (Cloud EU for dev; self-host exit path)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR26, FR30, FR31, FR32 · NFR2, NFR16 · Epic 5 (Stories 5.4, 5.5), Story 4.6 · builds on [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0012](./0012-local-first-dev-cloud-models-only.md); relates to [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md)

## Context
The LLMOps layer needs end-to-end tracing (query → chunks → model → answer), token/cost tracking, prompt/model-config versioning, and evaluation dataset/score tracking (FR30–FR32, Epic 5). The tech stack originally said "OpenTelemetry + (optional) LangSmith" and never evaluated **Langfuse**, an open-source LLM engineering platform that covers most of these concerns. Raw OpenTelemetry + Grafana is vendor-neutral and great for infra, but is **not LLM-aware** (no prompt, completion, token-cost, or eval-dataset concepts). The project is local-first ([ADR 0012](./0012-local-first-dev-cloud-models-only.md)) and cost-conscious.

## Decision
Use **OpenTelemetry + Langfuse together** — they are complementary, not redundant:

- **OpenTelemetry** is the single instrumentation standard (all spans/metrics; no lock-in; swappable backends).
- **Langfuse (self-hosted, open source)** is the **LLM-native backend** that consumes OTel and integrates natively with LangChain/LangGraph. It provides RAG-step traces with prompt/response inspection, **token & cost per trace** (FR31), **prompt management/versioning** (FR32), and **eval dataset/score** tracking (Epic 5).

Routing: **instrument once with the OTel SDK (an in-app library — nothing to host) → LLM/RAG spans to Langfuse; infra spans/metrics to Azure Monitor (or optional local Prometheus/Grafana).** No local observability container is required in a managed-dev setup (OTel exports directly to Langfuse Cloud / Azure Monitor); Prometheus + Grafana are optional, only for local infra dashboards. Evaluation *logic* stays in the own pytest + gold-dataset harness (Epic 5); Langfuse stores datasets/scores and traces. Access remains behind the `Telemetry` port where practical ([ADR 0003](./0003-local-first-ports-and-adapters.md)).

## Update (2026-11-06): Langfuse Cloud Hobby (free) is the default for dev/MVP
Rather than self-hosting, dev/MVP uses **Langfuse Cloud — Hobby tier** (free: all features with limits, **50k units/month**, **30-day** data access, 2 users, community support). This removes the self-hosting ops burden (the datastore noted below) while keeping $0 cost, and — because Langfuse is open source — the **self-hosting exit path remains** (less lock-in than a closed SaaS like LangSmith). Use the **EU region** (`https://cloud.langfuse.com` EU). Credentials: `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` via the secrets provider.

> ⚠️ **Data-governance caveat:** Langfuse traces contain prompts **and retrieved document content** (potentially sensitive). Sending these to a SaaS is acceptable for the **licensed sample/MVP corpus**, but **real customer data should use self-hosted Langfuse (or an EU region + DPA)** — this ties to Epic 6 and is a revisit trigger. Limits (50k units/mo, 30-day retention) also mean production-scale tracing or long eval history will need the paid tier or self-hosting.

**Self-hosting remains the option** for data governance and scale; the choice is a config switch (same OTel instrumentation + SDK).

## Update (2026-11-07): Grafana Cloud (free) for infra observability + k6
The **infra** observability layer (metrics, logs, traces, dashboards, alerts) uses **Grafana Cloud — Free tier** ($0, all services with usage limits, **14-day** retention, community support), replacing the previously "optional local Prometheus/Grafana". It ingests our existing OpenTelemetry via **OTLP** → no code change, just an endpoint + token (`GRAFANA_OTLP_ENDPOINT`, `GRAFANA_OTLP_TOKEN` via the secrets provider). **Azure Monitor becomes optional/prod** (deferred). This continues the managed-free-tier trajectory (Neon/R2/Redis Cloud/Langfuse).

**Clear division of layers (not redundant):**
- **Langfuse** = the **LLM/RAG** layer (prompts, token cost, eval datasets, RAG traces).
- **Grafana Cloud** = the **infra** layer (HTTP/DB latency, error rates, system metrics, logs, traces) + **dashboards & alerts** (Story 5.6) + **k6 performance tests** (NFR1 p95 retrieval < 1.5 s, NFR2 TTFT < 5 s — k6 was already the chosen perf tool).

> ⚠️ **Caveats:** 14-day retention is fine for **operational** dashboards because the durable audit trail (`query_trace`, `audit_event`) lives in **Postgres/Neon**, not Grafana. Free-tier **usage limits** (metric series, log/trace volume) are ample at MVP scale — verify current limits. Same data-governance note as Langfuse applies to anything sensitive in logs/traces (scrub PII — Presidio; Epic 6).

**Timing:** this is a decision capture. The OTel→Grafana OTLP wiring and k6 setup are implemented in **Epic 5** (observability), not now. Everything stays behind the `Telemetry` port, so Grafana↔Azure Monitor is a config swap.

## Update (2026-11-11): re-evaluated LangSmith before wiring; keep Langfuse
Before building the Epic 5 instrumentation, we explicitly re-opened **Langfuse vs LangSmith** (nothing is wired yet — only config keys + a doctor health check exist, so switching would be cheap). LangSmith's real edge is **zero-config, best-in-class LangGraph tracing** (we use LangGraph for the request-time graph, Story 3.5) plus a very polished eval/annotation UX. We still keep **Langfuse**, for reasons specific to this project — not merely "self-hosting under infra constraints":

1. **Framework boundary ([ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md)).** We deliberately keep LangChain/LangGraph *behind our ports* and the domain framework-agnostic. LangSmith is the **native observability of the LangChain ecosystem** — adopting it leans back into the framework we chose to hold at arm's length. Langfuse is **OTel-based / framework-agnostic**, consistent with that stance. (We don't lose graph traces: Langfuse ships a LangChain/LangGraph callback handler.)
2. **EU data residency + governance (NFR16, recurring).** Traces carry user **queries + retrieved document content** (potentially sensitive industrial data / PII). Langfuse offers an **EU cloud region and a self-host exit path** → data stays in our control. LangSmith is US-default (EU region is newer) and proprietary.
3. **Open-source = thesis-inspectable + no lock-in.** Langfuse can be read, forked and run locally — a stronger learning artifact and a cleaner "sovereign observability" narrative for the dissertation.

**We would pick LangSmith instead if** developer velocity (zero-config LangGraph tracing + richest eval UX) were the top priority *and* residency/lock-in were non-issues — e.g. a pure LangChain-stack product optimizing DX. That is not this project's posture. This re-evaluation is a revisit trigger result, not a reversal; the `Telemetry` port keeps the backend swappable if that calculus changes.

## Update (2026-11-11) — Prompt management: git-source-of-truth + Langfuse sync (Story 5.5)

AC1 of Story 5.5 allows prompt management "via **Langfuse prompt management** and/or repo artifacts". We adopt a **hybrid, with git as the source of truth**:

- **Versioned repo artifacts** (`packages/common/src/ikip_common/llm/prompt_config/<version>.json` + `active.json`) are authoritative. This is what makes the governance ACs deterministic: a prompt/model change is a **PR diff** → it triggers the regression suite (`config-regression.yml`, AC2); **promotion** flips `active` only when retrieval + groundedness + safety gates pass (`eval config promote`, AC3); **rollback** is a pointer flip to an immutable prior version (AC4). The running answer flow reads the active artifact (`active_prompt_config()`), with a built-in fallback so config IO can never break generation.
- **Langfuse is the runtime/UI mirror**, not the source of truth: on promote, each prompt is synced to Langfuse prompt management under label `production` (behind a `PromptPublisher` port; no-op when the SDK/creds are absent, so CI stays network-free). This gives the LLM-native UI, non-engineer visibility, and prompt↔trace correlation with the Story 5.4 `trace_id`.

**Why not Langfuse as source of truth:** a prompt edited in the Langfuse UI produces no PR and no CI run, so AC2/AC3 (diff-triggered regression + gated promotion) would lose their deterministic, reviewable gate and CI would need live Langfuse creds. Git-source keeps change control in code review where the eval gates live; Langfuse remains swappable behind the port.

## Consequences
**Positive**
- One instrumentation (OTel), two fit-for-purpose backends; no lock-in.
- Langfuse covers prompt versioning, token/cost, eval-dataset tracking and an LLM-native trace UI the plan would otherwise hand-roll.
- **Open source + self-hosted = $0**, runs in the local Docker stack — fits local-first.
- Native LangChain/LangGraph integration → minimal glue.

**Negative / risks**
- Self-hosting adds a service with its own datastore (Postgres; newer versions add components such as Clickhouse/Redis/blob — verify current requirements); extra local footprint on a 16 GB laptop.
- Two observability backends to understand (LLM vs infra) — mitigated by the clear routing split.
- Prod self-hosting on Azure adds a container + datastore to operate (or use Langfuse Cloud free tier).

**Neutral**
- Infra metrics go to Azure Monitor (Prometheus/Grafana optional, local only) — unchanged.

## Alternatives Considered
- **OTel + Grafana only (no LLM-native layer):** no extra service, but no prompt management, no per-trace token cost, no eval-dataset UI — all hand-rolled. Rejected; weak LLMOps ergonomics.
- **LangSmith (SaaS):** best-in-class, **zero-config LangGraph tracing** (we use LangGraph) and a polished eval/annotation UX — the strongest DX option. Rejected for IKIP because (a) it re-couples observability to the LangChain ecosystem we deliberately hold behind ports ([ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md)), (b) US-default hosting / proprietary vs our EU-residency + data-governance posture (NFR16) for traces that carry query + document content, and (c) closed-source vs Langfuse's inspectable/forkable/self-hostable model (thesis value, no lock-in). It remains the right call for a pure-LangChain product optimizing dev velocity without residency/lock-in concerns. Re-evaluated 2026-11-11 (see Update above); the `Telemetry` port keeps it swappable.
- **Langfuse only (drop OTel):** loses the vendor-neutral instrumentation standard and unified infra tracing. Rejected — keep OTel as the contract.

## Revisit When
- Self-hosting Langfuse becomes operationally heavy vs. value → use Langfuse Cloud (free/paid) or fall back to OTel-only.
- A different LLMOps platform offers a decisive advantage for IKIP's needs.
- Scale requires separating the Langfuse datastore from the app database.

> Consolidated stack view: [`../architecture/llmops-stack.md`](../architecture/llmops-stack.md).
