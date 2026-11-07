# Terraform — dev environment (Azure OpenAI for embeddings)

First real Infrastructure-as-Code slice of IKIP. Provisions, in `Azure subscription 1`:

- a resource group (`rg-ikip-dev`),
- an **Azure OpenAI** account (`Microsoft.CognitiveServices`, kind `OpenAI`) — the same
  resource the Azure AI Foundry portal would create, but declaratively ([ADR 0006](../../../../docs/adr/0006-monorepo.md) IaC, [ADR 0007](../../../../docs/adr/0007-pluggable-llm-client-azure-openai.md)),
- a **`text-embedding-3-small`** deployment ([ADR 0020](../../../../docs/adr/0020-embedding-model-text-embedding-3-small.md)).

State is **local** and gitignored; a remote backend (Azure Storage) is a Story 6.6 hardening step.

## Prerequisites
- `terraform >= 1.5`, `az` CLI, and `az login` into the target account.
- Subscription id: `az account show --query id -o tsv`.

## Usage
```bash
cd infrastructure/terraform/environments/dev
cp terraform.tfvars.example terraform.tfvars   # then set subscription_id
terraform init
terraform plan
terraform apply        # creates real Azure resources (pay-per-token; ~$0 idle)
```

## Wiring the app (.env)
After `apply`:
```bash
terraform output -raw azure_openai_endpoint               # -> AZURE_OPENAI_ENDPOINT
terraform output -raw azure_openai_embedding_deployment   # -> AZURE_OPENAI_EMBEDDING_DEPLOYMENT
terraform output -raw azure_openai_api_key                # -> AZURE_OPENAI_API_KEY (sensitive)
```
`AZURE_OPENAI_API_VERSION` is set in `.env` (e.g. a current GA version), not by Terraform.

## Teardown
```bash
terraform destroy      # removes the account + deployment + resource group
```

## Cost
`S0` has no fixed hourly charge; you pay per embedded token (`text-embedding-3-small` ≈ $0.02/1M).
This gmail subscription is pay-as-you-go (no student credit) — see
`docs/runbooks/dev-on-azure-cost-control.md`.
