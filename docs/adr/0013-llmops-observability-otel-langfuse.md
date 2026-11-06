# 0013. LLMOps observability: OpenTelemetry + Langfuse (self-hosted)

- **Status:** Accepted
- **Date:** 2026-11-06
- **Deciders:** Architect, PM
- **Related:** FR26, FR30, FR31, FR32 · NFR2 · Epic 5 (Stories 5.4, 5.5), Story 4.6 · builds on [ADR 0003](./0003-local-first-ports-and-adapters.md), [ADR 0012](./0012-local-first-dev-cloud-models-only.md); relates to [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md)

## Context
The LLMOps layer needs end-to-end tracing (query → chunks → model → answer), token/cost tracking, prompt/model-config versioning, and evaluation dataset/score tracking (FR30–FR32, Epic 5). The tech stack originally said "OpenTelemetry + (optional) LangSmith" and never evaluated **Langfuse**, an open-source LLM engineering platform that covers most of these concerns. Raw OpenTelemetry + Grafana is vendor-neutral and great for infra, but is **not LLM-aware** (no prompt, completion, token-cost, or eval-dataset concepts). The project is local-first ([ADR 0012](./0012-local-first-dev-cloud-models-only.md)) and cost-conscious.

## Decision
Use **OpenTelemetry + Langfuse together** — they are complementary, not redundant:

- **OpenTelemetry** is the single instrumentation standard (all spans/metrics; no lock-in; swappable backends).
- **Langfuse (self-hosted, open source)** is the **LLM-native backend** that consumes OTel and integrates natively with LangChain/LangGraph. It provides RAG-step traces with prompt/response inspection, **token & cost per trace** (FR31), **prompt management/versioning** (FR32), and **eval dataset/score** tracking (Epic 5).

Routing: **instrument once with OTel → LLM/RAG spans to Langfuse; infra spans/metrics to Prometheus/Grafana (local) → Azure Monitor (prod).** Evaluation *logic* stays in the own pytest + gold-dataset harness (Epic 5); Langfuse stores datasets/scores and traces. Access remains behind the `Telemetry` port where practical ([ADR 0003](./0003-local-first-ports-and-adapters.md)).

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
- Infra metrics continue on Prometheus/Grafana → Azure Monitor unchanged.

## Alternatives Considered
- **OTel + Grafana only (no LLM-native layer):** no extra service, but no prompt management, no per-trace token cost, no eval-dataset UI — all hand-rolled. Rejected; weak LLMOps ergonomics.
- **LangSmith (SaaS):** excellent LangGraph integration, zero-ops, but paid beyond a free tier and hosted (lock-in). Rejected on cost/lock-in vs self-hosted Langfuse; remains a fallback if self-hosting is unwanted.
- **Langfuse only (drop OTel):** loses the vendor-neutral instrumentation standard and unified infra tracing. Rejected — keep OTel as the contract.

## Revisit When
- Self-hosting Langfuse becomes operationally heavy vs. value → use Langfuse Cloud (free/paid) or fall back to OTel-only.
- A different LLMOps platform offers a decisive advantage for IKIP's needs.
- Scale requires separating the Langfuse datastore from the app database.

> Consolidated stack view: [`../architecture/llmops-stack.md`](../architecture/llmops-stack.md).
