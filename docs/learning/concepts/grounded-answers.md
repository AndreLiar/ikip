# Concept — Grounded answers: LangGraph, server-resolved citations, grounding validation

_Write-once concept note. First used by Story 3.5. Decision: [ADR 0022](../../adr/0022-grounded-answer-langgraph-gpt5-mini.md). Follows [hybrid-retrieval](./hybrid-retrieval.md); request-time half of [rag-orchestration](./rag-orchestration.md)._

## What "grounded" means
A grounded answer asserts **only** what the retrieved evidence supports, and every claim is **traceable** to document/version/page/section (FR16). The opposite is a hallucination: fluent text not backed by sources. For industrial maintenance, an ungrounded claim can be dangerous — so the system must prefer **saying nothing** (abstain) over guessing.

## The graph (LangGraph, request-time)
This is where LangGraph earns its place ([rag-orchestration](./rag-orchestration.md)): a stateful, branching flow, not a straight line.

```
analyze → retrieve (hybrid, Story 3.4) → [sufficient?] → generate → validate_grounding → [ok?] → finalize
                             └ no → abstain               (model abstains) ┘ no → abstain
```

- **analyze**: normalize the query (lightweight, no LLM call — stays within a 2-call budget).
- **retrieve**: `hybrid_retrieve` (tenant-scoped SQL). If it abstains/empty → abstain (no LLM call at all).
- **generate**: the model produces a *structured* answer (typed claims + evidence handles).
- **validate_grounding**: check each claim is actually entailed by its evidence.
- **finalize / abstain**: render validated claims + citations + warnings, or abstain.

## Why a prompt is not enough (the trust model)
Two independent mechanisms make grounding **structural**, not a matter of the model behaving:

1. **Opaque handles + server-resolved citations.** The model only sees evidence as `[E1]…[En]` and cites those handles. It **never sees or emits real document IDs** — we map handle → retrieval metadata **server-side**. So a citation *cannot* be fabricated; an unknown handle is treated as unsupported.
2. **Post-generation grounding validation.** A valid handle still doesn't prove the evidence *supports* the claim. `validate_grounding` runs an **entailment check** (default: a batched LLM-judge behind the `GroundingValidator` port) returning supported / partial / unsupported. Judging entailment against provided text is far more constrained than open generation, so it's markedly more reliable — and a cross-encoder/NLI adapter can replace it later.

## Grounding policy (safety asymmetry)
After validation:
- **supported** → keep the claim.
- **partial** → keep + warn.
- **unsupported, non-critical** → **drop** the claim + warn.
- **unsupported, safety-critical** → **abstain the whole answer** (a wrong safety instruction is worse than no answer).

We **validate before returning anything** — never stream an unverified claim (sécurité > time-to-first-token). Document injection is *contained* by this: an injected instruction only survives if the evidence entails it, which it won't.

## Model: reasoning vs classic (temperature vs reasoning_effort)
`gpt-5.4-mini` is a **reasoning model**: `temperature` is fixed at 1 (any other value errors) and depth/cost is tuned by **`reasoning_effort`**. A classic model (`gpt-4.1-mini` fallback) takes an explicit **`temperature`** and no `reasoning_effort`. The adapter sends **only the knob the model supports** (detected by name prefix); setting a temperature on a reasoning model is rejected at config time, not left to a 400. `gpt-5.4-mini` is chosen over the deprecated 4o-mini/4.1-mini for a longer lifecycle ([ADR 0022](../../adr/0022-grounded-answer-langgraph-gpt5-mini.md)).

## Ports & testability
`ChatClient` (structured completion) and `GroundingValidator` are ports; `FakeChatClient` / `FakeGroundingValidator` make the **whole graph CI-testable without a network call** — including the adversarial scenarios (ambiguous, contradictory, obsolete version, document injection, no evidence). Retrieval, tenant scoping and citation resolution stay in our SQL ([ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md)).

## Rules to remember
1. Ground every claim; prefer **abstention** over guessing (AC4).
2. Model sees **opaque handles**; citations are **resolved server-side** — never trust model-emitted references (FR16).
3. A valid citation ≠ a supported claim → run **entailment validation**.
4. Safety asymmetry: unsupported safety-critical claim ⇒ **abstain**; unsupported non-critical ⇒ drop + warn.
5. **Validate before returning** (no streaming of unverified claims).
6. Reasoning model ⇒ `reasoning_effort`; classic model ⇒ `temperature`; send only the supported one.
7. Always attach the **not-certified notice** (AC5); never present as a certified manufacturer procedure.

## Related
- Decision: [ADR 0022](../../adr/0022-grounded-answer-langgraph-gpt5-mini.md) · boundary [ADR 0021](../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md) · [ADR 0002](../../adr/0002-dual-orchestration-dagster-langgraph.md).
- Concepts: [hybrid-retrieval](./hybrid-retrieval.md) · [rag-orchestration](./rag-orchestration.md) · [embeddings](./embeddings.md) · [why-rag](./why-rag.md).
- Next: evaluation (Story 3.6, Ragas) measures faithfulness / citation precision / abstention rate and tunes thresholds + the grounding validator; caching (3.7).
