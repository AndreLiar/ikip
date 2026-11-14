# Epic 10 — Agentic RAG  (Post-MVP)

_Sharded from `../prd.md`. Part of the [epic index](./index.md). **Post-MVP** — sequenced after Epics 1–6; builds on the deterministic flow-RAG of Epic 3._

**Goal:** Evolve the fixed LangGraph flow (query → equipment-ID → hybrid retrieval → rerank → sufficiency → cited answer / abstain) into an **agentic controller** that decides its own retrieval/tool steps in a plan → act → observe loop — to handle the **hard tail** of questions the fixed flow cannot: multi-hop, cross-corpus/cross-domain, computational and ambiguous. This is done **without losing** citations (FR16), grounding, abstention, tenant isolation (NFR10) or cost control.

**Addresses:** the cross-domain questions created by multiple corpora/tenants (aerospace, energy, law, insurance, banking-finance…). Builds on **Epic 3** (retrieval + grounded answer), **Epic 5** (eval harness + tracing), **Epic 6** (tenant isolation + injection defense), and [ADR 0021](../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (LangGraph behind ports). Decision + triggers: [ADR 0026](../adr/0026-agentic-rag-evolution.md).

**Scope discipline:** agentic is for the hard tail, **not the default** — the fixed flow stays the fast/cheap/predictable path for simple lookups. Every story is independently evaluable and ships behind a flag so the agent can be enabled per tenant/query class.

---

## Story 10.1 Tool Abstraction & Registry
As an engineer, I want retrieval and non-retrieval capabilities exposed as typed **tools** behind a port, so that an agent can call them safely and I can add/remove tools without touching the orchestration.
**Acceptance Criteria:**
1. A `Tool` port (name, typed args/returns, description) + a registry; each **corpus/tenant is a retrieval tool**, plus non-retrieval tools (structured-DB lookup, unit/torque calculator).
2. Tool access is **tenant-scoped** — a tool invocation can never read another tenant's data (isolation tests extend Epic 6).
3. Every tool result carries **provenance** (document/version/page/section) so citations survive tool use (FR16).
4. Tools are unit-testable with fakes; the registry is config-driven (no code change to wire a new corpus).

## Story 10.2 Agentic Controller (cyclic plan–act–observe)
As a technician, I want the assistant to take **multiple reasoning/tool steps** when needed, so that hard questions are answered instead of abstained — while staying bounded and auditable.
**Acceptance Criteria:**
1. The LangGraph graph becomes **cyclic** (ReAct-style): a controller node calls tools, observes results, and loops or stops.
2. **Step/budget guardrails**: `max_steps`, per-query token/cost budget, and loop/no-progress detection terminate the agent deterministically.
3. **Checkpointing** persists agent state so a long/interrupted run is resumable (LangGraph checkpointer).
4. The fixed flow remains available; a router/flag selects agent vs flow per query class or tenant.

## Story 10.3 Iterative Retrieval & Query Reformulation
As a user, I want the assistant to **retry with a better query** when the first retrieval is weak, so that recall improves on hard questions before it gives up.
**Acceptance Criteria:**
1. On insufficient evidence, the agent reformulates (query-rewrite / step-back / HyDE) and re-retrieves, up to the step budget.
2. Reformulation is logged; the final answer still resolves citations to the chunks actually used.
3. Abstention still triggers when no reformulation clears the grounding threshold (no hallucinated fill-in).
4. An eval set of "weak-first-retrieval" questions shows measurable recall gain vs the fixed flow.

## Story 10.4 Multi-Corpus Routing & Cross-Domain Synthesis
As a user, I want a question answered across the **right corpora** (and several when needed), so that cross-domain questions (e.g., insurance + law) are handled with per-source citations.
**Acceptance Criteria:**
1. A router selects the relevant corpus/tenant tool(s) from the question; it may fan out to several and merge.
2. Cross-corpus results keep **per-source provenance**; the synthesized answer cites each source correctly.
3. Tenant isolation holds: routing only ever reaches tools the caller is authorized for.
4. Eval includes single-corpus (routes to one) and cross-domain (combines) cases with routing-accuracy and citation-integrity metrics.

## Story 10.5 Query Planning & Decomposition
As a user, I want compositional/**multi-hop** questions decomposed into sub-questions and synthesized, so that "compare X vs Y" style questions are answerable.
**Acceptance Criteria:**
1. A planning step decomposes a question into an ordered/parallel set of sub-queries with explicit dependencies.
2. Sub-answers are retrieved + grounded independently, then synthesized with citations preserved end-to-end.
3. The planner degrades gracefully to single-step retrieval for simple questions (no over-planning).
4. A multi-hop gold set measures end-to-end correctness + citation integrity.

## Story 10.6 Self-Critique & Grounding Verification
As a reviewer, I want the agent to **verify its draft against the retrieved evidence** before answering, so that ungrounded claims are caught and removed.
**Acceptance Criteria:**
1. A critique step checks each claim in the draft against cited chunks; unsupported claims are dropped or trigger another retrieval/abstention.
2. The verification loop is bounded by the step/cost budget.
3. Groundedness/faithfulness scores (Epic 5 metrics) improve vs no-critique on an adversarial set, with no latency regression beyond the agreed budget.
4. Safety abstention + injection defense (Epics 5/6) wrap tool outputs and the final answer.

## Story 10.7 Trajectory Evaluation, Cost/Latency Control & Agent Safety
As an operator, I want to **evaluate and bound the agent's trajectory**, so that we only enable agentic behavior where it demonstrably helps and never at runaway cost or risk.
**Acceptance Criteria:**
1. **Trajectory evals** extend the Epic 5 harness: tool-choice correctness, step correctness, steps-per-query, and cost/latency per query — traced in Langfuse (per-step spans).
2. Per-query **budget caps** (steps, tokens, wall-time) and a cheaper model for routing/planning keep p95 cost/latency within target; sub-result caching reuses work.
3. **Agent guardrails** required-gate in CI: step/loop bounds, tenant-scoped tools, injection defense on tool inputs/outputs, and a kill-switch flag per tenant.
4. A regression gate compares agent vs fixed-flow on quality **and** cost; agentic is enabled per query class only when it wins on the gate.
