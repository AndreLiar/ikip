# IKIP — LLMOps stack

_Consolidated view of the LLMOps stack (Epic 5 + related). Part of the [architecture index](./index.md). Decisions: [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md) (OTel + Langfuse), plus [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md), [ADR 0007](../adr/0007-pluggable-llm-client-azure-openai.md), [ADR 0009](../adr/0009-caching-strategy.md), [ADR 0010](../adr/0010-foundry-model-platform-no-dedicated-ai-gateway.md)._

## Philosophy
Build the LLMOps capability from **open, self-hostable, local-first** pieces — reuse the general observability standard (OpenTelemetry) and add an LLM-native layer (Langfuse) on top, rather than buying a closed SaaS. You *construct* the LLMOps (a stated learning goal) while using purpose-built tools where they genuinely help.

## The stack, by concern

| LLMOps concern | Tool | Local (dev) | Prod (Azure) | Ref |
|---|---|---|---|---|
| Model inference (LLM + embeddings) | Azure OpenAI via `LLMClient` port | API call | Azure OpenAI in **Foundry** | [ADR 0007](../adr/0007-pluggable-llm-client-azure-openai.md), [0010](../adr/0010-foundry-model-platform-no-dedicated-ai-gateway.md) |
| AI workflow orchestration | **LangGraph + LangChain** | local | local | [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md) |
| **Instrumentation standard** | **OpenTelemetry** | OTel SDK | OTel SDK | FR30, Story 5.4 |
| **LLM-native observability** (traces of RAG steps, prompt I/O, token/cost) | **Langfuse** (Cloud Hobby free for dev/MVP; self-host option) | Cloud Hobby (EU) | Cloud / self-host | [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md) |
| Prompt / model-config versioning | **Langfuse prompt management** + git artifacts | Langfuse + repo | idem | FR32, Story 5.5 |
| Evaluation logic (Recall@K, citation, groundedness) | **pytest + gold datasets** (own harness); datasets tracked in Langfuse | local | CI | Epic 5, Stories 5.1–5.2 |
| Safety / guardrails (default, $0) | **own guardrails** — adversarial test suite, untrusted-content handling, own groundedness eval | local | CI | Story 5.2, 5.3, 6.3 |
| Safety detectors (optional, paid) | **Foundry Content Safety** (Prompt Shields, groundedness) — behind a guardrail interface; free tier first | API | API | optional complement |
| Infra metrics / latency | OTel SDK (in-app) → backend | **Azure Monitor** or **Prometheus/Grafana** (optional, local) | **Azure Monitor / App Insights** | FR31, Story 5.6 |
| `query_trace` (user→chunks→model, latency, cost) | PostgreSQL + exported to Langfuse | local | local | FR30, Story 5.4 |
| Regression gates (eval + safety) | **GitHub Actions** | CI | CI | Story 5.5, 6.7; NFR14 |
| Caching (cost/latency) | Redis + Postgres (`Cache` port) | local | Redis/Azure Cache | [ADR 0009](../adr/0009-caching-strategy.md) |
| Feedback / failure analysis | app feedback (`message.rating/flagged`) → Langfuse | local | local | FR26, Story 4.6 |

## Why combine OpenTelemetry **and** Langfuse (not redundant)

They operate at different layers:

- **OpenTelemetry = the instrumentation contract.** Vendor-neutral spans/metrics for *everything* (HTTP, DB, queue, and the RAG workflow). Instrument once; no lock-in; swappable backends. But raw OTel + Grafana is **not** LLM-aware — it has no concept of a prompt, a completion, token cost, or an eval dataset.
- **Langfuse = an LLM-native backend that consumes OTel** (and integrates natively with LangChain/LangGraph). It adds exactly what OTel lacks for LLMOps: nested **RAG-step traces** with prompt/response inspection, **token & cost per trace**, **prompt management/versioning**, and **eval datasets/scores** — in a UI built for this.

So the flow is: **instrument with OTel → LLM/RAG spans go to Langfuse (LLM layer); infra spans/metrics go to Azure Monitor (or optional Prometheus/Grafana) (infra layer).** One instrumentation, two fit-for-purpose backends.

> **OTel is a library, not a service.** The OpenTelemetry SDK runs **inside the app** (FastAPI) and exports directly to backends — there is **nothing to host** for OTel itself (no Collector required at MVP). In a fully-managed dev setup, the app exports LLM traces to **Langfuse Cloud** and (optionally) infra metrics to **Azure Monitor**, so **no local observability container is required**. Prometheus + Grafana are an **optional** local choice only if you want infra dashboards on the laptop.

