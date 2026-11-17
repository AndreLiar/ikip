# Agentic RAG — what it is, why, and how it stays grounded

> Companion to [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) (design) and
> [MISSION-049](../missions/MISSION-049/mission.md) (the measurement that justified it). This note
> explains the *concepts*; code references are added as the foundation is built.

## 1. Flow-RAG vs agentic-RAG — who decides the steps?
Our current pipeline is **flow-RAG**: a fixed graph the *engineer* wired —
`analyze → retrieve → generate → validate`. The LLM only writes the final answer; it does **not**
decide *what* to retrieve, *whether to retrieve again*, or *how many steps* to take.

**Agentic-RAG** hands that control to the model: it runs a loop — **plan a step → act (call a tool) →
observe the result → decide to loop or stop**. The one-line difference: *in flow-RAG the steps are
wired; in agentic-RAG the model chooses them.* That raises the ceiling on question complexity, at the
cost of more LLM calls, less determinism, and more ways to fail — which is why we add it **only where
measured**, behind guardrails, never as the default.

## 2. Why the fixed flow can't do multi-hop (the measured motivation)
Retrieval embeds your **whole question** into one vector (a *bi-encoder*). Ask a 2-part question
("what is X? *and separately* what is Y?") and that single vector is **dominated by one part** — so
the other part's chunks never rank into the top-k. [MISSION-049](../missions/MISSION-049/mission.md)
measured it: recall@5 falls **0.889 (1-hop) → 0.444 (2-hop) → 0.278 (3-hop)**, and it is **not** a
budget problem (k=20 barely helps) — it's *representation*. The fix isn't a bigger k or a better
*single* query (rewrite made it worse); it's **asking separately** — decomposition — which fully
recovers recall (→ 0.889). That gap is the entire reason to go agentic here.

## 3. The building blocks
- **Tool** — a typed capability behind a port: `name`, typed `args`/`returns`, a `description` the
  controller reads to decide *when* to use it, and `invoke()`. "Retrieve over corpus X", "look up a
  spec in the structured DB", "convert units" are all tools. Crucially, a tool is **tenant-scoped**
  (built for one tenant, can't read another's data — NFR10) and every result carries **provenance**
  (doc/version/page) so citations survive (FR16).
- **Registry** — a name → tool map, **config-driven**: wiring a new corpus is data, not code.
- **Controller (ReAct loop)** — the cyclic node that picks a tool, observes, and loops/stops. "ReAct"
  = *Reason + Act* interleaved.
- **Guardrails** — because *a loop + an LLM = potentially unbounded cost/failure*, termination must be
  **deterministic**: `max_steps`, a token/cost/wall-time **budget**, **no-progress detection** (same
  tool+args or no new evidence → stop), and a per-tenant **kill-switch**. These are not optional.
- **Checkpointing** — persist the loop's state so a long/interrupted run is **resumable** and a step
  is **replayable** (debuggability).
- **Router** — decides *fixed flow vs agent* per query, so the ~80% simple lookups never pay the
  agentic tax.

## 4. How grounding survives tool use (the non-negotiable)
Agentic RAG is dangerous exactly where it's powerful: more steps = more chances to state an
unsupported claim. We keep [ADR 0022](../../adr/0022-grounded-answer-langgraph-gpt5-mini.md)'s
guarantee — *every claim resolves to a retrieved citation, or we abstain* — by construction:
1. **Provenance is a field on every `ToolResult`**, not reconstructed afterwards — so a chunk's
   citation rides with it through every merge.
2. The **existing grounding validator + abstention** still run on the final answer, unchanged — a
   claim with no retrieved citation is still dropped.
3. **Tools are tenant-scoped + injection-defended**, so more tool use never widens the data or attack
   surface across tenants.

Memory/decomposition/tools change **what we retrieve and how we assemble it — never what we claim**
(the same principle as [ADR 0032](../../adr/0032-memory-and-context-engineering.md)).

## 5. The disciplined path (not "agentic everywhere")
Build the **foundation** (Tool port, registry, cyclic controller, guardrails, trajectory traces) so
capabilities slot in later — but **ship only the measured slice on it** (decomposition). Each further
capability (multi-corpus routing, self-critique, planning, non-retrieval tools) waits for **its own
measured failure class** and must **win a quality+cost gate** before it's enabled — the same
measure-first discipline that *rejected* BM25 ([MISSION-046](../missions/MISSION-046/mission.md)) and
dedup ([MISSION-047](../missions/MISSION-047/mission.md)) and *deferred* the cross-encoder
([MISSION-048](../missions/MISSION-048/mission.md)).

## 6. Why a plain loop, not a LangGraph graph (a side-by-side)
The ADR 0033 plan reached for LangGraph's cyclic graph; the shipped controller
(`agent/controller.py`) is a plain-Python loop. Here is the *same* behaviour both ways, so the
trade-off is concrete — not a matter of taste.

**What LangGraph adds on top of a loop:** a **checkpointer** (persist run state → resume/replay a
long/interrupted run), **streaming** of steps, and **conditional-edge routing**. Those earn their
weight for *long, stateful, resumable* agents. Our controller is a **bounded, synchronous** loop
(≤4 steps, finishes in one request), so none of the three apply yet.

