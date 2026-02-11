# ------------------------------------------------------------------
# Dev Pipeline Service Account
# ------------------------------------------------------------------

resource "google_service_account" "dev_pipeline_sa" {
  project      = var.dev_project_id
  account_id   = "${var.project_name}-pipelines"
  display_name = "${var.project_name} Pipeline Service Account (dev)"
  description  = "Service account used by Vertex AI pipelines in dev"
}

# ------------------------------------------------------------------
# Dev Pipeline SA Roles
# ------------------------------------------------------------------

resource "google_project_iam_member" "dev_pipeline_sa_roles" {
  count = length(var.pipelines_roles)

  project = var.dev_project_id
  role    = var.pipelines_roles[count.index]
  member  = "serviceAccount:${google_service_account.dev_pipeline_sa.email}"
}

# ------------------------------------------------------------------
# Dev App SA Roles
# ------------------------------------------------------------------

resource "google_project_iam_member" "dev_app_sa_roles" {
  count = length(var.app_sa_roles)

  project = var.dev_project_id
  role    = var.app_sa_roles[count.index]
  member  = "serviceAccount:${google_service_account.dev_pipeline_sa.email}"
}
