# 0033. Agentic foundation (Tool port + cyclic controller) + the first measured slice: query decomposition

- **Status:** Accepted — foundation (10.1 Tool port/registry, 10.2 controller/guardrails) + the
  decomposition slice (10.5) implemented and gated (#130/#131), wired into `/ask` behind
  `AGENT_DECOMPOSE` (#132). **One deviation from this plan — see [Implementation notes](#implementation-notes--one-deviation-from-the-plan).** Measured in [MISSION-050](../learning/missions/MISSION-050/mission.md).
- **Date:** 2026-11-17
- **Deciders:** Architect, PM
- **Related:** [ADR 0026](./0026-agentic-rag-evolution.md) (agentic direction + triggers) · [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md) (LangGraph/ports) · [ADR 0022](./0022-grounded-answer-langgraph-gpt5-mini.md) (grounded-answer flow) · [Epic 10](../prd/epic-10-agentic-rag.md) (Stories 10.1, 10.2, 10.5) · [MISSION-049](../learning/missions/MISSION-049/mission.md) (the measurement) · concept [agentic-rag](../learning/concepts/agentic-rag.md)

## Context
ADR 0026 set the *direction* (agentic as a triggered, incremental evolution alongside the fixed
flow). [MISSION-049](../learning/missions/MISSION-049/mission.md) supplied the *trigger with
evidence*: on multi-hop questions the fixed single-shot flow's recall@5 **collapses** (0.889 → 0.444
at 2 hops → 0.278 at 3), the cheap fixes are **ruled out** (bigger k: 0.50 at k=20; query-rewrite:
no/worse), and **only multi-query decomposition recovers** it (→ 0.889). So there is a real, measured
reason to add exactly one capability — **decomposition** — and a decision to also stand up the
**reusable agentic foundation** it rides on, so later measured capabilities slot in without a rewrite.

This ADR is the concrete design for: (10.1) a **Tool port + registry**, (10.2) a **cyclic controller
+ guardrails**, and (10.5) the **decomposition slice** as the first flow on that foundation. The
fixed flow stays the default; agentic is selected per query.

### What already exists (reuse, don't rebuild — ADR 0021)
| Seam | Where | Reused as |
|---|---|---|
| Grounded-answer graph `analyze → retrieve → generate → validate` | `llm/answer.py` (`grounded_answer`) | the spine; agentic adds nodes + a branch, doesn't replace it |
| `make_hybrid_retrieve` / `hybrid_retrieve` → `RetrievalOutcome(documents, abstained)` | `llm/hybrid.py` | the **retrieval primitive** each sub-query / tool calls |
| Citations in `Document.metadata` (server-resolved, FR16), grounding validator, abstention | `llm/answer.py`, `llm/grounding.py` | **hard invariants** threaded through every added step |
| `RetrievalFilters(user_id=…)` ACL, tenant scoping (NFR10), injection defense (Epic 6) | `db/retrieval.py`, Epic 6 | tools inherit tenant scope + injection defense on their I/O |
| Eval harness (`eval run`/`compare`), Langfuse tracing | `eval/`, telemetry | gates + traces the agent (per-step spans) |

## Decision
Build an **agentic layer on the same LangGraph + same ports**, enabled per query by a router; ship
the **decomposition slice** as the first and only *measured-justified* flow on it; keep every hard
invariant (citations, abstention, isolation, budget) intact at each added step.

```
             ┌─ router ─ simple ─────────────► [ existing fixed flow ]        ← unchanged, default (~80%)
 query ──────┤
             └─ hard (multi-part) ─► [ agentic controller ] ──► plan/decompose
                                           │                        │
                                           │              ┌─ sub-q1 ─► retrieval tool ─┐
                                           ▼              ├─ sub-q2 ─► retrieval tool ─┤─► merge (per-part
                                     observe/loop ◄───────┴─ …       (tenant-scoped) ──┘    citations)
                                           │                                                   │
                                           └──────────────► existing generate → validate ◄─────┘
```

### 1. Tool port + registry (Story 10.1)
- A **`Tool` port**: `name`, typed `args`/`returns`, `description` (for the controller to choose it),
  and `invoke(args) -> ToolResult`. Each **corpus/tenant becomes a retrieval tool** (wrapping
  `hybrid_retrieve`); non-retrieval tools (structured-DB lookup, unit/torque calc) use the same port.
- A **registry** maps names → tools, **config-driven** (wire a new corpus with config, no code).
- **Two invariants baked into the port, not left to the caller:** every `ToolResult` carries
  **provenance** (document/version/page/section) so citations survive tool use (FR16); and a tool is
  **tenant-scoped** — constructed for one tenant, it *cannot* read another's data (isolation tests
  extend Epic 6). Injection defense wraps tool inputs/outputs.
