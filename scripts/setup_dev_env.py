"""Set up dev environment infrastructure using gcloud CLI.

Creates all GCP resources needed to run pipelines locally and on Vertex AI,
without requiring Terraform.

Resources created:
  - APIs enabled (Vertex AI, BigQuery, Artifact Registry, etc.)
  - Artifact Registry Docker repository
  - GCS buckets (pipeline root, model artifacts)
  - BigQuery dataset
  - Pipeline service account with IAM roles
"""

import argparse
import logging
import os
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

PROJECT_NAME = "fraud-detector"

APIS = [
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "logging.googleapis.com",
]

PIPELINE_SA_ROLES = [
    "roles/storage.admin",
    "roles/aiplatform.user",
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/bigquery.readSessionUser",
    "roles/artifactregistry.writer",
    "roles/serviceusage.serviceUsageConsumer",
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    logger.info("  $ %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def enable_apis(project_id: str) -> None:
    """Enable required GCP APIs."""
    logger.info("Enabling APIs...")
    run(["gcloud", "services", "enable", *APIS, "--project", project_id])
    logger.info("APIs enabled")


def create_artifact_registry(project_id: str, region: str) -> None:
    """Create Artifact Registry Docker repository if it doesn't exist."""
    repo_name = f"{PROJECT_NAME}-docker"
    logger.info("Creating Artifact Registry repository: %s", repo_name)
    result = run(
        ["gcloud", "artifacts", "repositories", "describe", repo_name,
         "--location", region, "--project", project_id],
        check=False,
    )
    if result.returncode == 0:
        logger.info("  Already exists")
        return
    run([
        "gcloud", "artifacts", "repositories", "create", repo_name,
        "--repository-format", "docker",
        "--location", region,
        "--project", project_id,
        "--description", "Docker images for fraud detector pipelines",
    ])
    logger.info("  Created")


def create_gcs_bucket(project_id: str, region: str, suffix: str) -> None:
    """Create a GCS bucket if it doesn't exist."""
    bucket = f"gs://{project_id}-{PROJECT_NAME}-{suffix}"
    logger.info("Creating GCS bucket: %s", bucket)
    result = run(["gsutil", "ls", bucket], check=False)
    if result.returncode == 0:
        logger.info("  Already exists")
        return
    run(["gsutil", "mb", "-l", region, "-p", project_id, "--pap", "enforced", bucket])
    logger.info("  Created")


def create_bq_dataset(project_id: str, region: str) -> None:
    """Create BigQuery dataset if it doesn't exist."""
    dataset = "fraud_detection"
    logger.info("Creating BigQuery dataset: %s", dataset)
    result = run(
        ["bq", "show", f"{project_id}:{dataset}"],
        check=False,
    )
    if result.returncode == 0:
        logger.info("  Already exists")
        return
    run(["bq", "mk", "--dataset", f"--location={region}", f"{project_id}:{dataset}"])
    logger.info("  Created")


def create_service_account(project_id: str) -> str:
    """Create pipeline service account if it doesn't exist."""
    sa_id = f"{PROJECT_NAME}-pipelines"
    sa_email = f"{sa_id}@{project_id}.iam.gserviceaccount.com"
    logger.info("Creating service account: %s", sa_email)

    result = run(
        ["gcloud", "iam", "service-accounts", "describe", sa_email, "--project", project_id],
        check=False,
    )
    if result.returncode == 0:
        logger.info("  Already exists")
    else:
        run([
            "gcloud", "iam", "service-accounts", "create", sa_id,
            "--display-name", f"{PROJECT_NAME} Pipeline Service Account (dev)",
            "--project", project_id,
        ])
        logger.info("  Created")

    return sa_email


def grant_roles(project_id: str, sa_email: str) -> None:
    """Grant IAM roles to the pipeline service account."""
    logger.info("Granting IAM roles to %s", sa_email)
    for role in PIPELINE_SA_ROLES:
        run([
            "gcloud", "projects", "add-iam-policy-binding", project_id,
            "--member", f"serviceAccount:{sa_email}",
            "--role", role,
            "--condition=None",
            "--quiet",
        ])
    logger.info("  %d roles granted", len(PIPELINE_SA_ROLES))


def main():
    parser = argparse.ArgumentParser(description="Set up dev environment infrastructure")
    parser.add_argument("--region", default="us-central1", help="GCP region (default: us-central1)")
    parser.add_argument("--skip-iam", action="store_true", help="Skip service account and IAM setup")
    args = parser.parse_args()

    project_id = os.environ.get("PROJECT_ID")
    if not project_id:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, check=True,
        )
        project_id = result.stdout.strip()

    if not project_id:
        logger.error("PROJECT_ID not set and no gcloud default project. Run:")
        logger.error("  export PROJECT_ID=<your-project-id>")
        sys.exit(1)

    region = args.region
    logger.info("=" * 60)
    logger.info("Setting up dev environment")
    logger.info("  Project: %s", project_id)
    logger.info("  Region:  %s", region)
    logger.info("=" * 60)

    enable_apis(project_id)
    create_artifact_registry(project_id, region)
    create_gcs_bucket(project_id, region, "pipeline-root")
    create_gcs_bucket(project_id, region, "artifacts")
    create_bq_dataset(project_id, region)

    if not args.skip_iam:
        sa_email = create_service_account(project_id)
        grant_roles(project_id, sa_email)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Dev environment ready!")
    logger.info("=" * 60)
    logger.info("Next steps:")
    logger.info("  make setup-data          # Load sample data")
    logger.info("  make run-training-local  # Run training pipeline locally")
    logger.info("  make submit-training     # Submit training to Vertex AI")


if __name__ == "__main__":
    main()
