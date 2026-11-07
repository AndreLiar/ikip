# Outputs feed the app's .env (AZURE_OPENAI_*). The key is sensitive and is read
# via `terraform output -raw azure_openai_api_key` — never printed in plan/apply.

output "azure_openai_endpoint" {
  description = "AZURE_OPENAI_ENDPOINT"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "azure_openai_embedding_deployment" {
  description = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
  value       = azurerm_cognitive_deployment.embedding.name
}

output "azure_openai_account_name" {
  description = "The provisioned account name (with unique suffix)."
  value       = azurerm_cognitive_account.openai.name
}

output "azure_openai_api_key" {
  description = "AZURE_OPENAI_API_KEY (sensitive)."
  value       = azurerm_cognitive_account.openai.primary_access_key
  sensitive   = true
}
