terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~>3.100.0"
    }
    random = {
      source = "hashicorp/random"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
}

variable "ghcr_token" {
  type      = string
  sensitive = true
}

resource "random_integer" "suffix" {
  min = 1000
  max = 9999
}

resource "azurerm_resource_group" "rg" {
  name     = "flask-free-rg-${random_integer.suffix.result}"
  location = "Central India"
}


resource "azurerm_service_plan" "plan" {
  name                = "flask-free-plan"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "F1"
}

resource "azurerm_linux_web_app" "app" {
  name                = "flask-free-webapp-${random_integer.suffix.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id

  site_config {
    always_on = false

    application_stack {
      docker_image      = "ghcr.io/220701171/flask-app"
      docker_image_tag  = "latest"
    }
  }

  app_settings = {
    WEBSITES_PORT                 = "5000"
    DOCKER_REGISTRY_SERVER_URL    = "https://ghcr.io"
    DOCKER_REGISTRY_SERVER_USERNAME = "220701171"
    DOCKER_REGISTRY_SERVER_PASSWORD = var.ghcr_token
  }

  identity {
    type = "SystemAssigned"
  }
}

output "webapp_url" {
  value = azurerm_linux_web_app.app.default_hostname
}

