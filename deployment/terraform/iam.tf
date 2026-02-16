# ------------------------------------------------------------------
# CICD runner SA roles in the CICD project
# ------------------------------------------------------------------
resource "google_project_iam_member" "cicd_runner_sa_cicd_project_roles" {
  count = length(var.cicd_roles)

  project = var.cicd_runner_project_id
  role    = var.cicd_roles[count.index]
  member  = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}

# ------------------------------------------------------------------
# CICD runner SA roles in deployment projects (staging & prod)
# ------------------------------------------------------------------
locals {
  cicd_sa_deploy_role_pairs = toset([
    for pair in setproduct(keys(local.deploy_project_ids), var.cicd_sa_deployment_required_roles) :
    "${pair[0]}:${pair[1]}"
  ])
}

resource "google_project_iam_member" "cicd_runner_sa_deploy_project_roles" {
  for_each = local.cicd_sa_deploy_role_pairs

  project = local.deploy_project_ids[split(":", each.key)[0]]
  role    = split(":", each.key)[1]
  member  = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}

# ------------------------------------------------------------------
# Pipeline SA roles in deployment projects
# ------------------------------------------------------------------
locals {
  pipeline_sa_role_pairs = toset([
    for pair in setproduct(keys(local.deploy_project_ids), var.pipelines_roles) :
    "${pair[0]}:${pair[1]}"
  ])
}

resource "google_project_iam_member" "pipeline_sa_roles" {
  for_each = local.pipeline_sa_role_pairs

  project = local.deploy_project_ids[split(":", each.key)[0]]
  role    = split(":", each.key)[1]
  member  = "serviceAccount:${google_service_account.pipeline_sa[split(":", each.key)[0]].email}"
}

# ------------------------------------------------------------------
# Allow CICD runner SA to create tokens for pipeline SAs
# ------------------------------------------------------------------
resource "google_service_account_iam_member" "cicd_runner_token_creator" {
  for_each = google_service_account.pipeline_sa

  service_account_id = each.value.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}

resource "google_service_account_iam_member" "cicd_runner_account_user" {
  for_each = google_service_account.pipeline_sa

  service_account_id = each.value.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.cicd_runner_sa.email}"
}
