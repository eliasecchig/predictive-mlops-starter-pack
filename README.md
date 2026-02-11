# Predictive MLOps Demo — E2E Fraud Detection on Google Cloud

A reusable, clone-and-run solution demonstrating the end-to-end predictive MLOps lifecycle on Google Cloud. Covers the full journey from exploratory data analysis and local model iteration to production-grade pipelines with scheduled retraining, batch scoring, monitoring, and CI/CD.

**Dataset**: FraudFinder (public fraud detection dataset in BigQuery)
**ML Framework**: scikit-learn / XGBoost
**Orchestration**: Vertex AI Pipelines (KFP v2)
**Monitoring**: Vertex AI Model Monitoring
**CI/CD**: GitHub Actions (Workload Identity Federation)
**Infra**: Terraform (multi-project: dev / staging / prod)

---

## Quick Start

### Prerequisites

- Google Cloud project(s) with billing enabled
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) installed
- `gcloud` CLI authenticated
- Terraform >= 1.0.0
- GitHub repository (for CI/CD)

### Install

```bash
make install
```

---

## Project Structure

```
predictive_mlops_demo/
├── notebooks/                  # Exploration: EDA + feature eng + local training
│   └── 01_exploratory.ipynb
├── fraud_detector/             # Production Python package
│   ├── config.py               # YAML config loader
│   ├── feature_engineering.py  # BQ read → pandas transforms → BQ write
│   ├── training.py             # XGBoost train, evaluate, save
│   ├── scoring.py              # Load model, predict, write to BQ
│   ├── monitoring.py           # Vertex AI Model Monitoring setup
│   └── utils.py                # BQ/GCS helpers
├── pipelines/                  # KFP pipeline definitions
│   ├── training_pipeline.py
│   ├── scoring_pipeline.py
│   ├── submit_pipeline.py      # Compile + submit to Vertex AI
│   └── components/             # KFP component definitions
├── config/                     # Pipeline configuration (YAML)
│   ├── training.yaml
│   ├── scoring.yaml
│   └── monitoring.yaml
├── tests/                      # Unit and integration tests
├── deployment/terraform/       # Infrastructure as code
└── .github/workflows/          # CI/CD pipelines
```

---

## Command Cheatsheet

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies with uv |
| `make test` | Run all tests (unit + integration) |
| `make test-unit` | Run unit tests only |
| `make lint` | Check code style with ruff |
| `make format` | Auto-format code |
| `make notebook` | Launch Jupyter Lab |
| `make run-training-local` | Run training pipeline locally |
| `make run-scoring-local` | Run scoring pipeline locally |
| `make submit-training` | Submit training pipeline to Vertex AI |
| `make submit-scoring` | Submit scoring pipeline to Vertex AI |
| `make schedule-training` | Create/update training schedule |
| `make schedule-scoring` | Create/update scoring schedule |
| `make setup-dev-env` | Provision dev infrastructure (Terraform) |
| `make setup-prod` | Provision staging + prod infrastructure |

---

## 1. Explore & Iterate (Notebook)

```bash
make notebook
```

Open `notebooks/01_exploratory.ipynb` to walk through:
- **EDA**: Explore raw transactions and labels in BigQuery
- **Feature engineering**: Compute rolling window features (count, avg, max) per customer and terminal
- **Model training**: Train XGBoost classifier, evaluate with AUC-ROC, precision, recall
- **Experiment tracking**: Log metrics to Vertex AI Experiments

> **Note**: Feature engineering uses pandas for portability. The layer is swappable — SQL-in-BQ, BigFrames, or Dataproc can be substituted without changing the rest of the pipeline.

---

## 2. Run Pipelines Locally

```bash
make run-training-local
make run-scoring-local
```

KFP supports local execution via `kfp.local.init()`. This runs the full pipeline DAG on your machine — same components, no cloud costs. Use this to debug component failures before submitting to Vertex AI.

---

## 3. Deploy to a Dev Environment

```bash
# Set your dev project
gcloud config set project YOUR_DEV_PROJECT_ID

# Provision dev infrastructure
make setup-dev-env

# Submit pipelines to Vertex AI
make submit-training
make submit-scoring
```

Verify in the [Vertex AI console](https://console.cloud.google.com/vertex-ai/pipelines):
- Pipeline DAG execution
- Model in Vertex AI Model Registry
- Predictions in BigQuery

---

## 4. Set Up the Path to Production (CI/CD)

```bash
# Provision staging + prod infra, WIF, GitHub Actions secrets
make setup-prod
```

This runs Terraform to provision:
- Staging and production GCP infrastructure
- Workload Identity Federation (keyless GitHub → GCP auth)
- GitHub Actions secrets and variables

**Workflow**:
1. PR to main → `pr_checks.yaml` runs tests
2. Push to main → `staging.yaml` deploys to staging
3. Manual approval → `deploy-to-prod.yaml` deploys to production

---

## 5. Schedule Pipelines

```bash
make schedule-training    # Weekly retraining (Sunday 2am)
make schedule-scoring     # Batch scoring every 6 hours
```

Schedules are configured in `config/training.yaml` and `config/scoring.yaml`. Uses Vertex AI `PipelineJobSchedule` — no Cloud Scheduler needed.

---

## 6. Monitor Your Model

Vertex AI Model Monitoring detects:
- **Data drift**: Feature distribution shifts (training vs. serving data)
- **Prediction drift**: Score distribution changes over time

Configure alert thresholds in `config/monitoring.yaml`. View results in the [Model Monitoring dashboard](https://console.cloud.google.com/vertex-ai/model-monitoring).

---

## 7. Customize for Your Use Case

| What to change | Where |
|---------------|-------|
| Dataset / tables | `config/*.yaml` + `fraud_detector/feature_engineering.py` |
| Model type | `fraud_detector/training.py` |
| Feature engineering | `fraud_detector/feature_engineering.py` (or swap to SQL/BigFrames/Dataproc) |
| Pipeline steps | `pipelines/components/` + `pipelines/*_pipeline.py` |
| Schedules | `config/training.yaml`, `config/scoring.yaml` |
| Infrastructure | `deployment/terraform/` |
| CI/CD | `.github/workflows/` |

---

## Google Cloud Services Used

| Service | Purpose |
|---------|---------|
| BigQuery | Data warehouse — raw data, features, predictions |
| Vertex AI Pipelines | Orchestrate training, scoring, monitoring |
| Vertex AI Model Registry | Version and alias trained models |
| Vertex AI Experiments | Track experiment metrics during exploration |
| Vertex AI Model Monitoring | Detect data/prediction drift |
| Cloud Storage | Model artifacts and pipeline staging |
| Artifact Registry | Docker images for pipeline components |
| Workload Identity Federation | Keyless GitHub Actions → GCP auth |
