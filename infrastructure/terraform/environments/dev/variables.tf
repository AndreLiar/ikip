# Inputs for the dev Azure OpenAI stack. Defaults are sensible for a solo dev
# environment; override in terraform.tfvars (gitignored) if needed.

variable "subscription_id" {
  description = "Azure subscription to deploy into (the pay-as-you-go 'Azure subscription 1')."
  type        = string
}

variable "location" {
  description = "Azure region. France Central keeps data in the EU (NFR) and hosts text-embedding-3-small. Fallback: swedencentral."
  type        = string
  default     = "francecentral"
}

variable "resource_group_name" {
  description = "Resource group holding all IKIP dev infra."
  type        = string
  default     = "rg-ikip-dev"
}

variable "openai_account_name" {
  description = "Azure OpenAI account name. A random suffix is appended because the custom subdomain must be globally unique."
  type        = string
  default     = "ikip-openai-dev"
}

variable "embedding_model" {
  description = "Embedding model to deploy. 3-small supports dimension reduction -> fits Neon (ADR 0015)."
  type        = string
  default     = "text-embedding-3-small"
}

variable "embedding_model_version" {
  description = "Model version string on Azure for the embedding model."
  type        = string
  default     = "1"
}

variable "embedding_deployment_name" {
  description = "Deployment name the app calls (goes into AZURE_OPENAI_EMBEDDING_DEPLOYMENT)."
  type        = string
  default     = "text-embedding-3-small"
}

variable "embedding_capacity" {
  description = "Deployment throughput in thousands of tokens/min (TPM). 30 = 30k TPM, ample for dev ingestion."
  type        = number
  default     = 30
}

variable "embedding_sku" {
  description = "Deployment SKU. text-embedding-3-small offers GlobalStandard (routes worldwide, cheapest) or DataZoneStandard (processing confined to the EU data zone). We default to DataZoneStandard for EU residency (ADR 0015). 'Standard' is NOT offered for this model."
  type        = string
  default     = "DataZoneStandard"
}

variable "tags" {
  description = "Tags applied to all resources (cost tracking / cleanup)."
  type        = map(string)
  default = {
    project     = "ikip"
    environment = "dev"
    managed_by  = "terraform"
  }
}
