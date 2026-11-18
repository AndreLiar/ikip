# MISSION-054 — Exercise the cyclic controller: make it bridge-hop capable, then probe (scoping + the enabling slice)

- **Mode:** Guidé (an architecture decision — exercise the deferred controller, capability-before-measurement)
- **Date:** 2026-11-18
- **Related:** [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md) (agentic foundation + controller) · [MISSION-049](../MISSION-049/mission.md) (multi-hop failure → justified decomposition) · [MISSION-050](../MISSION-050/mission.md)/[051](../MISSION-051/mission.md)/[052](../MISSION-052/mission.md) (decomposition gate) · concept [agentic-rag](../concepts/agentic-rag.md)
- **Status:** Enabling slice shipped (controller is now exercisable + bridge-capable); the live probe is the next mission.

## Objective
ADR 0033 shipped the cyclic plan–act–observe controller **tested but unexercised by any flow** — the
decomposition slice is a *static* fan-out (it can't use the loop; the `no_progress`/loop guards would
truncate a fan-out). The open question: is there a **measured failure class that flat decomposition
cannot fix** and the loop can? The candidate is the **bridge / conditional hop** — where hop 2 needs
the *answer* of hop 1 (e.g. "the max temp of the sensor **used by** system X": first find the
sensor, then query its temp). This mission scopes that probe and ships the enabling slice.

## Two findings that reframed the probe (before spending anything)
1. **Flat decomposition cannot fix a bridge hop — by construction.** The decomposer is prompted to
   emit *self-contained* sub-questions ("resolve pronouns so each stands alone") and fans them out
   in parallel. A bridge's second query is **unknowable at split time** (you don't yet know the
   entity), so decomposition structurally can't form it. ✅ The failure class is real and distinct
   from the compound multi-hop that MISSION-049 solved.
2. **The controller, as shipped, also could not bridge.** Its observation history rendered only
   passage **counts** (`tool(args) -> 5 passages`), not content — so the policy could never read the
   entity found at step 0 to form step 1's query. Measuring that controller would be a strawman: it
   would fail for a *plumbing* reason, telling us nothing about whether the agentic approach works.

**Decision — capability before measurement (a deliberate inversion of measure-first).** Normally we
measure the failure before building (MISSION-046/049). Here the fix is a *prerequisite for a fair
measurement*: a controller that structurally can't win is not worth probing. So we first make the
loop minimally bridge-capable, then probe whether it earns its keep. The build is small, pure-tested,
and behind an opt-in flag (default off) — it commits no live cost and no default change.

## The enabling slice (shipped here)
- **`controller.py` — content-aware observations.** `_observations()` now renders a **bounded
  snippet** of each step's evidence (`[chunk_id] text`, capped 3 passages × 240 chars) alongside the
  count, and the system prompt tells the policy to use an entity found in observations to form the
  next query. Bounds keep controller-prompt cost predictable.
- **`agent/agentic.py` (new) — `make_agentic_retrieve`.** The first flow to *exercise* the loop:
  wraps a base `retrieve` into a controller-driven retrieve of the **same shape** as
  `make_decomposed_retrieve`, so it drops into the existing grounded-answer graph unchanged
  (generate/validate, citations, abstention untouched — ADR 0022). Single tenant-scoped tool for
  now; the loop iterates *queries* against it (the bridge mechanism). Multi-corpus routing is later.
- **eval `--agent` (+ `--agent-max-steps`)** on `run`/`ragas`/`compare`, via a `_maybe_agentic`
  helper (agent > decompose, mutually exclusive), recorded under `config.agent` — the A/B is ready.
- **Tests (pure):** observations surface content (not just counts); a scripted bridge recovers c1→c2
  *only because* the policy reads evidence content; `make_agentic_retrieve` gathers loop evidence and
  surfaces the trajectory `stop_reason` on abstention. **34 agent + 44 eval/rerank tests green, ruff
  clean.** Zero live cost.

## The probe plan (next mission)
- **Gold:** a **synthetic grounded mini-corpus** (chosen for a *valid* measurement fastest). Per
  case, two ingested chunks: A ("system S uses component C"), B ("component C has property P =
  value"); question names **S, not C** ("what is P of the component used in S?"), ground_truth =
  value, `relevant_chunk_ids = [A, B]`. Single-shot retrieval surfaces A but not B → the bridge is
  forced. Honest caveat: synthetic/invented entities measure the **mechanism**, not a natural
  distribution — like MISSION-049 it isolates structure, but here the corpus is constructed.
- **Arms:** fixed flow vs `--decompose` vs `--agent`, on the bridge gold.
- **Expected (stated up front for honesty):** fixed fails (gets A only); decompose fails (can't form
  hop 2); `--agent` recovers (reads C from A's evidence, then retrieves B). If `--agent` does *not*
  clear it, that is an equally valuable result — it would say the content-aware loop still isn't
  enough and point at the next gap (e.g. richer observation, a dedicated lookup tool).
- **Metric:** recall@k on the union is deterministic (no paid judge) for the first cut — cheap; add
  Ragas (answer_correctness) only if the recall signal warrants it.

## Honest limits
- The controller change is the **minimum** to enable bridging (content in observations). It is **not
  yet measured live** — this mission ships capability + the seam, not a verdict.
- `--agent` runs a real LLM decision **per step** (cost scales with steps; `max_steps=4` default +
  the guardrails bound it). The live probe's cost is the next mission's concern.
- Still single-tool (one corpus). Multi-corpus routing (10.4) and checkpointing stay deferred
  (ADR 0033) until their own failure class is measured.

## See also
`packages/common/src/ikip_common/agent/agentic.py` · `agent/controller.py` (`_observations`) ·
`eval/__main__.py` (`_maybe_agentic`, `--agent`) · tests `test_agent_agentic.py`,
`test_agent_controller.py`. Enables the bridge-hop probe (next MISSION-0NN).
