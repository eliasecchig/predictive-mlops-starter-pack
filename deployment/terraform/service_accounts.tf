# CICD runner service account in the CICD project
resource "google_service_account" "cicd_runner_sa" {
  project      = var.cicd_runner_project_id
  account_id   = "${var.project_name}-cicd-runner"
  display_name = "${var.project_name} CICD Runner Service Account"
  description  = "Service account used by GitHub Actions for CI/CD pipelines"
}

# Pipeline service accounts in each deployment project
resource "google_service_account" "pipeline_sa" {
  for_each = local.deploy_project_ids

  project      = each.value
  account_id   = "${var.project_name}-pipelines"
  display_name = "${var.project_name} Pipeline Service Account (${each.key})"
  description  = "Service account used by Vertex AI pipelines in ${each.key}"
}
