# MISSION-055 — The bridge-hop probe: only the cyclic controller clears it (and the live run caught a controller bug)

- **Mode:** Autonome (measurement — does the deferred controller earn its keep on a real failure class?)
- **Date:** 2026-11-19
- **Related:** [MISSION-054](../MISSION-054/mission.md) (enabling slice: content-aware observations + `make_agentic_retrieve` + `--agent`) · [MISSION-049](../MISSION-049/mission.md)/[050](../MISSION-050/mission.md) (compound multi-hop → decomposition) · [ADR 0033](../../adr/0033-agentic-foundation-and-query-decomposition.md)

## Objective
MISSION-054 made the cyclic controller bridge-capable and shipped the eval seam. Now **measure**: is
there a failure class that flat decomposition can't fix and the loop can? The candidate is the
**bridge / conditional hop** (hop 2 needs hop 1's answer). Run fixed vs `--decompose` vs `--agent`
on a controlled bridge corpus.

## Method
`scripts/dataset/gen_bridge_probe.py` builds a **synthetic grounded mini-corpus**: 6 cases, each a
link A ("system S is fitted with component C") + the correct fact B ("C has property P = value") +
**9 same-property distractors** (other components, same P) → 66 chunks, seeded to tenant `…b2`
through the real indexing path. The question names **S + P, never C**. Arms run at **k=5** and
**k=2** (lower k shrinks single-retrieval coverage — a cheap proxy for "corpus too big to
co-retrieve both hops"). Correct-value = the gold value string appears in the answer.

## A controller bug the live run caught (before any verdict)
The first `--agent` run **abstained on 6/6** (recall 0.0). Root cause: `_ControllerDecision.args` was
an open `dict[str, Any]`, which **OpenAI/Azure structured output rejects** (`additionalProperties`
must be false) — so every live controller decision raised and the policy fail-safed to *stop* with
no evidence. The `LlmControllerPolicy` had **never worked live** — it was only tested with a
`FakeChat`. Fixed: the decision carries a **flat typed `query`** (all tools take `{"query": str}`;
the policy rebuilds the dict). **Lesson: a component tested only with fakes is not validated until
it runs live** — the probe paid for itself by surfacing this.

## Result — correct-value per case (6 cases)
| k | fixed | decompose | **agent** |
|---|--:|--:|--:|
| **k=2** (bridge forced) | **1/6** | **1/6** | **5/6** |
| k=5 (easy) | 5/6 | 5/6 | 6/6 |

Abstention at k=2: fixed 0.833, decompose 0.833, **agent 0.167**. Cost: a few cents total
(deterministic estimate ~$0.002/arm; the agent's per-step LLM call is the real but small premium).

## Discovery
1. **The bridge hop is a retrieval-COVERAGE failure, not a reasoning one.** At k=5 a single
   retrieval still co-retrieves both hops for 5/6 cases, and the model bridges **in-context** (all
   arms ~tie). The failure only bites when the second hop can't be co-retrieved — forced here by
   low k / many distractors. This is why it was invisible on a tiny corpus (a false "no problem"),
   echoing MISSION-050's metric-trap and MISSION-049's "collapse only at distance/scale".
2. **Decomposition ties fixed EXACTLY (1/6 at k=2).** This is the key proof that the bridge is a
   **distinct** failure class from the *compound* multi-hop decomposition solved (MISSION-050):
   flat decomposition emits self-contained sub-questions, but hop 2 ("the P of component C?") is
   unknowable at split time — so it can't even form the query. Measured, not assumed.
3. **The cyclic controller is the only arm that clears it (5/6 at k=2, +0.67 vs both).** The
   content-aware loop (MISSION-054) does the bridge: retrieve → read the component out of the
   evidence → re-query by the component → get the fact. This is the **first shipped flow to exercise
   the controller** (ADR 0033) and the first measured justification for it.

## Verdict
**The bridge-hop failure class is real, and only the cyclic controller fixes it.** This justifies
the `--agent` controller for this class — the agentic branch earns its keep where decomposition
structurally cannot. Promotion path (next): a **conditional/bridge detector** to route only these
queries to `--agent` (keep the cheap flow + decomposition for the rest), behind the kill-switch and
the per-step budget — same "default for that class only" discipline as decomposition (MISSION-050).

## Honest limits
- **Synthetic, invented entities, n=6.** This measures the **mechanism** (can the loop bridge?),
  not a natural distribution — like MISSION-049 it isolates structure; a natural bridge corpus would
  strengthen external validity. The direction (only the agent recovers) is unambiguous.
- **k=2 is an artificial lever.** It's a valid *proxy* for "the fact chunk can't be co-retrieved"
  (what happens naturally as a corpus grows), but a real promotion gate should reproduce the failure
  at the production k by scale (more distractors), not by shrinking k.
- **The agent misses 1/6 (pump seal, 34 bar)** even at k=2 — the loop isn't perfect (step budget /
  a re-query that didn't land); worth a trace look before a wider claim.
- **Cost scales per step** (one LLM decision per loop iteration, `max_steps=4` + guardrails bound
  it). The routing detector is what keeps that cost off the easy majority.
- Still single-tool. Multi-corpus routing + checkpointing stay deferred (ADR 0033).

## See also
`scripts/dataset/gen_bridge_probe.py` (`--distractors` sweeps the regime) · `agent/controller.py`
(`_ControllerDecision.query` fix) · `agent/agentic.py` · runs under `eval-results/ab/bridge_d9*`.
Builds on [MISSION-054](../MISSION-054/mission.md); the bridge-detector routing is the next slice.
