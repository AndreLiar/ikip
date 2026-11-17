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

## See also
[ADR 0026](../../adr/0026-agentic-rag-evolution.md) (direction/triggers) · [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) (this design) · [grounded-answers](./grounded-answers.md) · [hybrid-retrieval](./hybrid-retrieval.md) · [rag-orchestration](./rag-orchestration.md)
