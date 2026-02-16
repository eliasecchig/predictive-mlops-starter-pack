# ------------------------------------------------------------------
# GitHub Provider Configuration
# ------------------------------------------------------------------

provider "github" {
  owner = var.repository_owner
}

# ------------------------------------------------------------------
# Optional Repository Creation
# ------------------------------------------------------------------

resource "github_repository" "repo" {
  count = var.create_repository ? 1 : 0

  name        = var.repository_name
  description = "Predictive MLOps Demo - Fraud Detection Pipeline"
  visibility  = "private"

  has_issues   = true
  has_projects = false
  has_wiki     = false

  auto_init = true
}

# ------------------------------------------------------------------
# Data source for existing repository
# ------------------------------------------------------------------

data "github_repository" "repo" {
  count = var.create_repository ? 0 : 1

  full_name = "${var.repository_owner}/${var.repository_name}"
}

locals {
  repository_name = var.create_repository ? github_repository.repo[0].name : data.github_repository.repo[0].name
}

# ------------------------------------------------------------------
# GitHub Actions Variables — GCP Project
# ------------------------------------------------------------------

resource "github_actions_variable" "gcp_project_number" {
  repository    = local.repository_name
  variable_name = "GCP_PROJECT_NUMBER"
  value         = data.google_project.cicd_project.number
}

# ------------------------------------------------------------------
# GitHub Actions Secrets
# ------------------------------------------------------------------

resource "github_actions_secret" "wif_pool_id" {
  repository      = local.repository_name
  secret_name     = "WIF_POOL_ID"
  plaintext_value = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
}

resource "github_actions_secret" "wif_provider_id" {
  repository      = local.repository_name
  secret_name     = "WIF_PROVIDER_ID"
  plaintext_value = google_iam_workload_identity_pool_provider.github_provider.workload_identity_pool_provider_id
}

resource "github_actions_secret" "gcp_service_account" {
  repository      = local.repository_name
  secret_name     = "GCP_SERVICE_ACCOUNT"
  plaintext_value = google_service_account.cicd_runner_sa.email
}

# ------------------------------------------------------------------
# GitHub Actions Variables
# ------------------------------------------------------------------

resource "github_actions_variable" "staging_project_id" {
  repository    = local.repository_name
  variable_name = "STAGING_PROJECT_ID"
  value         = var.staging_project_id
}

resource "github_actions_variable" "prod_project_id" {
  repository    = local.repository_name
  variable_name = "PROD_PROJECT_ID"
  value         = var.prod_project_id
}

resource "github_actions_variable" "region" {
  repository    = local.repository_name
  variable_name = "REGION"
  value         = var.region
}

resource "github_actions_variable" "cicd_project_id" {
  repository    = local.repository_name
  variable_name = "CICD_PROJECT_ID"
  value         = var.cicd_runner_project_id
}

resource "github_actions_variable" "pipeline_sa_email_staging" {
  repository    = local.repository_name
  variable_name = "PIPELINE_SA_EMAIL_STAGING"
  value         = google_service_account.pipeline_sa["staging"].email
}

resource "github_actions_variable" "pipeline_sa_email_prod" {
  repository    = local.repository_name
  variable_name = "PIPELINE_SA_EMAIL_PROD"
  value         = google_service_account.pipeline_sa["prod"].email
}

resource "github_actions_variable" "artifact_registry_repo_name" {
  repository    = local.repository_name
  variable_name = "ARTIFACT_REGISTRY_REPO_NAME"
  value         = google_artifact_registry_repository.docker_repo.name
}

resource "github_actions_variable" "pipeline_gcs_root_staging" {
  repository    = local.repository_name
  variable_name = "PIPELINE_GCS_ROOT_STAGING"
  value         = "gs://${google_storage_bucket.pipeline_root["staging"].name}"
}

resource "github_actions_variable" "pipeline_gcs_root_prod" {
  repository    = local.repository_name
  variable_name = "PIPELINE_GCS_ROOT_PROD"
  value         = "gs://${google_storage_bucket.pipeline_root["prod"].name}"
}

# ------------------------------------------------------------------
# GitHub Production Environment with Branch Policy
# ------------------------------------------------------------------

resource "github_repository_environment" "production" {
  environment = "production"
  repository  = local.repository_name

  deployment_branch_policy {
    protected_branches     = true
    custom_branch_policies = false
  }
}
