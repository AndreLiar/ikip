# 0026. Agentic RAG: a deliberate, triggered evolution of the flow-RAG (not a rewrite, not the default)

- **Status:** Accepted (direction) — implementation is **Post-MVP Epic 10**, enabled per query class when it wins the gate.
- **Date:** 2026-11-14
- **Deciders:** Architect, PM
- **Related:** [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md) · [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (LangGraph behind ports) · [ADR 0022](./0022-grounded-answer-langgraph-gpt5-mini.md) (grounded-answer flow) · Epic 3 (RAG) · Epic 5 (eval/tracing) · Epic 6 (isolation/injection) · [Epic 10](../prd/epic-10-agentic-rag.md)

## Context
IKIP's request-time RAG is already a **graph** (LangGraph): query analysis → equipment-ID → hybrid retrieval → rerank → sufficiency → cited answer / abstain. But the control flow is **fixed and deterministic** — the engineer wired the steps; the LLM does not decide *what* to retrieve, *whether to retrieve again*, or *how many steps* to take. Call it **flow-RAG**.

As we onboard **many corpora/tenants across domains** (aerospace, energy, law, insurance, banking-finance…), a class of questions appears that flow-RAG structurally cannot answer well:
- **multi-hop / compositional** ("compare the maintenance interval of pump X vs the energy-corpus equivalent"),
- **cross-corpus / cross-domain** (insurance + law),
- **computational / structured lookup** (unit conversions, torque, specs from a table/DB),
- **ambiguous** (needs disambiguation or a clarifying question before retrieving),
- **weak-first-retrieval** (a reformulation would succeed where the fixed flow abstains).

**Agentic RAG** — the LLM as an agent that decides its own tool/retrieval steps in a plan → act → observe loop — raises the ceiling on question complexity. But it costs more (LLM calls, latency), is less deterministic, has more failure modes (loops, wrong tool), makes citations/grounding harder to keep tight, and widens the attack surface.

## Decision
**Evolve to agentic RAG as a deliberate, *triggered*, *incremental* capability — behind the same ports, alongside (not replacing) the fixed flow — and enable it per query class only when it beats the fixed flow on a quality+cost gate.**

1. **Keep the fixed flow as the default.** ~80% of technician questions (one manual, one answer) are better served by the fast/cheap/predictable flow. Agentic serves the **hard tail**.
2. **Reuse, don't rebuild.** LangGraph already supports cyclic/ReAct graphs (ADR 0021); ports, OTel→Langfuse tracing, the eval harness, injection defense, abstention, citations and tenant isolation already exist. The gap is a **Tool port + registry**, a **cyclic controller**, **multi-corpus routing**, **trajectory evals**, and **loop/budget guardrails** — not a new stack.
3. **Incremental path, each step independently evaluated** (Epic 10): (a) tool-calling retrieval → (b) iterative retrieval / reformulation → (c) **multi-corpus routing** → (d) planning / decomposition → (e) self-critique / grounding verification.
4. **The first step is (c) multi-corpus routing** — the multi-domain corpora make cross-domain questions the earliest, highest-value agentic win.
5. **Hard invariants preserved at every step:** citations/provenance threaded through every tool call (FR16); **tenant-scoped tools** (a tool never crosses a tenant, NFR10); abstention + injection defense wrap tool outputs; a **per-query budget** (max steps / tokens / wall-time) bounds every run.

## Triggers (when to actually build it)
Build a step when the data says the fixed flow's ceiling is reached, not before:
- the eval harness shows a **recurring failure class** (multi-hop / cross-domain / weak-first-retrieval) the fixed flow can't fix;
- **≥2 domains/tenants** are live (already true) so cross-corpus questions are real;
- the step's **quality gain on its gold set** exceeds its **cost/latency penalty** on the regression gate.

## Consequences
**Positive**
- Answers the hard tail (multi-hop, cross-domain, computational, ambiguous) that flow-RAG abstains on.
- Natural fit for the growing multi-tenant/multi-domain corpus — cross-corpus routing is the first win.
- Reuses the existing investment (LangGraph, ports, tracing, evals, security) — bounded new surface.

**Negative / watch**
- More LLM calls → higher cost + latency; mitigated by budgets, a cheap router/planner model, sub-result caching, and enabling agentic only per winning query class.
- Less determinism + more failure modes (loops, wrong tool) → mitigated by step/loop guards, trajectory evals, and a per-tenant kill-switch.
- Citations/grounding are harder across tool calls → provenance threading is a required-gate invariant, not optional.
- Wider attack surface (tool use + injection) → injection defense on tool inputs/outputs, tenant-scoped tools, isolation tests extended.

## Alternatives considered
- **Stay flow-RAG only** — simplest/cheapest; rejected because it structurally abstains on the hard tail that multi-domain corpora create.
- **Go fully agentic as the default** — rejected: worse (cost/latency/unpredictability) for the 80% simple-lookup majority; agentic must be the exception, gated.
- **A different agent framework (e.g., a bespoke ReAct loop or another lib)** — rejected: LangGraph already provides cyclic graphs + checkpointing behind our ports (ADR 0021); no reason to add a stack.
