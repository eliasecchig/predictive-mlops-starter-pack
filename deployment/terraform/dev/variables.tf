variable "dev_project_id" {
  description = "The GCP project ID for the development environment"
  type        = string
}

variable "region" {
  description = "The GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "project_name" {
  description = "The name of the project"
  type        = string
  default     = "fraud-detector"
}

variable "app_sa_roles" {
  description = "Roles to assign to the dev application service account"
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageConsumer",
  ]
}

variable "pipelines_roles" {
  description = "Roles to assign to the dev pipeline service account"
  type        = list(string)
  default = [
    "roles/storage.admin",
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/bigquery.readSessionUser",
    "roles/artifactregistry.writer",
  ]
}
