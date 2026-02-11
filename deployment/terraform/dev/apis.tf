locals {
  dev_services = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "logging.googleapis.com",
  ]
}

resource "google_project_service" "dev_services" {
  count = length(local.dev_services)

  project            = var.dev_project_id
  service            = local.dev_services[count.index]
  disable_on_destroy = false
}
