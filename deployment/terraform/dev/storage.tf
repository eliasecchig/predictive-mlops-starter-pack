# ------------------------------------------------------------------
# Dev Pipeline Root GCS Bucket
# ------------------------------------------------------------------

resource "google_storage_bucket" "pipeline_root" {
  project                     = var.dev_project_id
  name                        = "${var.dev_project_id}-${var.project_name}-pipeline-root"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  depends_on = [google_project_service.dev_services]
}

# ------------------------------------------------------------------
# Dev Model Artifacts GCS Bucket
# ------------------------------------------------------------------

resource "google_storage_bucket" "model_artifacts" {
  project                     = var.dev_project_id
  name                        = "${var.dev_project_id}-${var.project_name}-artifacts"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  depends_on = [google_project_service.dev_services]
}

# ------------------------------------------------------------------
# Dev Artifact Registry (Docker)
# ------------------------------------------------------------------

resource "google_artifact_registry_repository" "docker" {
  project       = var.dev_project_id
  location      = var.region
  repository_id = "${var.project_name}-docker"
  format        = "DOCKER"
  description   = "Docker images for fraud detector pipelines"

  depends_on = [google_project_service.dev_services]
}

# ------------------------------------------------------------------
# Dev BigQuery Dataset
# ------------------------------------------------------------------

resource "google_bigquery_dataset" "fraud_detection" {
  project    = var.dev_project_id
  dataset_id = "fraud_detection"
  location   = var.region

  description = "Fraud detection dataset for dev environment"

  depends_on = [google_project_service.dev_services]
}
