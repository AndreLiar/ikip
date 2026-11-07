# MISSION-016 — Decisions

Full rationale in [ADR 0022](../../../adr/0022-grounded-answer-langgraph-gpt5-mini.md). Summary:

## D1 — Model gpt-5.4-mini (fallback gpt-4.1-mini)
The cheap 4o-mini/4.1-mini line is **deprecated** (retirement 2027-04-14); `gpt-5.4-mini`
is GA, DataZoneStandard/EU, verified available in France Central (`az cognitiveservices
model list`), retirement 2027-09-21. Fallback `gpt-4.1-mini` with no architecture change
(Terraform variable + `.env`). Final choice is budget/benchmark-driven (Story 3.6), not reputation.

## D2 — Structured outputs + server-resolved citations
Model emits typed claims referencing **opaque handles** `[E1]…`; citations resolved
**server-side** from retrieval metadata. The model can't fabricate a document reference;
an unknown handle ⇒ unsupported. Prompt alone is never trusted as a grounding guarantee.

## D3 — validate_grounding = batched LLM-judge behind a port
A valid handle ≠ a supported claim, so we check **entailment** after generation. Default:
one batched LLM-judge call (`LLMGroundingValidator`) behind `GroundingValidator`. Cheaper/
no-new-dep vs a local NLI cross-encoder (against [ADR 0012](../../../adr/0012-local-first-dev-cloud-models-only.md)); a cross-encoder adapter can replace it later.
**Policy (safety asymmetry):** unsupported safety-critical ⇒ abstain whole answer; unsupported
non-critical ⇒ drop + warn; partial ⇒ keep + warn.

## D4 — Validate before returning (sécurité > TTFT)
Generate structured (non-streamed) → validate → return. We never stream an unverified claim.
NFR1 p95 governs *retrieval*; generation latency is accepted for safety. (Streaming the
*validated* answer later is possible without changing the contract.)

## D5 — Temperature optional (option B)
`chat_temperature: float | None = None`. The adapter sends **only the knob the model
supports**: reasoning models (prefix gpt-5/o1/o3/o4) get `reasoning_effort` and **reject**
an explicit temperature at config time (clear error, not a raw Azure 400); non-reasoning
models (gpt-4.1-mini) get `temperature` if set and no `reasoning_effort`. This preserves the
validated gpt-5.4-mini behaviour and makes the fallback fully tunable. Pure helpers
(`_chat_kwargs`, `_reasoning_model`) are unit-tested without network.
