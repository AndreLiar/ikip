# MISSION-013 — Execution log

Evidence labels: `[verified]` = run with output seen · `[hypothesis]` · `[recommendation]` · `[untested]`. Secrets redacted.

## Step 1 — Provision Azure OpenAI as code (Terraform) — [verified]

**Why:** Story 3.2 needs a real embedding model. We provision it as IaC (reproducible, destroyable) rather than clicking in the Azure AI Foundry portal — see [decisions.md](./decisions.md) D1.

**Environment** — [verified]
- `terraform v1.5.7`, `az CLI 2.76`.
- Account switched to `kanmegnea@gmail.com`, subscription `Azure subscription 1` (`fd0b9d4a-…`, pay-as-you-go). The `ynov.com` student account was blocked by the Talanx tenant's MFA at login.
- `Microsoft.CognitiveServices` provider: `Registered`.

**Files created:** `infrastructure/terraform/environments/dev/{versions,variables,main,outputs}.tf`, `terraform.tfvars.example`, `README.md`. State is local + gitignored (remote backend deferred to Story 6.6).

**Commands** — [verified]
```
terraform init      # azurerm v4.81.0, random v3.9.1
terraform plan      # Plan: 4 to add, 0 to change, 0 to destroy
terraform apply     # FIRST attempt: partial
```

**Error + root cause** — [verified]
First `apply` created the resource group + OpenAI account, then failed on the deployment:
```
400 InvalidResourceProperties: The specified SKU 'Standard' for model
'text-embedding-3-small 1' is not supported in this region 'francecentral'.
```
Root cause: Azure no longer offers the `Standard` SKU for this model. Diagnosed with:
```
az cognitiveservices model list --location francecentral \
  --query "[?model.name=='text-embedding-3-small'].{skus:model.skus[].name}"
# -> ["GlobalStandard","DataZoneStandard"]   (no "Standard")
```
**Fix:** added `embedding_sku` variable, default `DataZoneStandard` (EU data zone — residency posture; see [decisions.md](./decisions.md) D3). Re-applied: `1 added` (only the deployment; account/RG already in state — no destroy/recreate).

**Outputs** — [verified]
```
azure_openai_endpoint             = https://ikip-openai-dev-6p0ptk.openai.azure.com/
azure_openai_embedding_deployment = text-embedding-3-small
azure_openai_account_name         = ikip-openai-dev-6p0ptk
azure_openai_api_key              = <sensitive>
```

## Step 2 — Wire `.env` — [verified]
Filled `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION=2024-10-21`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small` from `terraform output` (key written without printing). `CHAT_DEPLOYMENT` left empty (no chat model yet).

## Step 3 — Live embedding verification — [verified]
Called the deployment directly, requesting **512 dims** (the ADR 0020 Matryoshka reduction):
```
POST .../deployments/text-embedding-3-small/embeddings?api-version=2024-10-21
body: {"input":"Le code defaut E42 …","dimensions":512}
-> HTTP 200 OK | model: text-embedding-3-small | vector dims: 512 | usage: 21 tokens
```
Gotchas hit + fixed:
- `source .env` broke in zsh on a value containing `&` → parse `.env` in Python instead of sourcing it.
- macOS system Python had no CA bundle (`CERTIFICATE_VERIFY_FAILED`) → used `certifi`'s CA bundle for the SSL context (never disabled verification).

## Teardown (reference) — [untested]
```
cd infrastructure/terraform/environments/dev && terraform destroy
```

## Step 4 — Embedding port + adapters — [verified]
**Decision applied (ADR 0021):** reuse LangChain's `AzureOpenAIEmbeddings` *behind* our port, not as the system of record. Files:
- `ikip_common/llm/base.py` — `EmbeddingClient` Protocol (`embed`, `model_version`, `dimensions`) + `Vector` alias.
- `ikip_common/llm/azure.py` — `AzureOpenAIEmbeddingClient` wrapping `AzureOpenAIEmbeddings` (lazy import, config from Settings, `dimensions=512`). Raises `AzureConfigError` if AZURE_OPENAI_* missing.
- `ikip_common/llm/fake.py` — `FakeEmbeddingClient` (deterministic unit vectors from a text hash; no network).
- Deps: root group `embeddings = ["langchain-openai", "langchain-core"]`; `pgvector` added to ikip-common core (Vector type in models).

## Step 5 — Embedding model + migration — [verified]
- `ikip_common/db/models.py` — `Embedding(UUIDPrimaryKey, TenantScoped, Timestamped)`: `chunk_id` FK, `model_version`, `vector = Vector(512)`, unique `(chunk_id, model_version)`.
- Migration `1aa8f27570e7_add_embedding.py` — hand-written: `CREATE EXTENSION IF NOT EXISTS vector` + `embedding` table + indexes. Offline SQL render verified **both directions** (upgrade creates `VECTOR(512)` + unique constraint; downgrade drops cleanly — no enum types, so no enum-trap). — [verified]

## Step 6 — Store service — [verified]
`ikip_common/db/embeddings.py` — `EmbeddingRepository` (tenant-scoped) + `embed_and_store` (idempotent: skips existing `(chunk, model_version)`; additive: a new version writes new rows, never deletes — FR14) + `vectors_for_chunk`.

## Step 7 — Tests + gate — [verified]
```
uv run pytest packages/common/tests/test_embeddings_fake.py   # 7 passed (pure)
SSL_CERT_FILE=$(certifi) uv run pytest .../test_embeddings_azure_live.py  # 2 passed (real Azure, 512-dim)
uv run pytest packages/common/tests -q   # 21 passed, 21 skipped (DB gated on TEST_DATABASE_URL)
uv run ruff check packages/common        # All checks passed
uv run ruff format --check packages/common  # 36 files already formatted
```
- Pure (CI): `test_embeddings_fake.py` — determinism, dims, order, model_version tag.
- DB-gated (CI ephemeral Neon branch): `test_embedding_store.py` — persistence, idempotent re-embed, **additive version coexistence** (FR14), **tenant isolation** (NFR10), **citation chain** embedding→chunk→section→document_version (FR16).
- Live (local/integration): `test_embeddings_azure_live.py` — 512-dim via the real adapter; skipped unless AZURE_OPENAI_* set.

**Gotcha (local):** macOS system/venv Python lacked a CA bundle → `CERTIFICATE_VERIFY_FAILED` on the live Azure call. Fix: `SSL_CERT_FILE=$(python -c 'import certifi;print(certifi.where())')`. Not needed in Linux CI.

**Local DB caveat:** no Docker/neonctl/Neon token locally → DB tests not executed on this machine; migration verified via offline SQL render, DB tests run in CI (ephemeral Neon branch). Optional: create an ephemeral Neon branch and set TEST_DATABASE_URL for a live local run.
