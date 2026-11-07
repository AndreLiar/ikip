# IKIP dev — Azure OpenAI for embeddings (Story 3.2).
#
# Creates the SAME underlying resource the Azure AI Foundry portal would create
# (a Microsoft.CognitiveServices account, kind="OpenAI") + an embedding model
# deployment — but declaratively, so it is reproducible, reviewable and
# destroyable (terraform destroy). This is why we use IaC over portal click-ops.

# Globally-unique suffix: the OpenAI account's custom subdomain (which forms the
# public endpoint https://<name>.openai.azure.com) must be unique across Azure.
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
  numeric = true
}

resource "azurerm_resource_group" "this" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_cognitive_account" "openai" {
  name                = "${var.openai_account_name}-${random_string.suffix.result}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  kind                = "OpenAI"
  sku_name            = "S0" # pay-per-token; no fixed hourly charge

  # Required for a stable https://<subdomain>.openai.azure.com endpoint and for
  # token-based (Entra ID) auth in addition to key auth.
  custom_subdomain_name = "${var.openai_account_name}-${random_string.suffix.result}"

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model
    version = var.embedding_model_version
  }

  sku {
    name     = var.embedding_sku
    capacity = var.embedding_capacity
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.chat_model
    version = var.chat_model_version
  }

  sku {
    name     = var.chat_sku
    capacity = var.chat_capacity
  }

  # Azure serializes deployment creation on one account; depend on the embedding
  # deployment so `apply` creates them one after the other (avoids a transient conflict).
  depends_on = [azurerm_cognitive_deployment.embedding]
}
