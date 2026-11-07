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

## How it maps to the code (`llm/answer.py`)
Built in `build_answer_graph(retrieve, chat_client, validator)` and run by
`grounded_answer(question, …)` → `graph.invoke({"question": question})`.

| LangGraph element | In `answer.py` | Role |
|---|---|---|
| State (`StateGraph(AnswerState)`) | `class AnswerState(TypedDict)` | carries `question`, `documents`, `doc_by_marker`, `evidence`, `sufficient`, `draft`, `result` between nodes |
| Node `analyze` | `def analyze` | normalize the query (no LLM) |
| Node `retrieve` | `def retrieve_node` | calls our `hybrid_retrieve`; assigns opaque handles `[E1]…`; fills `evidence` |
| Node `generate` | `def generate` | `chat_client.complete_structured(...) → GroundedAnswer` |
| Node `validate` | `def validate` | `GroundingValidator` + grounding policy → `AnswerResult` |
| Node `abstain` | `def abstain` | "insufficient evidence" |
| Conditional edge | `route_after_retrieve` | `generate` if `sufficient` else `abstain` |
| Conditional edge | `route_after_generate` | `abstain` if model returned `status="abstained"` else `validate` |

## Walkthrough — trace #1: answered (test `test_live_grounded_answer_with_real_model`)
Query **"What does fault E42 mean?"**, with a chunk `c1` = *"Fault code E42 indicates the pump motor has overheated."*

1. **analyze** → `question="what does fault e42 mean?"`.
2. **retrieve** → `hybrid_retrieve` returns `c1`; state gets `doc_by_marker={"E1": <c1>}`, `evidence={"E1": "Fault E42 … overheated."}`, `sufficient=True`.
3. `route_after_retrieve` → **generate**.
4. **generate** → the prompt shows only the opaque handle `[E1]`; `gpt-5.4-mini` returns `GroundedAnswer(status="answered", claims=[Claim(text="E42 = pump motor overheat", evidence_markers=["E1"], safety_critical=False)])`.
5. `route_after_generate` → **validate** (status ≠ abstained).
6. **validate** → the validator judges `E1` **supported** → claim kept; the citation is **resolved server-side** from `doc_by_marker["E1"].metadata` (revision A, page 142). `result = AnswerResult(status="answered", answer="… [E1]", not_certified_notice=…)`.
7. END → verified grounded answer.

## Walkthrough — trace #2: abstention (test `test_live_abstains_on_irrelevant_evidence`)
Query **"What is the torque spec for the gearbox housing bolts?"**, evidence only mentions lubrication.

1. **retrieve** returns an off-topic doc → `sufficient=True` (there *is* text) → **generate**.
2. **generate** → the model, constrained "answer only from the evidence, else abstain", returns `status="abstained"`.
3. `route_after_generate` → **abstain** → `AnswerResult(status="abstained", reason="insufficient evidence")`. Nothing invented (AC4).

*(Third branch, covered by the pure tests `test_answer_graph.py`: an unsupported **safety-critical** claim at `validate` → immediate full abstention — the safety asymmetry.)*

## Why not a plain if/else
Three decision points (sufficiency, model abstention, grounding failure) sharing one state → exactly LangGraph's model. It also leaves room to add nodes (equipment identification, retries, tool calls) **without rewriting** the flow, and the graph doubles as the execution trace for observability ([ADR 0013](../../adr/0013-llmops-observability-otel-langfuse.md)).

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
