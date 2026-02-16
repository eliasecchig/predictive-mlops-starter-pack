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

## Step-by-Step Journey

Use this section to guide a data scientist from clone to production.

### Step 1: Clone & Install

```bash
git clone <repo-url>
cd predictive_mlops_demo
make install
```

Installs all dependencies (including pipelines, notebook, and dev extras) via `uv`.

### Step 2: Authenticate to GCP

```bash
gcloud auth application-default login
```

`PROJECT_ID` is auto-detected from `gcloud` config. Override with `export PROJECT_ID=<your-project>` if needed.

### Step 3: Load Data into BigQuery

```bash
make setup-data              # 10K synthetic rows (fast demo)
make setup-data-gcs          # ~100K rows from GCS
make setup-data-full         # ~3.1M rows full dataset
```

Default uses synthetic data (10K rows, ~2% fraud rate) for fast iteration.

| Table | Rows |
|-------|------|
| `tx` | 10,000 |
| `txlabels` | 10,000 |

### Step 4: Run Training Pipeline Locally

```bash
make run-training-local
```

Runs the full KFP pipeline locally via `SubprocessRunner(use_venv=False)`:

```
feature-engineering-op  →  Reads raw BQ data, computes 25 rolling features, writes to BQ
train-op                →  Trains XGBoost model, uploads artifact
evaluate-op             →  Evaluates on holdout set, returns AUC-ROC
register-op             →  Registers model in Vertex AI (skipped locally: LOCAL_ONLY)
setup-monitoring-op     →  Sets up Model Monitoring (skipped locally: SKIPPED:LOCAL_ONLY)
```

Expected output: AUC-ROC ~0.888, all 5 steps SUCCESS. `register-op` and `setup-monitoring-op` skip gracefully in local mode.

### Step 5: Run Tests

```bash
make test-unit
make lint
```

15 unit tests (feature engineering, monitoring, training). All lint checks should pass.

### Step 6: Submit Training Pipeline to Vertex AI

```bash
make submit-training
```

What happens under the hood:
1. **Deps image check** — hashes `Dockerfile` + `pyproject.toml` + `uv.lock`. If the hash matches the local cache (`.deps-image-tag`), no network call. Otherwise checks AR, builds only if missing.
2. **Code wheel** — hashes `fraud_detector/**/*.py`, builds and uploads a wheel to AR Python repo if the version is new.
3. **Compile + submit** — compiles the KFP pipeline and submits to Vertex AI. Prints the console URL after submission.

Expected Vertex AI output:

| Step | Status | Output |
|------|--------|--------|
| `feature-engineering-op` | SUCCEEDED | Features written to BQ |
| `train-op` | SUCCEEDED | Model artifact uploaded to GCS |
| `evaluate-op` | SUCCEEDED | AUC-ROC ~0.888 |
| `register-op` | SUCCEEDED | Model registered in Vertex AI Model Registry |
| `setup-monitoring-op` | SUCCEEDED | Monitor created with weekly drift detection |

### Step 7: Submit Scoring Pipeline to Vertex AI

```bash
make submit-scoring
```

Must run after training (the model needs to exist in the registry). All 3 steps should succeed: `feature-engineering-op` → `predict-op` → `write-predictions-op`. Predictions written to `fraud_detection.fraud_scores`.

### Step 8: Deploy Infrastructure + CI/CD

Edit `deployment/terraform/vars/env.tfvars`, then:

```bash
make setup-prod
```

Creates: WIF pool, CI/CD service accounts, pipeline SAs, GCS buckets, BQ datasets, and GitHub Actions secrets/variables for staging + prod.

### Step 9: Push to Main

```bash
git push origin main
```

Triggers CI/CD: PR checks (lint + tests) → staging deploy → manual prod deploy.

## Development Workflow (day-to-day)

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

### KFP component code — deps image + AR wheel approach
KFP components use a two-layer approach:
1. **Base image** (`fraud-detector-docker`) — deps-only, rebuilt only when `Dockerfile`/`pyproject.toml`/`uv.lock` change
2. **Code wheel** (`fraud-detector` package) — published to Artifact Registry Python repo, installed at component startup via `packages_to_install`

The `pipeline_component()` decorator in `fraud_detector/pipelines/__init__.py` wraps `dsl.component()` and sets:
- `base_image=get_base_image()` — the deps-only container
- `install_kfp_package=False`
- `packages_to_install=["--no-deps", "fraud-detector=={CODE_VERSION}"]` — installs the wheel without resolving deps (all deps are in the base image)
- `pip_index_urls=[get_ar_index_url()]` — points to the AR Python repo only (no PyPI, avoids dependency confusion)