### (a) the shipped loop — ~1 function, reads top-to-bottom
```python
def run_agent(*, question, registry, policy, budget, cost_fn):
    steps, evidence, seen_actions, seen_chunks, cost = [], [], set(), set(), 0.0
    if budget.kill_switch:
        return AgentTrajectory(steps, evidence, "kill_switch")
    for i in range(budget.max_steps):                       # ← max_steps guard (the `for` bound)
        action = policy.decide(question=question, tools_menu=registry.describe(),
                               observations=_observations(steps), step=i)
        if action.is_stop:
            return AgentTrajectory(steps, evidence, "stop")
        key = (action.tool, _args_key(action.args))
        if key in seen_actions:                             # ← loop guard
            return AgentTrajectory(steps, evidence, "loop")
        seen_actions.add(key)
        try:
            tool = registry.get(action.tool)
        except KeyError:                                    # ← hallucinated-tool guard
            steps.append(AgentStep(action, None))
            return AgentTrajectory(steps, evidence, "error")
        result = tool.invoke(action.args)
        steps.append(AgentStep(action, result)); cost += cost_fn(action, result)
        new = [e for e in result.evidence if e.provenance.get("chunk_id") not in seen_chunks]
        seen_chunks.update(e.provenance.get("chunk_id") for e in new); evidence.extend(new)
        if budget.max_cost_usd and cost > budget.max_cost_usd:
            return AgentTrajectory(steps, evidence, "budget")   # ← cost guard
        if not new:
            return AgentTrajectory(steps, evidence, "no_progress")  # ← no-progress guard
    return AgentTrajectory(steps, evidence, "max_steps")
```
Every guardrail is an explicit `if` on the same page — readable, unit-testable, and *provably*
terminating. No heavy import: the whole thing (and its 11 tests) runs in the base `validate` CI lane.

### (b) the equivalent LangGraph graph — more code, split across nodes + routers
```python
from typing import TypedDict
from langgraph.graph import StateGraph, END          # ← now every importer pulls langgraph

class S(TypedDict):
    question: str; steps: list; evidence: list
    seen_actions: set; seen_chunks: set; cost: float; pending: object; stop_reason: str | None

def decide(s: S) -> S:
    return {"pending": policy.decide(question=s["question"], tools_menu=registry.describe(),
                                     observations=_observations(s["steps"]), step=len(s["steps"]))}

def route_after_decide(s: S):                         # guardrails leak into routers…
    a = s["pending"]
    if a.is_stop:                         s["stop_reason"] = "stop";       return END
    if (a.tool, _args_key(a.args)) in s["seen_actions"]: s["stop_reason"]="loop"; return END
    if len(s["steps"]) >= budget.max_steps: s["stop_reason"] = "max_steps"; return END
    return "act"

def act(s: S) -> S:
    a = s["pending"]
    try: tool = registry.get(a.tool)
    except KeyError: return {"steps": s["steps"] + [AgentStep(a, None)], "stop_reason": "error"}
    result = tool.invoke(a.args)
    new = [e for e in result.evidence if e.provenance.get("chunk_id") not in s["seen_chunks"]]
    return {"steps": s["steps"] + [AgentStep(a, result)], "evidence": s["evidence"] + new,
            "seen_actions": s["seen_actions"] | {(a.tool, _args_key(a.args))},
            "seen_chunks": s["seen_chunks"] | {e.provenance.get("chunk_id") for e in new},
            "cost": s["cost"] + cost_fn(a, result), "_added": len(new)}   # must stash a flag…

def route_after_act(s: S):                            # …and the other half of the guardrails here
    if s.get("stop_reason") == "error":                 return END
    if budget.max_cost_usd and s["cost"] > budget.max_cost_usd: s["stop_reason"]="budget"; return END
    if not s["_added"]:                                 s["stop_reason"]="no_progress"; return END
    return "decide"

g = StateGraph(S); g.add_node("decide", decide); g.add_node("act", act)
g.set_entry_point("decide")
g.add_conditional_edges("decide", route_after_decide, {"act": "act", END: END})
g.add_conditional_edges("act", route_after_act, {"decide": "decide", END: END})
app = g.compile()   # + recursion_limit as a *second*, framework-owned stop condition
```

### What the side-by-side shows
- **More code + indirection** for identical behaviour: an explicit `State` schema, two nodes, two
  router functions, immutable state-merging, and a stashed `_added` flag to reconstruct "did this
  step add evidence?" — which the loop just *knows*.
- **The safety-critical guardrails scatter** into `route_after_decide` / `route_after_act` (routers
  that awkwardly mutate state), and termination now *also* depends on LangGraph's `recursion_limit`
  and edge-evaluation — framework-owned behaviour, versus four `if`s I own and test directly.
- **Every test pulls langgraph** — the agent logic leaves the fast, dependency-free CI lane.
- **For zero gain today:** the checkpointer/streaming/branching we'd be buying go unused, because the
  run is bounded and synchronous.

**When (b) wins:** the day a capability needs *durable, resumable* agent state (iterative reasoning
over minutes, human-in-the-loop pauses) — then the checkpointer is the whole point, and the loop
becomes a graph. Until then, (a) is the simplest thing that meets the need and keeps the safety
guarantees in code we own. Same measure-first rule as not adding the torch reranker on spec.

## See also
[ADR 0026](../../adr/0026-agentic-rag-evolution.md) (direction/triggers) · [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) (this design) · [grounded-answers](./grounded-answers.md) · [hybrid-retrieval](./hybrid-retrieval.md) · [rag-orchestration](./rag-orchestration.md)
