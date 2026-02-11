# Coding Agent Guidance — Predictive MLOps Demo

## Project Overview

This is an E2E predictive MLOps solution for fraud detection on Google Cloud. It demonstrates the full lifecycle from notebook exploration to production pipelines with CI/CD.

## Architecture

- **Data**: BigQuery is the single source of truth (raw data, features, predictions)
- **ML**: XGBoost classifier trained in Python (scikit-learn/XGBoost)
- **Features**: Computed in pandas (rolling window aggregations), written back to BQ
- **Pipelines**: Vertex AI Pipelines (KFP v2) for training, scoring, monitoring
- **Infra**: Terraform (multi-project: dev/staging/prod)
- **CI/CD**: GitHub Actions with Workload Identity Federation
- **Package Manager**: uv

## Key Design Decisions

1. **No Feature Store** — BigQuery is the only data layer
2. **Python feature engineering** — pandas transforms after reading from BQ (swappable to SQL/BigFrames/Dataproc)
3. **Config-driven** — all parameters in YAML files under `config/`
4. **Conditional model registration** — only if AUC exceeds threshold
5. **KFP local runner** — test pipelines locally before cloud submission
6. **Single source folder** — all code (business logic + pipelines) lives under `fraud_detector/`

## Code Structure

```
fraud_detector/                     # Single source code package
  config.py                         # YAML config loader with ${VAR} env var resolution
  feature_engineering.py            # read_raw_data() → compute_features() → write_features_to_bq()
  training.py                       # train_model() → evaluate_model() → save_model() → register
  scoring.py                        # load_model() → batch_predict() → write_predictions_to_bq()
  monitoring.py                     # Vertex AI Model Monitoring setup
  utils.py                          # BQ/GCS client helpers
  config/                           # YAML pipeline configs
    training.yaml                   # XGBoost params, eval threshold, split date
    scoring.yaml                    # Model version, predictions table
    monitoring.yaml                 # Drift thresholds, alert emails
  pipelines/
    training_pipeline.py            # KFP: feature_eng → train → evaluate → register (conditional)
    scoring_pipeline.py             # KFP: feature_eng → predict → write_predictions
    submit_pipeline.py              # CLI: --local, --compile-only, --schedule-only
    components/                     # Individual KFP @dsl.component definitions

scripts/                            # Data setup and E2E test scripts
tests/                              # Unit + integration tests
deployment/terraform/               # Multi-project Terraform + GitHub CI/CD wiring
notebooks/                          # Exploratory notebook
```

`fraud_detector/config.py` resolves the config path via `Path(__file__).parent / "config"`.

## Development Workflow

1. **Edit code** in `fraud_detector/`
2. **Run tests**: `make test-unit`
3. **Test locally**: `make run-training-local` (KFP local execution)
4. **Submit to dev Vertex AI**: `make submit-training`
5. **Deploy infra + CI/CD**: `make setup-prod` (Terraform)
6. **Push to main**: triggers staging deploy via GitHub Actions

## Feature Engineering

Rolling window features per customer and terminal:
- Windows: 1d, 7d, 28d, 90d
- Aggregations: count, avg, max of tx_amount
- Total: 24 rolling features + tx_amount = 25 features

## Dataset (FraudFinder)

Public data in `gs://fraudfinder-public-data/`:
- `sample/tx/` + `sample/tx_labels/` — ~100K rows, ~11 MB (1 day)
- `tx/` + `tx_labels/` — ~3.1M rows, ~308 MB (1 month)
- Source: `cymbal-fraudfinder.txbackup.all` (Jan 2024), ~2% fraud rate

| Table | Key Columns |
|-------|-------------|
| `tx` | tx_id, tx_ts, customer_id, terminal_id, tx_amount |
| `txlabels` | tx_id, tx_fraud |

## Config Files

- `config/training.yaml` — pipeline schedule, XGBoost params, eval threshold
- `config/scoring.yaml` — scoring schedule, model version alias
- `config/monitoring.yaml` — drift thresholds, alert emails

## Testing

- Unit tests: `tests/unit/` — test feature engineering and training logic
- Integration tests: `tests/integration/` — require PROJECT_ID env var
- Run: `make test` or `make test-unit`

## Infrastructure

- `deployment/terraform/` — multi-project Terraform (staging + prod + CI/CD)
- `deployment/terraform/dev/` — simpler single-project dev setup (optional)
- Projects: asp-test-dev (dev), asp-test-stg (staging), asp-test-prd (prod)

