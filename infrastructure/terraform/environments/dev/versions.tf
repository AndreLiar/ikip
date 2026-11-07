# Terraform + provider pinning (dev environment).
# First real IaC slice of the project (Story 3.2 prerequisite; opens Story 6.6).
# State is local for now (gitignored); remote state (Azure Storage backend) is a
# Story 6.6 hardening step — intentionally deferred to keep this slice simple.

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  # Auth comes from `az login` (Azure CLI). No credentials in code.
  subscription_id = var.subscription_id
  features {}
}
