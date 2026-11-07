# 0022. Grounded-answer service: LangGraph + gpt-5.4-mini, server-resolved citations, post-generation grounding validation

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** Architect, PM
- **Related:** FR15–FR18 · NFR1, NFR2, NFR6, NFR16 · Story 3.5 · builds on [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md), [ADR 0007](./0007-pluggable-llm-client-azure-openai.md), [ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md); consumes Story 3.4 hybrid retrieval

## Context
Story 3.5 turns retrieval into a **grounded answer**: a technician-facing response whose every claim cites document/version/page/section (FR16), that surfaces safety warnings, **abstains** when evidence is insufficient (FR17-style), and is never presented as a certified manufacturer instruction. This needs (1) a chat model, (2) request-time orchestration, and (3) a trust model that doesn't rely on the LLM behaving.

Forces:
- **Model longevity + cost:** the cheap 4o-mini/4.1-mini line is **deprecated** (retirement announced 2027-04-14). A new build shouldn't adopt a model it must migrate within months.
- **Trust:** a prompt alone does not guarantee grounding. The model can fabricate citations or assert unsupported claims — unacceptable for industrial safety content.
- **Latency vs safety:** streaming improves perceived latency (NFR2) but would surface unverified claims.

## Decision
A **LangGraph `StateGraph`** orchestrates the request-time flow behind our ports ([ADR 0021](./0021-framework-boundary-langchain-langgraph-vs-data-plane.md)):

```
analyze → retrieve (hybrid, Story 3.4) → [sufficient?] → generate → validate_grounding → [ok?] → finalize
                             └ no → abstain               (model abstains) ┘ no → abstain
```

1. **Model: `gpt-5.4-mini`** (GA, DataZoneStandard/EU, verified available in France Central; retirement 2027-09-21 — longer runway than 4o-mini). Fallback `gpt-4.1-mini` with **no architecture change** (one Terraform variable + `.env`). Provisioned via Terraform like the embedding deployment.
2. **Structured outputs + server-resolved citations:** the model emits typed `claims` referencing **opaque evidence handles** (`[E1]…`), never raw document IDs. Citations are resolved **server-side** from trusted retrieval metadata — the model cannot fabricate a reference; an unknown handle is treated as unsupported (FR16).
3. **Post-generation grounding validation (`validate_grounding`):** a batched **LLM-judge** (`GroundingValidator` port, `LLMGroundingValidator` default) checks each claim is *entailed* by its cited evidence (supported/partial/unsupported). A cross-encoder/NLI adapter can replace it behind the port later. Validity of a citation ≠ support — we check support.
4. **Grounding policy (safety asymmetry):** unsupported **safety-critical** claim → **abstain the whole answer**; unsupported non-critical claim → **drop + warn**; partial → keep + warn. We **validate before returning** (no streaming of unverified claims) — sécurité > TTFT.
5. **Abstention + notice:** insufficient evidence (empty retrieval, model abstains, or nothing survives validation) → "insufficient evidence", never invented content (AC4). Every answer carries a **not-certified notice** (AC5).

### Model parameters: `temperature` vs `reasoning_effort`
`gpt-5.4-mini` is a **reasoning model**: it fixes `temperature=1` (any other value 400s) and is tuned by **`reasoning_effort`** (minimal/low/… — depth vs cost/latency). Non-reasoning models (the `gpt-4.1-mini` fallback) accept an explicit **`temperature`** and don't take `reasoning_effort`. So the adapter sends **only the knob the model supports**, selected by a reasoning-model heuristic (name prefix `gpt-5`/`o1`/`o3`/`o4`):
- reasoning model → `reasoning_effort`; an explicit `CHAT_TEMPERATURE` is **rejected at config time** (clear error, not a raw Azure 400).
- non-reasoning model → `temperature` if set; no `reasoning_effort`.

`chat_temperature` is optional (`None` default → nothing sent). This keeps the validated `gpt-5.4-mini` behaviour untouched while making the fallback fully tunable.

## Consequences
**Positive**
- **Trust is structural, not prompt-based:** opaque handles + server-side citation resolution + entailment validation mean a fabricated/unsupported claim can't reach the user; injection in a document is *contained* (an injected instruction only survives if entailed by evidence, which it isn't).
- **Longer model runway**; fallback is a config swap.
- **Ports keep it swappable** (ADR 0021): `ChatClient`, `GroundingValidator`; `Fake*` make the whole graph CI-testable without network; retrieval/tenant/citations stay in our SQL.
- **Correct per-model params** — no 400s, fallback tunable.

**Negative / risks**
- **Two LLM calls** (generate + validate) per answered question → ~2× token cost + latency. Mitigated: batched judge (1 call), `reasoning_effort=minimal`, abstention short-circuits before generation.
- **Latency:** validating before returning forgoes streaming TTFT (NFR2); reasoning adds latency. Accepted for safety; NFR1 (p95) governs *retrieval*, not generation.
- **Reasoning-model detection is heuristic** (name prefix) — documented and overridable.
- **LLM-judge is still an LLM:** entailment against provided text is far more constrained than open generation, but not infallible; a cross-encoder adapter is the hardening path (Story 3.6 tunes thresholds).

**Neutral**
- `validate_grounding` is a distinct node so Story 3.6 can measure/tune it (faithfulness, citation precision, abstention rate).

## Alternatives Considered
- **gpt-4o-mini / gpt-4.1-mini as the primary model:** cheap and adequate, but deprecated (2027-04-14) — kept only as fallback.
- **gpt-4o / larger model:** more capable, ~15× cost; overkill for grounded synthesis at MVP.
- **Prompt-only grounding (no validate step):** simplest, but trusts the model to not fabricate — rejected for safety-critical content.
- **NLI cross-encoder now:** most rigorous, but a heavy torch dependency against [ADR 0012](./0012-local-first-dev-cloud-models-only.md); deferred behind the `GroundingValidator` port.
- **Hand-rolled control flow instead of LangGraph:** re-implements a state machine poorly; LangGraph is the request-time orchestrator per [ADR 0002](./0002-dual-orchestration-dagster-langgraph.md).

## Revisit When
- Eval (Story 3.6) shows the LLM-judge misses unsupported claims → swap an NLI cross-encoder behind `GroundingValidator`.
- Latency/cost of two calls is too high → single-pass self-citation + cheaper check, or caching (Story 3.7).
- `gpt-5.4-mini` nears retirement or a cheaper longer-lived model appears → change the Terraform variable (+ re-benchmark).