## Gotchas & Learnings for Coding Agents

### BigQuery Decimal types
BigQuery returns `tx_amount` as Python `Decimal` (dtype `object`). XGBoost cannot handle this. Always use `.astype(float)` after `.fillna(0)`:
```python
X = df[feature_cols].fillna(0).astype(float)
```
This applies to ALL places that prepare features for model input: `train_model()`, `evaluate_model()`, `batch_predict()`, and all KFP component equivalents.

### Timezone handling
BigQuery returns timestamps as tz-aware (UTC). Pandas `Timestamp()` comparisons fail with mixed tz-aware/tz-naive. Strip timezone after loading from BQ:
```python
df["tx_ts"] = pd.to_datetime(df["tx_ts"], utc=True).dt.tz_localize(None)
```
Or guard comparisons:
```python
ts_col = df["tx_ts"]
if ts_col.dt.tz is not None:
    ts_col = ts_col.dt.tz_localize(None)
```

### Vertex AI labels
Label values cannot contain dots. When using floats as label values (e.g., AUC score), replace dots:
```python
labels={"auc_roc": str(round(auc_roc, 4)).replace(".", "_")}
```

### KFP local execution
- Use `SubprocessRunner(use_venv=False)` to reuse the current environment instead of creating a venv per component
- Requires the `docker` Python package even for SubprocessRunner
- KFP type checking is strict: if a pipeline parameter is `float`, you must pass `float(value)` — an `int` from YAML config will fail with `InconsistentTypeException`
- `EXPORT DATA` in BigQuery requires wildcard URIs (`gs://bucket/path/*.parquet`)

### KFP component code — custom container approach
KFP components use a custom Docker image (`fraud-detector-docker`) that has the full `fraud_detector` package pre-installed. This means:
- **No `packages_to_install`** — everything is in the image, so startup is fast
- **No code duplication** — components are thin wrappers that import from the library
- **No runtime pip installs** — all dependencies are baked into the image
- The image URI is constructed from env vars: `{REGION}-docker.pkg.dev/{CICD_PROJECT_ID}/fraud-detector-docker/fraud-detector:{IMAGE_TAG}`
- For local execution (`SubprocessRunner(use_venv=False)`), the base_image is ignored — it just imports from the local env
- CI/CD builds the image with `gcloud builds submit` and tags it with the git SHA
- For dev, use `make build-image` (requires Docker + Artifact Registry repo)

### Rolling features performance
The optimized pattern for pandas rolling window features with groupby uses direct `.values` assignment instead of merge:
```python
indexed = df.set_index("tx_ts")
rolling = indexed.groupby(group_col)["tx_amount"].rolling(f"{window}D", min_periods=1)
df[col] = rolling.count().droplevel(0).sort_index().values
```
Do NOT use the merge-per-feature pattern — it's orders of magnitude slower on large datasets.

### Pipeline status checking
Use the Python SDK to check Vertex AI pipeline status, not `gcloud` CLI:
```python
from google.cloud import aiplatform
aiplatform.init(project="<project-id>", location="us-central1")
jobs = aiplatform.PipelineJob.list(
    filter='display_name="fraud-detector-training"',
    order_by="create_time desc",
)
job = jobs[0]
print(f"State: {job.state.name}")
for task in job.task_details:
    print(f"  {task.task_name}: {task.state.name}")
```

### Bucket naming convention
Pipeline code uses `{project_id}-fraud-detector-artifacts` and `{project_id}-fraud-detector-pipeline-root`. Terraform must match this pattern. The dev terraform is optional — buckets are auto-created or created by earlier demo steps.

### GitHub provider in Terraform
Terraform handles GitHub Actions secrets/variables automatically via `github_actions_secret` and `github_actions_variable` resources. Requires `GITHUB_TOKEN` env var and the `integrations/github` provider. No manual secret configuration needed.

## Guidelines for Code Changes

- Keep changes minimal and focused
- Follow existing patterns in the codebase
- All pipeline parameters should be config-driven (YAML)
- KFP components are thin wrappers — all business logic lives in the library modules (`feature_engineering.py`, `training.py`, `scoring.py`)
- Always use `.astype(float)` when preparing features for model input
- Always handle timezone-aware timestamps from BigQuery
- Run `make test-unit` after any changes
- Run `make lint` to check code style
- Use `make run-training-local` to validate pipeline changes before submitting to Vertex AI
