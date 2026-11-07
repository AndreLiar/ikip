# MISSION-013 — Reproduction tutorial

Reproduce from a clean checkout: provision Azure OpenAI as code, then generate and
store embeddings behind our port. See concepts [embeddings](../../concepts/embeddings.md)
and [rag-orchestration](../../concepts/rag-orchestration.md); decisions [ADR 0020](../../../adr/0020-embedding-model-text-embedding-3-small.md), [ADR 0021](../../../adr/0021-framework-boundary-langchain-langgraph-vs-data-plane.md).

## Prerequisites
- `terraform >= 1.5`, `az` CLI, an Azure subscription (pay-as-you-go or student).
- `uv`, Python 3.12. A Postgres with pgvector for DB tests (Neon branch or local).

## Part A — Provision Azure OpenAI (Terraform)
```bash
az login                                   # interactive; pick the right account
az account show --query id -o tsv          # note the subscription id

cd infrastructure/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars   # set subscription_id
terraform init
terraform plan                                 # expect: 4 to add
terraform apply                                # creates RG + OpenAI account + deployment
```
**Expected:** outputs `azure_openai_endpoint`, `azure_openai_embedding_deployment`.
**Common mistake:** `400 ... SKU 'Standard' ... not supported` — `text-embedding-3-small`
only offers `GlobalStandard` / `DataZoneStandard`. We default to `DataZoneStandard`
(EU). Diagnose region/SKU with:
```bash
az cognitiveservices model list --location francecentral \
  --query "[?model.name=='text-embedding-3-small'].model.skus[].name"
```

### Wire .env
```bash
terraform output -raw azure_openai_endpoint              # -> AZURE_OPENAI_ENDPOINT
terraform output -raw azure_openai_embedding_deployment  # -> AZURE_OPENAI_EMBEDDING_DEPLOYMENT
terraform output -raw azure_openai_api_key               # -> AZURE_OPENAI_API_KEY
# AZURE_OPENAI_API_VERSION=2024-10-21 ; EMBEDDING_DIMENSIONS=512
```

## Part B — Install + run
```bash
uv sync --group embeddings                 # pulls pgvector (core) + langchain-openai
```

### Pure tests (no network, no DB)
```bash
uv run pytest packages/common/tests/test_embeddings_fake.py -q   # 7 passed
```

### Live Azure test (real embeddings)
```bash
SSL_CERT_FILE=$(uv run python -c "import certifi; print(certifi.where())") \
  uv run pytest packages/common/tests/test_embeddings_azure_live.py -q   # 2 passed
```
**Common mistake:** `CERTIFICATE_VERIFY_FAILED` on macOS → set `SSL_CERT_FILE` as above.

### Migration (reversibility check, no DB needed)
```bash
cd packages/common
uv run alembic upgrade 2e6989484fa8:1aa8f27570e7 --sql     # renders CREATE EXTENSION + table
uv run alembic downgrade 1aa8f27570e7:2e6989484fa8 --sql   # renders clean DROP
```

### DB tests (pgvector) — against an isolated DB only
```bash
export TEST_DATABASE_URL="postgresql://…ephemeral-neon-branch…/db"
cd packages/common && uv run alembic upgrade head          # applies the embedding migration
uv run pytest packages/common/tests/test_embedding_store.py -q   # 5 passed
```
> ⚠️ The fixtures `create_all`/`drop_all` — point TEST_DATABASE_URL at a **throwaway**
> branch/DB, never the shared dev branch. In CI an ephemeral Neon branch is created
> and deleted per run.

## Verify the whole slice
```bash
uv run pytest packages/common/tests -q         # 21 passed, 21 skipped (DB) without TEST_DATABASE_URL
uv run ruff check packages/common && uv run ruff format --check packages/common
```

## Teardown
```bash
cd infrastructure/terraform/environments/dev && terraform destroy
```

## Troubleshooting
- **`AzureConfigError: missing AZURE_OPENAI_*`** → `.env` not filled from `terraform output`.
- **pgvector `type "vector" does not exist`** → the migration/fixture didn't run `CREATE EXTENSION vector` (or you bypassed alembic). Run `alembic upgrade head`.
- **Dimension mismatch on insert** → the client's `dimensions` must equal the column `vector(512)`; a fake client must use `dimensions=512`.
