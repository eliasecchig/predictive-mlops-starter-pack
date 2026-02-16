# ------------------------------------------------------------------
# Workload Identity Federation for GitHub Actions
# ------------------------------------------------------------------

data "google_project" "cicd_project" {
  project_id = var.cicd_runner_project_id
}

# WIF Pool
resource "google_iam_workload_identity_pool" "github_pool" {
  project                   = var.cicd_runner_project_id
  workload_identity_pool_id = "${var.project_name}-pool"
  display_name              = "${var.project_name} GHA Pool"
  description               = "Workload Identity Pool for GitHub Actions"
}

# WIF OIDC Provider
resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.cicd_runner_project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Actions Provider"
  description                        = "OIDC provider for GitHub Actions"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
  }

  attribute_condition = "assertion.repository == '${var.repository_owner}/${var.repository_name}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions to impersonate the CICD runner SA
resource "google_service_account_iam_member" "wif_sa_binding" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.repository_owner}/${var.repository_name}"
}

# Allow GitHub Actions to create tokens for the CICD runner SA
resource "google_service_account_iam_member" "wif_token_creator" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/${var.repository_owner}/${var.repository_name}"
}
