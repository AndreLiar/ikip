# MISSION-016 — LangGraph grounded-answer service with citations (Epic 3, Story 3.5)

**Mode:** Guidé (model choice + grounding/validation + temperature decisions) → Autonome (impl) + knowledge transfer.
**Objective:** turn retrieval into a trustworthy grounded answer — a LangGraph flow that synthesizes cited answers from evidence, validates grounding, surfaces warnings, and abstains when evidence is insufficient; never presented as a certified manufacturer instruction.
**Maps to:** Epic 3 / Story 3.5. Consumes Story 3.4 (`hybrid_retrieve`); applies [ADR 0022](../../../adr/0022-grounded-answer-langgraph-gpt5-mini.md), [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Decisions (brainstormed + ratified)
- **Model `gpt-5.4-mini`** (reasoning, GA, DataZoneStandard/EU; verified available), fallback `gpt-4.1-mini` — over the deprecated 4o-mini. [decisions.md](./decisions.md) D1.
- **Structured outputs + server-resolved citations** (opaque handles; model can't fabricate a reference). D2.
- **Post-generation `validate_grounding`** = batched LLM-judge behind `GroundingValidator` port; safety-asymmetric policy. D3.
- **Validate before returning** (sécurité > TTFT). D4.
- **Temperature optional (option B)**: `chat_temperature` only for non-reasoning models; reasoning models use `reasoning_effort`; unsupported combo rejected at config time. D5.

## Acceptance criteria
1. LangGraph workflow: analyze → (equipment via filters) → retrieve → rerank → sufficiency → cited generation. — **[verified]** (`StateGraph` in `answer.py`; graph tests)
2. Answers grounded only in retrieved evidence; each claim cites doc/version/page/section. — **[verified]** (opaque handles + server-side resolution; `test_answered_resolves_citation_server_side`; live test)
3. Safety warnings + uncertainties surfaced. — **[verified]** (`warnings` in schema + policy; partial-support warning test)
4. Abstains rather than inventing when evidence insufficient. — **[verified]** (no-evidence / model-abstain / unsupported-safety / fabricated-handle tests; live abstain test)
5. Never presented as certified manufacturer instruction. — **[verified]** (`NOT_CERTIFIED_NOTICE` always attached; test)

## Deliverables
- Terraform: `gpt-5.4-mini` chat deployment (DataZoneStandard) + outputs; `.env` wired.
- `ikip_common/llm/base.py` — `ChatClient` port + `ChatMessage`.
- `ikip_common/llm/schemas.py` — `GroundedAnswer`/`Claim`, `GroundingResult`/`ClaimVerdict`.
- `ikip_common/llm/chat_azure.py` — `AzureChatClient` (+ pure `_chat_kwargs`/`_reasoning_model`: per-model temperature/reasoning_effort).
- `ikip_common/llm/grounding.py` — `GroundingValidator` port + `LLMGroundingValidator`.
- `ikip_common/llm/fake_chat.py` — `FakeChatClient`, `FakeGroundingValidator`.
- `ikip_common/llm/answer.py` — LangGraph `StateGraph`, citation resolution, grounding policy, `grounded_answer`, `make_hybrid_retrieve`.
- Config: `azure_openai_chat_deployment`, `chat_reasoning_effort`, `chat_temperature`.
- Tests: `test_answer_graph.py` (8), `test_grounding.py` (2), `test_chat_params.py` (6), `test_answer_live.py` (2 live).

## Concepts
Introduces [grounded-answers](../../concepts/grounded-answers.md). Reuses [hybrid-retrieval](../../concepts/hybrid-retrieval.md), [rag-orchestration](../../concepts/rag-orchestration.md), [embeddings](../../concepts/embeddings.md).