```
            OpenTelemetry (instrument once)
            ├── LLM / RAG spans ─────────▶ Langfuse  (prompts, token cost, eval datasets, RAG trace UI)
            └── infra spans / metrics ───▶ Prometheus/Grafana (local) → Azure Monitor (prod)
```

## Why Langfuse (answering "why wasn't it used?")

Honestly: it was **overlooked** — the tech-stack had defaulted to "OTel + (optional) LangSmith" and never evaluated Langfuse. On the merits it is the **best fit** for IKIP:

- **Open source + self-hostable** → runs in Docker, **$0**, fits local-first ([ADR 0012](../adr/0012-local-first-dev-cloud-models-only.md)); no per-token SaaS fee, no vendor lock-in.
- **Native LangChain/LangGraph + OpenTelemetry** integration → minimal glue.
- Covers tracing, **prompt management/versioning** (FR32), **eval datasets/scores** (Epic 5), **cost tracking** (FR31) — several things the plan would otherwise hand-roll.

**The one real trade-off:** self-hosting adds a service with its own datastore (Postgres; newer versions add components like Clickhouse/Redis/blob — verify current self-host requirements). Mitigation: run it in the local Docker Compose, or spin it up only when inspecting traces; it is not on the request hot path.

## Langfuse vs LangSmith (the alternative)
- **Langfuse (chosen):** open source, self-hostable, free, OTel + LangGraph native. Best for a cost-conscious, local-first, no-lock-in project.
- **LangSmith:** LangChain's own SaaS, excellent LangGraph integration, zero-ops — but paid beyond a free tier and hosted (lock-in). Reasonable if you prefer zero self-hosting; rejected here on cost/lock-in.

## Presidio ≠ Content Safety (two different jobs — common confusion)

They are **not** equivalent and do not overlap: Presidio does PII, Content Safety does harm/injection/groundedness.

| | **Presidio** | **Azure AI Content Safety** |
|---|---|---|
| **Job** | PII detection + anonymization | harmful-content moderation + Prompt Shields + groundedness |
| **Examples** | names, emails, SSN, cards, phones → mask/redact | hate/violence/sexual; jailbreak/injection; "is the answer grounded?" |
| **License / cost** | OSS (MIT), free, self-hosted | paid (per 1,000 records, small free tier) |
| **Where it runs** | locally (spaCy/transformers + regex) | Azure managed API |

- The real **paid equivalent of Presidio** is **Azure AI Language – PII detection** (not Content Safety).
- IKIP uses **Presidio** for the PII requirement (NFR16, Story 6.4) via the `PiiScrubber` port — free, local-first. Content Safety stays an optional harm/injection complement with no Presidio equivalent.

## Cost note on safety (Content Safety is paid)
Unlike Entra ID, **Azure AI Content Safety is a paid service** (per 1,000 records; a limited free tier exists). It is therefore **optional**, not MVP-required: IKIP's safety requirements (FR17/18, NFR18) are already met by **own guardrails** — the adversarial/prompt-injection test suite (Story 6.3), untrusted-retrieved-content handling (coding standard), the own groundedness eval (Story 5.2) and the safety-abstention set (Story 5.3). Default MVP = $0 (own guardrails); Content Safety is a managed complement behind a guardrail interface, free tier first, enabled only if stronger managed detection is wanted.

## Division of labour (one line)
**Foundry** = models (+ *optional* Content Safety detectors) · **own guardrails** = default safety (injection/groundedness/abstention) · **LangGraph/LangChain** = orchestration · **pytest + gold datasets** = eval logic & CI gates · **OpenTelemetry** = instrumentation · **Langfuse** = LLM-native tracing/prompts/eval/cost · **Prometheus/Grafana → Azure Monitor** = infra metrics · **Redis/Postgres** = caching.

## Cost
Langfuse = **$0** on **Cloud Hobby** (free: 50k units/mo, 30-day retention, EU region) for dev/MVP, or self-hosted ($0, open source) — see [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md). OTel/Prometheus/Grafana = $0 local. You pay only for **LLM tokens** + (optionally) **Foundry Content Safety** calls. Governance caveat: Langfuse traces carry prompts + retrieved content → use self-hosting (or EU + DPA) for real customer data (Epic 6).