Usage in component files:
```python
from fraud_detector.pipelines import pipeline_component

@pipeline_component()
def my_component_op(...):
    ...
```

**`ensure_deps_image()`** — hashes `Dockerfile`, `pyproject.toml`, `uv.lock` → 12-char content tag. Uses a three-tier check:
1. **Local cache** (`.deps-image-tag` file) — if the computed hash matches the cached tag, skip everything (instant, no network)
2. **AR registry check** (`gcloud artifacts docker images describe`) — if the image exists remotely, cache the tag locally and skip the build
3. **Build + push** — only when the tag is genuinely missing from AR

This means the common case (code-only changes, deps unchanged) has zero overhead from the image check.

**`ensure_code_package()`** — hashes `fraud_detector/**/*.py` → builds wheel as `0.1.0+{hash}` → uploads to AR Python repo if version is missing. Each developer's code change produces a unique hash → no collisions.

One-time setup: `make setup-ar-python` creates the AR Python repo.

- For local execution (`SubprocessRunner(use_venv=False)`), `packages_to_install` is ignored — it just imports from the local env
- CI/CD builds the deps image and uploads the wheel
- For dev, use `make build-image` (deps-only, requires Docker + AR Docker repo)

### Pipeline submission console link
After `submit_to_vertex()` submits a pipeline job, the Vertex AI console URL is printed to stdout so you can follow the run directly in your browser. The URL is constructed from `job.resource_name` after `job.submit()` returns.

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

### KFP base_image must be a function call
`BASE_IMAGE = get_base_image()` at module level gets evaluated at import time — before `IMAGE_TAG` is set by `ensure_deps_image()`. Use `pipeline_component()` which calls `get_base_image()` at decoration time. The same applies to `CODE_VERSION` — `get_code_package()` reads the env var at call time.

### enable_caching is a PipelineJob arg
`enable_caching` is a `PipelineJob` constructor argument, not a pipeline parameter. KFP silently ignores it if you pass it in `parameter_values`.

### Model file naming for Vertex AI serving
sklearn serving container requires `model.joblib` or `model.pkl` filename. KFP's `dsl.Output[dsl.Model]` gives you `model.path` which is just `model` (no extension). Vertex AI Model Registry rejects it. Save to `os.path.dirname(model.path) + "/model.joblib"` and update evaluate_op to load from the same path.

### artifact_uri must be a GCS directory
`Model.upload()` expects `artifact_uri` to be a GCS directory containing the model file, not a file path.

### Metadata store initialization
Vertex AI Metadata store must exist before the first pipeline submission. New projects need initialization — creating a throwaway `Experiment` triggers it.

### Cross-project Artifact Registry access for Vertex AI
Each project has a Vertex AI Service Agent (`service-{PROJECT_NUMBER}@gcp-sa-aiplatform-cc.iam.gserviceaccount.com`) that pulls container images. It needs `roles/artifactregistry.reader` on the CI/CD project's Docker repo.

### Cloud Build log streaming with WIF
`gcloud builds submit` can't stream logs with Workload Identity Federation auth. The federated token can submit builds but can't read from the default Cloud Logging bucket. Fix: use `--async` and poll with `gcloud builds describe`.

### Pipeline service account must be explicit
Pipeline SA must be passed explicitly via `job.submit(service_account=...)` when submitting cross-project. Without it, the default compute SA is used, which lacks permissions.

### IAM role string splitting
IAM role splitting with `/` as separator breaks on `roles/foo.bar`. `split("/", "staging/roles/aiplatform.user")[1]` returns `"roles"` not `"roles/aiplatform.user"`. Use `:` as separator instead.

### Pipeline SA needs logging permissions
Pipeline SA needs `roles/logging.logWriter` or container logs silently disappear, making debugging impossible.

### ARM Mac to AMD64 for Vertex AI
Standard `docker build` on ARM Mac produces ARM images. Vertex AI requires AMD64. Install the buildx plugin, create a multiarch builder, use `--platform linux/amd64 --push`.

### Container dependency groups
The container needs `--extra pipelines` in `uv sync`. KFP is in optional dependencies — the container runs without it and gets `No module named 'kfp'`.

### Pipeline execution order on first deploy
Scoring pipeline must run after training on first deploy. `predict-op` looks up the latest registered model — if training hasn't finished, there's no model to find. In production, the schedules handle this naturally (training weekly, scoring every 6h).

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
