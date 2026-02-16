# Setup Guide

Complete setup instructions for running the Predictive MLOps Demo from scratch.

## Prerequisites

### Required

- **Google Cloud Project** with billing enabled
- **Python 3.11, 3.12, or 3.13**
- **uv** package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **gcloud CLI** installed and configured
- **Git** for version control

### Optional (for full deployment)

- **Docker Desktop** with buildx plugin (for ARM Mac → AMD64 builds)
- **Terraform >= 1.0** (for infrastructure provisioning)
- **GitHub account** (for CI/CD setup)

## Quick Start (Local Development)

### 1. Install Dependencies

```bash
git clone https://github.com/your-org/predictive_mlops_demo.git
cd predictive_mlops_demo
make install
```

This installs all Python dependencies using uv.

### 2. Authenticate to Google Cloud

```bash
# Login with your user account
gcloud auth login

# Set application default credentials
gcloud auth application-default login

# Set your project
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID
```

### 3. Load Sample Data

```bash
# Load 10K synthetic transactions (fast, for testing)
make setup-data

# OR load 100K transactions from public GCS (realistic demo)
make setup-data-gcs

# OR load the full 3M+ dataset (production-scale testing)
make setup-data-full
```

This creates:
- BigQuery dataset: `fraud_detection`
- Tables: `tx` (transactions), `txlabels` (fraud labels)

### 4. Run Training Pipeline Locally

```bash
make run-training-local
```

This runs the full pipeline on your laptop using KFP's subprocess runner:
- Feature engineering (pandas rolling windows)
- Model training (XGBoost)
- Evaluation (AUC ~0.89)
- Local model save

Output: `local_outputs/training_pipeline/`

### 5. Run Scoring Pipeline Locally

```bash
make run-scoring-local
```

This loads the trained model and scores all transactions.

Output: `local_outputs/scoring_pipeline/`

## Cloud Deployment (Vertex AI)

### 1. Enable Required APIs

```bash
gcloud services enable \
  compute.googleapis.com \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### 2. Set Up Artifact Registry

```bash
# Create Python package repository
make setup-ar-python

# Create Docker repository (for deps-only image)
gcloud artifacts repositories create fraud-detector-docker \
  --repository-format=docker \
  --location=us-central1 \
  --project=$PROJECT_ID
```

### 3. Build and Push Container Image

```bash
# For Intel/AMD machines
make build-image

# For ARM Mac (requires Docker buildx)
docker buildx create --use --name multiarch-builder
make build-image
```

### 4. Submit Training Pipeline to Vertex AI

```bash
export PROJECT_ID=your-project-id
make submit-training
```

This:
- Compiles the KFP pipeline
- Submits to Vertex AI Pipelines
- Prints the console URL to track progress

### 5. Submit Scoring Pipeline

```bash
make submit-scoring
```

Predictions are written to `{PROJECT_ID}.fraud_detection.predictions`.

## Multi-Environment Setup (Staging + Production)

### 1. Create Projects

Create three Google Cloud projects:
- Dev/CI-CD project (e.g., `my-fraud-cicd`)
- Staging project (e.g., `my-fraud-staging`)
- Production project (e.g., `my-fraud-prod`)

### 2. Configure Terraform Variables

```bash
cd deployment/terraform/vars
cp env.tfvars.example env.tfvars
```

Edit `env.tfvars`:

```hcl
project_name           = "fraud-detector"
prod_project_id        = "my-fraud-prod"
staging_project_id     = "my-fraud-staging"
cicd_runner_project_id = "my-fraud-cicd"
region                 = "us-central1"
repository_owner       = "your-github-username"
repository_name        = "predictive_mlops_demo"
create_repository      = false
```

### 3. Set Up GitHub Repository

```bash
# Create a new repo on GitHub (don't initialize it)
# Then push this code:
git remote add origin https://github.com/your-username/predictive_mlops_demo.git
git branch -M main
git push -u origin main
```

### 4. Deploy Infrastructure

```bash
# This provisions:
# - Staging + prod GCP resources (buckets, service accounts, IAM)
# - Workload Identity Federation for GitHub Actions
# - GitHub Actions secrets and variables (automatic)

cd deployment/terraform
terraform init
terraform apply -var-file=vars/env.tfvars
```

Review the plan, type `yes` to proceed.

### 5. Trigger CI/CD

```bash
git add .
git commit -m "feat: initial setup"
git push origin main
```

This triggers:
- Staging deployment (automatic)
- Production deployment (manual approval via GitHub environment protection)

## Development Environment Setup

For day-to-day development, you can use a simplified dev environment:

```bash
# Set up dev infrastructure with Terraform
make setup-dev-env-terraform

# OR use the Python script (simpler, no Terraform required)
export PROJECT_ID=your-dev-project-id
make setup-dev-env
```

This creates:
- Service accounts with correct IAM roles
- Artifact Registry repos
- Storage buckets
- Enables required APIs

## Jupyter Notebook

Explore the data and experiment with models:

```bash
make notebook
```

This launches Jupyter Lab. Open `notebooks/01_exploratory.ipynb`.

## Testing

```bash
# Unit tests only (no cloud dependencies)
make test-unit

# Integration tests (requires PROJECT_ID)
export PROJECT_ID=your-test-project-id
make test-integration

# All tests
make test
```

## Troubleshooting

### "Permission denied" errors

Check that you've authenticated:
```bash
gcloud auth application-default login
```

And that your user/service account has the required roles:
- BigQuery Admin
- Vertex AI User
- Storage Admin
- Artifact Registry Writer

### "Image not found" errors

Build and push the container image first:
```bash
make build-image
```

### ARM Mac Docker builds failing

Install Docker buildx and create a builder:
```bash
docker buildx create --use --name multiarch-builder
docker buildx inspect --bootstrap
```

### KFP pipeline submission fails

Check that Vertex AI API is enabled:
```bash
gcloud services enable aiplatform.googleapis.com
```

And that you've set `PROJECT_ID`:
```bash
export PROJECT_ID=your-project-id
```

### Terraform apply fails with GitHub provider errors

Set your GitHub token:
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

Token needs `repo` and `workflow` scopes.

## Next Steps

- Review `CLAUDE.md` or `GEMINI.md` for architecture details and gotchas
- Customize the model in `fraud_detector/model.py`
- Adjust features in the `compute_features()` method
- Modify pipeline schedules in `fraud_detector/config/*.yaml`
- Set up monitoring thresholds in `fraud_detector/config/monitoring.yaml`

## Getting Help

- Check existing [Issues](https://github.com/your-org/predictive_mlops_demo/issues)
- Review the [Contributing Guide](CONTRIBUTING.md)
- See [CLAUDE.md](CLAUDE.md) for common pitfalls and solutions
