terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.13.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7.0"
    }
  }
}

# Default provider - CICD runner project
provider "google" {
  project = var.cicd_runner_project_id
  region  = var.region
}

# Provider for staging project
provider "google" {
  alias   = "staging"
  project = var.staging_project_id
  region  = var.region
}

# Provider for prod project
provider "google" {
  alias   = "prod"
  project = var.prod_project_id
  region  = var.region
}

# Provider for staging with billing override
provider "google" {
  alias                 = "staging_billing"
  project               = var.staging_project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.staging_project_id
}

# Provider for prod with billing override
provider "google" {
  alias                 = "prod_billing"
  project               = var.prod_project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.prod_project_id
}
