# ------------------------------------------------------------------
# Artifact Registry Repository (Docker) in CICD project
# ------------------------------------------------------------------

resource "google_artifact_registry_repository" "docker_repo" {
  project       = var.cicd_runner_project_id
  location      = var.region
  repository_id = "${var.project_name}-docker"
  description   = "Docker repository for ${var.project_name} pipeline components"
  format        = "DOCKER"

  depends_on = [google_project_service.cicd_services]
}

# ------------------------------------------------------------------
# Grant Vertex AI Service Agents read access to Docker repo
# (Staging/Prod Vertex AI needs to pull images from CICD AR repo)
# ------------------------------------------------------------------

data "google_project" "deploy_projects" {
  for_each   = local.deploy_project_ids
  project_id = each.value
}

resource "google_artifact_registry_repository_iam_member" "vertex_ai_reader" {
  for_each = local.deploy_project_ids

  project    = var.cicd_runner_project_id
  location   = var.region
  repository = google_artifact_registry_repository.docker_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:service-${data.google_project.deploy_projects[each.key].number}@gcp-sa-aiplatform-cc.iam.gserviceaccount.com"
}

# ------------------------------------------------------------------
# Pipeline Root GCS Buckets (one per deployment project)
# ------------------------------------------------------------------

resource "google_storage_bucket" "pipeline_root" {
  for_each = local.deploy_project_ids

  project                     = each.value
  name                        = "${each.value}-${var.project_name}-pipeline-root"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  depends_on = [google_project_service.deploy_project_services]
}

# ------------------------------------------------------------------
# Model Artifacts GCS Buckets (one per deployment project)
# ------------------------------------------------------------------

resource "google_storage_bucket" "model_artifacts" {
  for_each = local.deploy_project_ids

  project                     = each.value
  name                        = "${each.value}-${var.project_name}-artifacts"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  depends_on = [google_project_service.deploy_project_services]
}

# ------------------------------------------------------------------
# BigQuery Datasets (one per deployment project)
# ------------------------------------------------------------------

resource "google_bigquery_dataset" "fraud_detection" {
  for_each = local.deploy_project_ids

  project    = each.value
  dataset_id = "fraud_detection"
  location   = var.region

  description = "Fraud detection dataset for ${each.key} environment"

  depends_on = [google_project_service.deploy_project_services]
}
