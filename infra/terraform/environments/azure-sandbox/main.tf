terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "azurerm" {
  features {}

  # Point all ARM API calls at the local floci-az emulator
  # Azurite-compatible credentials are used automatically
  subscription_id            = "00000000-0000-0000-0000-000000000000"
  tenant_id                  = "00000000-0000-0000-0000-000000000000"
  skip_provider_registration = true

  # floci-az endpoint override
  use_cli = false
}

resource "azurerm_resource_group" "sandbox" {
  name     = "${var.project}-sandbox-rg"
  location = var.location
}

resource "azurerm_storage_account" "app" {
  name                     = "${replace(var.project, "-", "")}sandbox"
  resource_group_name      = azurerm_resource_group.sandbox.name
  location                 = azurerm_resource_group.sandbox.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "snapshots" {
  name                  = "contract-snapshots"
  storage_account_id    = azurerm_storage_account.app.id
  container_access_type = "private"
}

resource "azurerm_storage_container" "archives" {
  name                  = "observation-archives"
  storage_account_id    = azurerm_storage_account.app.id
  container_access_type = "private"
}

resource "azurerm_storage_queue" "drift_events" {
  name                 = "drift-events"
  storage_account_name = azurerm_storage_account.app.name
}

resource "azurerm_storage_queue" "probe_results" {
  name                 = "probe-results"
  storage_account_name = azurerm_storage_account.app.name
}
