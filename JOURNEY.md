# Demo Journey

End-to-end walkthrough: from clone to production deployment.

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- `uv` package manager (auto-installed by `make install` if missing)

## Step 1: Clone & Install

```bash
git clone <repo-url>
cd predictive_mlops_demo
make install
```

This installs all dependencies (including pipelines, notebook, and dev extras) via `uv`.

## Step 2: Authenticate to GCP

```bash
gcloud auth application-default login
export PROJECT_ID=<your-gcp-project-id>
```

## Step 3: Load Data into BigQuery

```bash
make setup-data              # ~100K rows sample (fast, ~10s)
make setup-data-full         # ~3.1M rows full dataset
```

This loads real FraudFinder transaction data from a public GCS bucket (`gs://fraudfinder-public-data/`) into BigQuery tables `tx` and `txlabels` in the `fraud_detection` dataset.

**Data source**: 1 month of transactions from `cymbal-fraudfinder.txbackup.all` (Jan 2024), ~2% fraud rate.

## Step 4: Run Training Pipeline Locally

```bash
make run-training-local
```

This runs the full KFP training pipeline locally using `kfp.local.SubprocessRunner`:

```
feature-engineering-op  →  Reads raw BQ data, computes 25 rolling features, writes to BQ
train-op                →  Trains XGBoost model, uploads to GCS
evaluate-op             →  Evaluates on holdout set, returns AUC-ROC
register-op             →  Registers model in Vertex AI if AUC >= threshold (0.85)
```

Expected results with sample data: AUC ~0.888, model registered.

## Step 5: Run Tests

```bash
make test-unit
```

9 unit tests covering feature engineering and training logic.

## Step 6: Submit Pipeline to Vertex AI (Dev)

```bash
make submit-training
```

This compiles the KFP pipeline and submits it to Vertex AI Pipelines on your dev project. No Terraform required — the buckets and datasets were already created by previous steps.

Check pipeline status:

```python
from google.cloud import aiplatform

aiplatform.init(project="<project-id>", location="us-central1")

# List recent pipeline runs
jobs = aiplatform.PipelineJob.list(
    filter='display_name="fraud-detector-training"',
    order_by="create_time desc",
)
job = jobs[0]
print(f"State: {job.state.name}")
for task in job.task_details:
    print(f"  {task.task_name}: {task.state.name}")
```

## Step 7: Deploy Infrastructure + CI/CD

Edit `deployment/terraform/vars/env.tfvars` with your values:

```hcl
project_name           = "fraud-detector"
prod_project_id        = "<your-prod-project>"
staging_project_id     = "<your-staging-project>"
cicd_runner_project_id = "<your-dev-project>"
region                 = "us-central1"
repository_owner       = "<your-github-org-or-user>"
repository_name        = "predictive_mlops_demo"
```

Then apply:

```bash
export GITHUB_TOKEN=<your-github-pat>
make setup-prod
```

This creates:
- Workload Identity Federation (WIF) pool + OIDC provider for GitHub Actions
- CI/CD runner service account with cross-project permissions
- Pipeline service accounts for staging and prod
- GCS buckets (pipeline root, model artifacts) per environment
- BigQuery datasets per environment
- GitHub Actions secrets (`WIF_POOL_ID`, `WIF_PROVIDER_ID`, `GCP_SERVICE_ACCOUNT`)
- GitHub Actions variables (`GCP_PROJECT_NUMBER`, `STAGING_PROJECT_ID`, `PROD_PROJECT_ID`, etc.)
- GitHub production environment with branch protection

## Step 8: Push to Main

```bash
git add -A && git commit -m "feat: initial fraud detection pipeline"
git push origin main
```

This triggers the CI/CD pipeline:

1. **PR checks** (`pr_checks.yaml`): lint + unit tests on pull requests
2. **Staging deploy** (`staging.yaml`): on merge to main — compiles and submits training + scoring pipelines to staging
3. **Prod deploy** (`deploy-to-prod.yaml`): manual dispatch — deploys to prod + creates pipeline schedules

## Useful Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies |
| `make test-unit` | Run unit tests |
| `make run-training-local` | Run training pipeline locally (KFP) |
| `make run-scoring-local` | Run scoring pipeline locally (KFP) |
| `make submit-training` | Submit training pipeline to Vertex AI |
| `make submit-scoring` | Submit scoring pipeline to Vertex AI |
| `make setup-data` | Load sample data into BigQuery |
| `make setup-data-full` | Load full dataset into BigQuery |
| `make setup-dev-env` | Deploy dev infrastructure (optional) |
| `make setup-prod` | Deploy staging/prod infrastructure + CI/CD |
| `make notebook` | Launch Jupyter Lab |
| `make lint` | Run linter |
| `make format` | Auto-format code |

## Project Structure

```
fraud_detector/                    # Single source code package
  model.py                         # FraudDetector class (pure ML: features, training, scoring)
  config.py                        # YAML config loader with ${VAR} resolution
  config/                          # YAML pipeline configs
    training.yaml
    scoring.yaml
    monitoring.yaml
  pipelines/
    training_pipeline.py            # KFP: FE → Train → Evaluate → Register
    scoring_pipeline.py             # KFP: FE → Predict → Write
    submit_pipeline.py              # CLI: --local, --compile-only, --schedule-only
    components/                     # Individual @dsl.component definitions

scripts/                           # setup_data.py, test_e2e.py
tests/                             # unit + integration tests
deployment/terraform/              # Multi-project Terraform + GitHub CI/CD
notebooks/                         # Exploratory notebook
```
