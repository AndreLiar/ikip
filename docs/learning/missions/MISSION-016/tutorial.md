# MISSION-016 — Reproduction tutorial

Build + run the grounded-answer service. Concept: [grounded-answers](../../concepts/grounded-answers.md);
decision [ADR 0022](../../../adr/0022-grounded-answer-langgraph-gpt5-mini.md).

## Prerequisites
- Stories 3.2–3.4 done. `uv sync --group embeddings` (pulls langchain + langgraph).
- Azure chat deployment provisioned (Part A).

## Part A — Provision the chat model (Terraform)
```bash
# verify availability on YOUR subscription first
az cognitiveservices model list --location francecentral \
  --query "[?model.name=='gpt-5.4-mini'].{v:model.version, skus:model.skus[].name}"

cd infrastructure/terraform/environments/dev
terraform plan      # expect: 1 to add (chat deployment)
terraform apply
terraform output -raw azure_openai_chat_deployment   # -> AZURE_OPENAI_CHAT_DEPLOYMENT in .env
```

## Part B — Use it (Python)
```python
from ikip_common.llm import build_chat_client, build_embedding_client
from ikip_common.llm.answer import grounded_answer, make_hybrid_retrieve

retrieve = make_hybrid_retrieve(session, tenant_id, build_embedding_client())
out = grounded_answer("What does fault E42 mean?", retrieve=retrieve, chat_client=build_chat_client())

if out.status == "abstained":
    print("abstained:", out.abstention_reason)
else:
    print(out.answer)                       # claims with [E#] markers
    for c in out.claims:
        for cit in c.citations:             # resolved server-side (FR16)
            print(cit.marker, cit.revision, cit.hierarchy_path, cit.page_start)
    print(out.warnings)
print(out.not_certified_notice)             # always present (AC5)
```

## Part C — Test without network (fakes)
```python
from ikip_common.llm import FakeChatClient, FakeGroundingValidator, GroundedAnswer, Claim
from ikip_common.llm.hybrid import RetrievalOutcome
from ikip_common.llm.answer import grounded_answer
from langchain_core.documents import Document

doc = Document(page_content="Fault E42: pump motor overheat.",
               metadata={"chunk_id": "c1", "revision": "A", "hierarchy_path": "3.2", "page_start": 142})
chat = FakeChatClient(GroundedAnswer(status="answered",
        claims=[Claim(text="E42 = overheat", evidence_markers=["E1"])]))
out = grounded_answer("E42?", retrieve=lambda q: RetrievalOutcome(documents=[doc], abstained=False),
                      chat_client=chat, validator=FakeGroundingValidator())
assert out.status == "answered"
```

## Part D — Run the suites
```bash
uv run pytest packages/common/tests/test_answer_graph.py \
              packages/common/tests/test_grounding.py \
              packages/common/tests/test_chat_params.py -q         # pure, no network
SSL_CERT_FILE=$(uv run python -c "import certifi;print(certifi.where())") \
  uv run pytest packages/common/tests/test_answer_live.py -q        # real gpt-5.4-mini
uv run ruff check packages/common && uv run ruff format --check packages/common
```

## Common mistakes
- **`temperature does not support 0.0 with this model`** → gpt-5.4-mini is a reasoning model;
  don't set `CHAT_TEMPERATURE` (use `CHAT_REASONING_EFFORT`). Only the gpt-4.1-mini fallback takes temperature.
- **`CERTIFICATE_VERIFY_FAILED` (macOS)** → `SSL_CERT_FILE=$(python -c 'import certifi;print(certifi.where())')`.
- **Model citing a handle you didn't provide** → treated as unsupported by design (fabrication guard).
- **Import error on `answer`/`hybrid` in CI** → they need the `embeddings` group (langchain/langgraph); tests `importorskip`.
