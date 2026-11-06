# Why LangGraph (and not just LangChain)?

_Explainer companion to [ADR 0002](../adr/0002-dual-orchestration-dagster-langgraph.md). Part of the [architecture index](./index.md). Answers: "I understand LangChain gives us the AI building blocks — what does LangGraph add?"_

> 🇫🇷 Version française : [`why-langgraph.fr.md`](./why-langgraph.fr.md)

---

## One-sentence answer

> **LangChain gives you the bricks. LangGraph is the controller** that decides *which* brick runs next, carries state between them, branches, loops, checkpoints, and makes the whole decision path inspectable.

LangChain = the components (LLM client, retriever, prompt templates, output parsers, tool wrappers).
LangGraph = the **state machine / wiring** around those components.

If IKIP's flow were a straight line — *retrieve → stuff into prompt → call LLM → return* — a plain LangChain chain would be enough. It isn't: the flow is full of **decisions**, and that is the gap LangGraph fills.

---

## The flow is not linear — it is decision-heavy

One real IKIP query: *"Fault on this equipment — find the applicable maintenance procedure for this model and revision."*

```
authorize? ──no──▶ 403 (stop)
   │yes
analyze → identify equipment model/revision
   │
hybrid retrieval (filtered by that model/revision)
   │
rerank
   │
enough evidence? ──no──▶ ABSTAIN ("insufficient evidence")   ◀── safety-critical branch
   │yes
generate cited answer + surface safety warnings
```

Three things here a linear chain cannot express cleanly:

1. **A gate** (`authorize?`) that can stop the whole thing *before any retrieval* — authorize-before-retrieve (FR21).
2. **A branch** (`enough evidence?`) where one path answers and the other *refuses* — abstention (FR17), the single most important safety behavior in this project.
3. **State** that accumulates across steps: the query → identified model/revision → retrieved chunks → rerank scores → sufficiency verdict → citations → trace.

---

## Important: LangGraph does not "magically" decide — *you* declare the decisions

A common misconception: that LangGraph figures out on its own when to use which brick. It does not. **You** define the graph — the **nodes** (the steps) and the **conditional edges** (the decisions) — and LangGraph executes that logic reliably, with state and traceability.

In IKIP, *you* write the rule:
> *"authorize first; then identify the equipment; then retrieve; and **IF** the evidence is not sufficient **THEN** abstain, **ELSE** generate a cited answer."*

LangGraph's job is to run that declared logic dependably — carrying the shared **state** between steps, taking the branch you specified, looping or resuming when needed, and keeping the whole path **inspectable** (→ `QueryTrace`).

So the precise way to say it:

> LangGraph is the **state machine** that chains the LangChain bricks according to **explicit decisions you have defined**, passing a shared **state** between steps, and keeping everything **traceable and resumable**.

Division of labour, stated plainly:
- **LangChain brick** = does the work (talk to the LLM, query the vector store, parse an output).
- **LangGraph graph** = decides the sequence: *"first authorize, then identify equipment, then retrieve, and IF not enough evidence THEN abstain."*

The real value is therefore not "it connects bricks" — it is that **your decision rules + the state memory + the traceability** are first-class, testable things, which is what makes abstention and safety *provable* (Story 5.3) rather than hidden inside prompt text.

---

## What LangGraph specifically brings to IKIP

| Capability | Why IKIP needs it | Traces to |
|---|---|---|
| **Explicit shared state** | Every node reads/writes one State object; no manually threading dicts between steps. | Core workflow, Epic 3 |
| **Conditional branching** | `authorized?`, `sufficient?` → answer vs **abstain**. This *is* the safety logic. | FR17, FR21 · Story 3.5, 5.3 |
| **Loops / retries / self-correction** | If retrieval is weak, re-query with relaxed filters or re-rank before giving up — a cycle, which plain chains (DAGs) cannot do. | FR12, FR14 |
| **Checkpointing / durable resume** | Persist state per node; resume after a failure; durable, auditable execution. | NFR3 (reliability) |
| **Human-in-the-loop** | Pause for a technician to confirm equipment identity before proceeding — native interrupt/resume. | Safety boundaries (brief §9) |
| **Node-level observability** | Each node is a discrete, traceable unit → maps directly to `QueryTrace`; you can see exactly which path a query took and why it abstained. | FR30 · Story 5.4 |

