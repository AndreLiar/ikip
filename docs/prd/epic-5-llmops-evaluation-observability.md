# Epic 5 — LLMOps, Evaluation & Observability

_Sharded from `../prd.md`. Part of the [epic index](./index.md)._

**Goal:** Make retrieval and generation observable, measurable and safe to update: comprehensive gold datasets, an evaluation harness (retrieval, citation, groundedness, safety), end-to-end tracing, prompt/model-config versioning with regression gates, and dashboards for latency/cost/health with alerts.

**Related requirements:** FR29–FR32 · NFR1, NFR2, NFR6, NFR7, NFR8, NFR9 · depends on Epics 2–4

> Recommended evaluation/benchmark datasets (DocVQA, BEIR, RAGBench, IBM RAGWorkbench, SEC EDGAR) are listed in `../data-sources.md`.

---

## Story 5.1 Gold Evaluation Datasets
As an evaluator, I want dedicated gold datasets for key failure modes, so that evaluation is representative.
**Acceptance Criteria:**
1. Datasets exist for: exact equipment identifiers, outdated manuals, conflicting sources, unanswerable questions, tables, scanned PDFs, malicious documents.
2. Each case specifies question, relevant evidence and expected behavior (incl. abstention).
3. Datasets are versioned and reviewable.
4. A documented command runs evaluation against any dataset.

## Story 5.2 Retrieval, Citation & Groundedness Evaluation Harness
As an evaluator, I want automated quality metrics, so that improvements are measured, not demoed.
**Acceptance Criteria:**
1. Recall@K and ranking metrics computed on the retrieval datasets.
2. Citation-correctness (resolution to correct document/location) measured.
3. Groundedness/faithfulness measured against evidence.
4. Results stored and comparable across runs (regression baseline).

## Story 5.3 Safety-Abstention Evaluation
As a safety owner, I want critical safety-abstention tests, so that the system refuses unsafe/unsupported guidance.
**Acceptance Criteria:**
1. A predefined critical safety test set runs in CI.
2. 100% pass required; failures block release.
3. Reports show which cases abstained vs. answered.
4. Malicious-document cases confirm safe handling (ties to Epic 6).

## Story 5.4 End-to-End Tracing
As an engineer, I want tracing from query → chunks → model → answer, so that I can debug and audit behavior.
**Acceptance Criteria:**
1. `query_trace` records user, retrieval IDs, model, latency and cost.
2. Traces are correlatable end-to-end (OpenTelemetry instrumentation → Langfuse for LLM/RAG traces; see [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)).
3. Traces are queryable for a given query/conversation.
4. Sensitive content handling in traces respects security policy.

## Story 5.5 Prompt/Model Config Versioning & Regression Gates
As an AI engineer, I want versioned prompts/model configs gated by regression tests, so that changes are controlled.
**Acceptance Criteria:**
1. Prompt and model configurations are versioned artifacts (prompts managed via **Langfuse prompt management** and/or repo artifacts — [ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)).
2. Changing a config triggers the evaluation regression suite.
3. Promotion requires passing retrieval, groundedness and safety gates.
4. Rollback to a prior config version is supported.

## Story 5.6 Operations & Evaluation Dashboards with Alerts
As an operator, I want dashboards and alerts for latency, cost, pipeline health and quality, so that I can run the platform.
**Acceptance Criteria:**
1. Dashboards show p95 latencies, error rates, pipeline health and token cost.
2. Evaluation dashboard shows Recall@K, citation correctness, groundedness and regressions.
3. Alerts fire on defined thresholds (latency, errors, cost, quality regressions).
4. Observability backends via the `Telemetry` port: **Langfuse** (LLM/RAG traces + eval), **Azure Monitor/App Insights** (infra), with **Prometheus/Grafana optional** (local infra dashboards) — OTel is in-app instrumentation, nothing to host ([ADR 0013](../adr/0013-llmops-observability-otel-langfuse.md)).