- Unit-testable with fakes (a `FakeTool` returns canned `ToolResult`s) — so the controller is tested
  with **no DB/LLM**, like the rest of the request-time stack.

### 2. Cyclic controller + guardrails (Story 10.2)
- The graph becomes **cyclic** (ReAct-style): a **controller node** decides a step (call a tool /
  stop), **observes** the result, and loops or finishes. LangGraph already supports cyclic graphs +
  checkpointing — no new framework (ADR 0021).
- **Guardrails are deterministic and mandatory**, so the agent can never run away:
  - `max_steps` (hard cap on loop iterations),
  - per-query **token/cost budget** and **wall-time** cap,
  - **loop / no-progress detection** (same tool+args, or no new evidence → terminate),
  - a **kill-switch flag** per tenant, and the **router** that only sends *hard* queries here.
- **Checkpointing** persists controller state so a long/interrupted run is resumable (LangGraph
  checkpointer) — and so a step can be traced/replayed. *(Deferred — not in the shipped loop; see
  [Implementation notes](#implementation-notes--one-deviation-from-the-plan).)*

### 3. Query decomposition — the first flow (Story 10.5, the measured slice)
The minimal, bounded flow that cashes the MISSION-049 result:
1. **Decompose node**: one LLM call splits a compound question into an ordered/parallel set of
   sub-questions (degrades to a *single* sub-question for simple queries → no over-planning, 10.5 AC3).
2. **Fan-out retrieval**: each sub-question calls the **retrieval tool** (reusing `hybrid_retrieve`,
   same filters/tenant scope).
3. **Merge**: union the retrieved evidence, **keeping each chunk's original citation** (no re-ranking
   away provenance).
4. **Generate → validate**: the *existing* nodes answer over the merged evidence; grounding validator
   + abstention unchanged — an unsupported claim is still dropped/abstained.

This is barely "agentic" (one split call + deterministic fan-out), which is the point: it is the
*smallest* slice with measured justification, and it proves the foundation end-to-end.

### 4. The gate (nothing becomes default un-measured)
Agentic is enabled **per query class only when it wins a gate** (10.7 AC4):
- **Retrieval**: the MISSION-049 probe — recall **0.444 → ~0.89** on the multi-hop gold.
- **Answer**: Ragas `answer_correctness`/`faithfulness` on the probe (decomposed vs fixed flow), via
  the existing `compare --runs` harness (judge-averaged, MISSION-047 discipline).
- **Cost/latency**: per-query budget respected; a cheaper model for the split; p95 within target.
- **Safety**: tenant-scoped tools + injection defense tests (Epic 6) extended to tool I/O.

## How it works — concepts (so the foundation is understood, not just merged)
*(expanded in concept [agentic-rag](../learning/concepts/agentic-rag.md))*
- **Why single-shot can't multi-hop** — a bi-encoder embeds the *whole* question into one vector; a
  2-part question's vector is dominated by one part, so the other part's chunks never rank (measured:
  recall halves, and k=20 doesn't help — it's representation, not budget).
- **Tool** = a typed capability behind a port (retrieval-over-corpus-X, calculator, DB-lookup). The
  controller picks tools by their `description`; the **registry** makes the tool set data, not code.
- **Plan–act–observe (ReAct)** = the loop *plan a step → act (call a tool) → observe the result →
  decide to loop or stop*. "Agentic" = **the model chooses the steps**, vs the fixed flow where the
  engineer wired them.
- **Guardrails** exist because a loop + an LLM = unbounded cost/failure: `max_steps`, budget, and
  no-progress detection make termination **deterministic**, not model-dependent.
- **Checkpointing** persists loop state → a run is resumable and replayable (debuggability + 10.2 AC3).
- **Citations survive** because provenance is a field on `ToolResult` (not reconstructed later), and
  merge preserves it — the grounding guarantee (ADR 0022) is unchanged by tool use.

## Consequences
**Positive** — answers the measured multi-hop failure; the foundation (Tool port, controller,
guardrails, trajectory traces) is reused by every later agentic capability; fixed flow unchanged for
the 80%; every invariant preserved by construction.
**Negative / watch** — more LLM calls → cost/latency (mitigated: router gates entry, cheap split
model, budgets, sub-result caching); less determinism + new failure modes (mitigated: step/loop
guards, trajectory evals, kill-switch); citations harder across steps (mitigated: provenance is a
required field on `ToolResult`, isolation tests extended).
**Neutral** — request-time only (ADR 0002); no change to the build-time KB pipeline.

## Alternatives considered
- **Deterministic splitter (no LLM) for decomposition** — split on punctuation/conjunctions. Rejected
  as the *primary* path (brittle on real phrasing) but kept as the **fallback** when the LLM split
  returns one part; cheap and worth having.
- **Full plan-act-observe agent as the first build** — rejected: only decomposition is measured
  (MISSION-049); building self-critique (10.6) / multi-corpus routing (10.4) now would pay for
  complexity no measurement demands (the cross-encoder lesson, MISSION-048). We build the *foundation*
  (so they slot in later) but ship only the *measured* flow on it.
- **A separate agent framework** — rejected: LangGraph already gives cyclic graphs + checkpointing
  behind our ports (ADR 0021); no new stack.

## Scope — built now vs explicitly deferred
**Now (shipped):** Tool port + registry (retrieval tool), cyclic controller + guardrails,
decomposition flow, `/ask` flag, the gate.
**Deferred until its own failure class is measured:** **checkpointing** (see below), the **router**
(decomposition self-gates per query for now; a dedicated compound-question router is not built),
multi-corpus **routing** (10.4 — needs a multi-domain *single-tenant* corpus or multi-corpus authz;
structurally provable but unmeasured), non-retrieval **tools** (calculator/DB), **self-critique**
(10.6), **planning** beyond flat decomposition, full **trajectory-eval gate** in CI (10.7).

## Implementation notes — one deviation from the plan
This section records where the shipped code diverges from §2 above, so the ADR stays honest.

- **The controller is a plain-Python loop (`agent/controller.py`), not a LangGraph cyclic graph.**
  §2/alternatives said "LangGraph already gives cyclic graphs + checkpointing — no new framework."
  We kept the *reuse-LangGraph* intent but implemented the loop + guardrails ourselves, deliberately:
  1. **ADR 0021** — the loop *is* the orchestration + the safety invariants (tenant-scoped tools,
     provenance threading, `max_steps`/budget/loop guards). Those must be **structurally guaranteed by
     our code**, not delegated to a framework whose loop/checkpointer semantics we don't control.
  2. **Base-env testability** — all 30 agent tests run in the `validate` CI gate with no LLM/DB/
     langchain (fakes + `ScriptedPolicy`). A LangGraph graph would drag langgraph into every test.
  3. The LLM step still goes through the **`ChatClient` port** (LangChain/Azure adapter behind it,
     ADR 0021), and the decomposition slice returns LangChain `Document`s that plug into the existing
     **LangGraph grounded-answer graph** (ADR 0022) — so LangGraph is reused where it already fits.
- **Checkpointing (Story 10.2 AC3) is NOT implemented.** The plan tied resumable/replayable runs to
  the LangGraph checkpointer; the shipped loop is in-memory. Justified for now: the first and only
  shipped flow (decomposition) is a bounded, synchronous fan-out that needs no durable state, and it
  doesn't even use the dynamic loop. **When** a capability needs durable/long-running agent state
  (e.g. iterative reasoning, human-in-the-loop), that is the trigger to adapt the loop into a
  LangGraph graph and adopt its checkpointer — measure-first, same as every other deferral here.
- **The decomposition slice does not use the cyclic controller** — it's a deterministic fan-out over
  the Tool port (a static plan runs *every* sub-query; the loop's `no_progress` guard would truncate
  it). So the controller ships **tested but not yet exercised by a shipped flow** — ready for the
  first capability whose steps depend on prior observations.

## Revisit when
- The decomposition gate passes → enable it per query class (multi-part detector) and make the agentic
  branch default *for that class only*.
- A measured failure the flat decomposition can't fix (conditional/iterative hops, cross-tool) →
  build the next controller capability on this foundation.
- A multi-domain single tenant appears → multi-corpus routing (10.4) becomes the next measured slice.