---

## "Couldn't I just build this in pure Python (no LangChain, no LangGraph)?"

**Yes — and that's the honest truth.** Nothing here *needs* either library:
- An "AI brick" is just an LLM API call, a pgvector query, a JSON parse — plain Python.
- The orchestration is just a state `dict` + `if/else` + loops + `try/except` + logging — plain Python.

Neither LangChain nor LangGraph gives you a capability Python lacks. They are **frameworks, not super-powers.** So the real question is not *possible vs. impossible* — it is **build vs. buy**: what are you willing to re-implement and maintain yourself?

If you hand-write the graph in pure Python, here is what you end up rebuilding — and what LangGraph already provides:

| Capability | In pure Python you must… |
|---|---|
| **Persistent state + checkpointing** | build a layer that saves state after each step (e.g. to Postgres) |
| **Resume after crash** (resume by `thread_id`) | code the "restart at the right node" logic |
| **Streaming** of intermediate steps/tokens | handle the streaming yourself |
| **Human-in-the-loop** (pause → wait → resume) | build the pause/persist/resume plumbing |
| **Inspectable, standard graph** | your `if/else` is bespoke control flow, unique to your codebase |
| **Tracing integration** (LangSmith, etc.) | instrument every step by hand |

So LangGraph's value is **not** "it enables decisions" (`if/else` already does that) — it is that it **saves you from re-implementing and maintaining** durable state, checkpointing, streaming and human-in-the-loop, and gives you a **standard, inspectable graph artifact** instead of homegrown plumbing.

**This is a genuine trade-off, both ways.** Pure Python is a legitimate choice — especially while the flow is simple — and the framework has real costs: an extra dependency, abstractions to learn, and fast-moving versions (LangChain/LangGraph change often). The framework earns its place only when you actually need durable resume, streaming and human-in-the-loop and don't want to own that infrastructure.

**One honest, project-specific reason:** IKIP's brief sets an explicit *learning objective* — to master LangChain / LangGraph / Dagster, which are industry-standard tools. For a thesis/portfolio, demonstrating them is a goal in itself. That is a valid reason — but a **pedagogical/portfolio** one, named as such, not a technical necessity.

Whatever you choose, the safety guarantees come from the tests, not the tool: the abstention set (Story 5.3, a release-blocking gate) and prompt/graph regression gates (Story 5.5) are what make the behavior *provable* — LangGraph just makes that structure easier to express and inspect.

---

## Analogy

- **LangChain** = Lego bricks + motors + sensors (the parts).
- **LangGraph** = the programmable controller + wiring diagram that reads the sensors and decides which motor to fire next — and can stop safely when a reading says *"not enough evidence."*

---

## How the two appear in the diagrams

| Diagram | LangGraph | LangChain |
|---|---|---|
| [System Context](./img/01_system_context.png) | on the RAG node label | on the same label |
| [RAG Workflow](./img/03_rag_workflow.png) | the node chain (principal/solid flow) | backing dependency (dashed "uses integrations") |

The placement is deliberate: **solid arrows = the orchestrated flow (LangGraph); dashed = the library the nodes depend on (LangChain).**

---

## Bottom line

LangChain integrates the models, retrievers and tools. LangGraph is the **stateful, conditional, auditable** controller that turns those integrations into a reliable, testable, safe RAG workflow. You *could* hand-build all of this in pure Python — nothing here is exclusive to the frameworks — but the graph is where the decision logic, state and auditability are easiest to express, test and inspect, and (for this project) it also demonstrates an industry-standard tool, which is a stated learning goal. That is the real case for it — build-vs-buy plus pedagogy — not that `if/else` is incapable.

> Decision record: [ADR 0002 — Dual orchestration](../adr/0002-dual-orchestration-dagster-langgraph.md). Note its "Revisit When": a trivially small system *could* collapse to LangChain-only; IKIP's abstention, authorization and audit needs are what justify the graph.
