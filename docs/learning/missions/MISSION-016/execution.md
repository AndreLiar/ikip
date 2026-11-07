# MISSION-016 — Execution log

Evidence labels: `[verified]` run with output · `[untested]`. Secrets redacted.

## Step 1 — Provision gpt-5.4-mini (Terraform) — [verified]
Verified availability first (authoritative on our subscription):
```
az cognitiveservices model list --location francecentral --query "[?model.name=='gpt-5.4-mini']"
# GA, skus incl DataZoneStandard, version 2026-03-17   (fallback gpt-4.1-mini also present)
```
Added chat vars + `azurerm_cognitive_deployment.chat` (depends_on embedding to serialize) + output.
`terraform apply` → `1 added` (account/embedding untouched). `.env` AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.4-mini.

## Step 2 — Ports + schemas + fakes — [verified]
- `base.py`: `ChatMessage`, `ChatClient` (complete_structured → typed pydantic).
- `schemas.py`: `GroundedAnswer`/`Claim` (evidence_markers, safety_critical), `GroundingResult`/`ClaimVerdict`.
- `grounding.py`: `GroundingValidator` port + `LLMGroundingValidator` (batched judge).
- `chat_azure.py`: `AzureChatClient` + pure `_chat_kwargs`/`_reasoning_model`.
- `fake_chat.py`: `FakeChatClient`, `FakeGroundingValidator` (scripted, deterministic).

## Step 3 — LangGraph graph — [verified]
`answer.py`: `StateGraph` analyze→retrieve→generate→validate(→END)/abstain, with conditional
edges (sufficient? / model-abstained?). Server-side citation resolution (`_citation_from_doc`),
grounding policy (`_apply_grounding_policy`), `NOT_CERTIFIED_NOTICE`, `grounded_answer`,
`make_hybrid_retrieve`. `RetrievalOutcome` imported from `llm.hybrid` (db layer stays langchain-free).

## Step 4 — Option B: per-model params — [verified]
`_chat_kwargs`: reasoning model → `reasoning_effort`, reject explicit temperature (AzureConfigError);
non-reasoning → `temperature` if set, no reasoning_effort. `chat_temperature` optional in config.

## Step 5 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_answer_graph.py test_grounding.py test_chat_params.py -q
# 8 + 2 + 6 pass
uv run pytest packages/common/tests -q                # 52 passed, 27 skipped (DB/live gated)
SSL_CERT_FILE=$(certifi) uv run pytest .../test_answer_live.py .../test_embeddings_azure_live.py -q
# 4 passed (real gpt-5.4-mini: grounded answer + abstain; embeddings 512)
uv run ruff check / format --check packages/common    # OK
```
Scenarios covered (fakes, deterministic): happy path w/ server-resolved citation; no-evidence
abstain (no LLM call); model abstention; unsupported safety-critical ⇒ abstain; unsupported
non-critical ⇒ drop+warn; fabricated handle ⇒ unsupported; injected instruction contained;
partial ⇒ warning; not-certified notice always present.

**Pitfalls hit:**
- `temperature=0` 400s on gpt-5.4-mini ("only default (1) supported") → option B: send temperature
  only for non-reasoning models; reasoning uses reasoning_effort. Fixed + covered by tests.
- `RetrievalOutcome` lives in `llm.hybrid` (holds langchain Documents), not `db.retrieval` → import fix.
- Heavy modules (`answer`, `hybrid`, `retriever`) import langchain/langgraph at top → kept OUT of
  `ikip_common.llm.__init__` so the fast CI `validate` job (no `embeddings` group) still imports the package.

## Baseline
57 green preserved; net suite now 52 passed + 27 skipped (pure/CI) and 4 live locally.
