# Codebase Walkthrough

A guided tour of the project — from ML logic to production infrastructure — followed by a hands-on exercise where you make your first code change and ship it.

**Prerequisites**: You've completed the [Setup Guide](SETUP.md) — `make install`, authenticated with `gcloud`, and loaded sample data with `make setup-data`.

---

## Part 1: Guided Codebase Tour

### The big picture

This is a production-ready starter pack for predictive ML on Google Cloud. It provides a complete, working system — feature engineering, model training, evaluation, batch scoring, monitoring, CI/CD, and multi-environment infrastructure — built around a fraud detection use case. The idea is to give you everything you need to go from prototype to production: clone it, run it end-to-end, understand how the pieces connect, then swap in your own model and data.

The project is organized into four layers:

```
┌─────────────────────────────────────────────────────────┐
│  ML Logic            fraud_detector/model.py            │
├─────────────────────────────────────────────────────────┤
│  Orchestration       fraud_detector/pipelines/          │
├─────────────────────────────────────────────────────────┤
│  CI/CD               .github/workflows/                 │
├─────────────────────────────────────────────────────────┤
│  Infrastructure      deployment/terraform/              │
└─────────────────────────────────────────────────────────┘
```

Each layer builds on the one above it. The tour follows this same order.

---

### Stop 1: ML logic — `fraud_detector/model.py`

This is the best place to start, since all the ML logic lives here.

`FraudDetector` is a plain Python class with no cloud dependencies that handles four things:

1. **Feature engineering** (`compute_features`) — computes 24 rolling-window features from raw transactions. For each of 2 grouping columns (`customer_id`, `terminal_id`) × 4 time windows (1, 7, 28, 90 days) × 3 aggregations (count, avg, max) = 24 features, plus `tx_amount` = 25 total.

2. **Training** (`train`) — fits an XGBoost classifier. Data is split by time (not randomly) to prevent leakage.

3. **Evaluation** (`evaluate`) — computes AUC-ROC, precision, recall, F1, and a confusion matrix.

4. **Prediction** (`predict`) — scores a DataFrame, adding `fraud_probability` and `fraud_prediction` columns.

All feature preparation uses `.fillna(0).astype(float)` because BigQuery returns `tx_amount` as Python `Decimal`, which XGBoost can't handle.

**Key design choice**: there's no I/O in this class — no BigQuery reads, no GCS writes. All of that is handled by the pipeline layer, which makes the ML logic testable in isolation and easy to swap out.

### Stop 2: Configuration — `fraud_detector/config/`

The project is fully config-driven — all pipeline parameters live in YAML files:

| File | Controls |
|------|----------|
| `training.yaml` | XGBoost hyperparameters, train/test split date, AUC threshold for registration, pipeline schedule |
| `scoring.yaml` | Model version alias (`champion`), predictions table, scoring schedule |
| `monitoring.yaml` | Per-feature drift thresholds (Jensen-Shannon divergence), alert emails |

`config.py` loads these and resolves `${PROJECT_ID}` and other `${VAR}` placeholders from environment variables at runtime. If `PROJECT_ID` isn't set, it auto-detects from `gcloud`.

If you want to change hyperparameters, schedules, or thresholds, you just edit a YAML file — no code changes needed.

#### SQL templates — `fraud_detector/config/sql/`

The config directory also contains SQL templates that define exactly what data is read from BigQuery. Components use these via `config.py`'s `load_sql()` function, with `{project_id}` and `{bq_dataset}` placeholders filled in at runtime:

| Template | Used by | What it does |
|----------|---------|-------------|
| `read_raw_transactions.sql` | Feature engineering | Joins `tx` and `txlabels` tables, returns raw transactions with fraud labels |
| `read_features.sql` | Training + evaluation | Reads the pre-computed feature table |
| `read_unscored.sql` | Scoring | Reads feature rows that haven't been scored yet (LEFT JOIN against predictions) |

The SQL is intentionally simple — if you want to filter data differently or add new source tables, these are the files to edit.

### Stop 3: Pipeline components — `fraud_detector/pipelines/components/`

Each pipeline step is a KFP component — a Python function decorated with `@pipeline_component()`. Components are **thin wrappers**: they handle I/O (BigQuery reads, artifact storage) and delegate actual ML work to `FraudDetector`.

Walk through them in execution order:

| Component | What it does |
|-----------|-------------|
| `feature_engineering_op` | Reads raw transactions from BigQuery → calls `FraudDetector.compute_features()` → writes feature table back |
| `train_op` | Reads features → calls `FraudDetector().train()` → saves model as `model.joblib` |
| `evaluate_op` | Loads the trained model → calls `FraudDetector().evaluate()` → logs metrics |
| `register_op` | If AUC ≥ threshold → registers model to Vertex AI Model Registry with `champion` alias |
| `predict_op` | Loads `champion` model from registry → calls `FraudDetector().predict()` |
| `write_predictions_op` | Writes scored transactions to the `fraud_scores` BigQuery table |
| `monitoring_op` | Sets up Vertex AI Model Monitoring — drift detection on each feature |

Open `feature_engineering_op.py` and `train_op.py` to see the pattern. Imports happen *inside* the function body — this is a KFP requirement, since each component runs in its own container.

### Stop 4: Pipeline definitions — `fraud_detector/pipelines/`

Two pipeline files wire the components into directed acyclic graphs (DAGs).

**Training pipeline** (`training_pipeline.py`):

```
feature_engineering_op
        │
        ├──→ data_profile_op (parallel, optional)
        │
        └──→ train_op
                │
                └──→ evaluate_op
                        │
                        └──→ register_op (conditional: AUC ≥ threshold)
                                │
                                └──→ setup_monitoring_op
```

Steps are connected with `.after()` calls and artifact passing (`train_task.outputs["model"]` flows into `evaluate_op`). The model is only registered if it meets the AUC threshold — this prevents low-quality models from reaching production. Monitoring is only set up if registration succeeds.

The **scoring pipeline** (`scoring_pipeline.py`) follows a simpler flow: feature engineering → predict → write predictions.

### Stop 5: Pipeline submission — `fraud_detector/pipelines/submit_pipeline.py`

This CLI connects the pipeline definitions to execution environments and supports four modes:

| Flag | What happens |
|------|-------------|
| `--local` | Runs the pipeline on your laptop via KFP's `SubprocessRunner` — same DAG, local subprocesses |
| `--compile-only` | Outputs a pipeline JSON spec, no execution |
| *(default)* | Builds container image + code wheel, submits to Vertex AI Pipelines |
| `--schedule-only` | Creates/updates a Cloud Scheduler cron job without running the pipeline |

It also manages the **two-layer build system**:
- **Deps image** — Docker image with only dependencies. Tagged with a content hash of `Dockerfile` + `pyproject.toml` + `uv.lock`. Only rebuilt when deps change.
- **Code wheel** — `fraud_detector/` packaged as a Python wheel, published to Artifact Registry. Each code change gets a unique version hash. Components install it at startup.

This means code-only changes deploy a ~27KB wheel instead of rebuilding a full container image.

### Stop 6: Build configuration — `Dockerfile` and `pyproject.toml`

These two files define what goes into the deps-only container image and how the project is packaged.

**`Dockerfile`** is deliberately minimal — it installs dependencies without copying any application code:

```dockerfile
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY fraud_detector/_version.py ./fraud_detector/_version.py
RUN uv sync --frozen --no-dev --no-editable --no-install-project --extra pipelines
ENV PATH="/app/.venv/bin:$PATH"
```

The key flag is `--no-install-project` — it installs all dependencies but not the `fraud_detector` package itself. Application code arrives later as a wheel via `packages_to_install` at component startup.

**`pyproject.toml`** organizes dependencies into groups:

| Group | What it includes | When it's needed |
|-------|-----------------|-----------------|
| Core (default) | BigQuery, pandas, XGBoost, scikit-learn | Always |
| `pipelines` | KFP, Artifact Registry auth, Docker, ydata-profiling | Container image + cloud submission |
| `notebook` | JupyterLab, matplotlib, seaborn | Local exploration |
| `dev` | pytest, ruff | Development and CI |

`make install` runs `uv sync --all-extras` to install everything locally. The container image only gets core + `pipelines`.

### Stop 7: Tests — `tests/`

Unit tests validate the ML logic in isolation, without any cloud dependencies:

- `test_feature_engineering.py` — feature columns, shapes, rolling window values
- `test_training.py` — train/test split, model training, evaluation metrics, serialization
- `test_monitoring.py` — drift detection logic

Tests use small synthetic DataFrames (10-200 rows) and can be run with `make test-unit`.

Integration tests (`tests/integration/`) require a GCP project and test against live BigQuery.

### Stop 8: Scripts — `scripts/`

Utility scripts handle setup, data loading, and environment verification:

| Script | What it does | Make target |
|--------|-------------|-------------|
| `setup_data.py` | Loads transaction data into BigQuery — either synthetic (10K rows, fast), sample from GCS (100K rows), or the full FraudFinder dataset (3.1M rows) | `make setup-data`, `make setup-data-gcs`, `make setup-data-full` |
| `verify_setup.py` | Runs pre-flight checks (Python version, dependencies, gcloud auth, PROJECT_ID, APIs enabled, BigQuery tables exist) and reports what's missing | `make verify-setup` |
| `setup_dev_env.py` | Provisions dev infrastructure without Terraform — enables APIs, creates Artifact Registry repos, GCS buckets, BigQuery dataset, and a pipeline service account with IAM roles | `make setup-dev-env` |

These are the scripts you interact with most during initial setup. They're designed to be idempotent — running them again skips resources that already exist.

### Stop 9: CI/CD — `.github/workflows/`

Three workflows handle the path from code change to production:

**`pr_checks.yaml`** — runs on every pull request to `main`:
- Installs dependencies
- Runs unit tests + integration tests
- Lints with ruff
- Must pass before merge

**`staging.yaml`** — runs automatically when a PR is merged to `main`:
- Authenticates to GCP via Workload Identity Federation (no service account keys)
- Builds the deps-only container image (via Cloud Build, only if deps changed)
- Submits training + scoring pipelines to the **staging** project
- Triggers the production workflow

**`deploy-to-prod.yaml`** — requires manual approval via GitHub environment protection:
- Submits training + scoring pipelines to the **production** project
- Creates/updates Cloud Scheduler cron jobs (training weekly, scoring every 6 hours)

The full flow:

```
PR opened          →  pr_checks.yaml     →  lint, test
PR merged to main  →  staging.yaml       →  build image, deploy to staging
Manual approval    →  deploy-to-prod.yaml →  deploy to prod, create schedules
```

### Stop 10: Infrastructure — `deployment/terraform/`

Terraform provisions the multi-project GCP setup:

| Resource | Where | Purpose |
|----------|-------|---------|
| Artifact Registry (Docker + Python) | CI/CD project | Store container images and code wheels |
| Workload Identity Federation | CI/CD project | Keyless GitHub Actions → GCP auth |
| Service accounts + IAM | All projects | Pipeline execution permissions |
| GCS buckets | Staging + Prod | Pipeline root, model artifacts |
| BigQuery datasets | Staging + Prod | Data warehouse |
| GitHub secrets/variables | GitHub repo | Automated secret management |
| Production environment | GitHub repo | Manual approval gate |

Three GCP projects:
- **CI/CD project** — builds artifacts, manages GitHub integration
- **Staging project** — pre-production validation
- **Production project** — live system with scheduled pipelines

You can deploy all of this with `make setup-prod`. Terraform also configures GitHub Actions secrets and variables automatically via the GitHub provider, so there's no manual secret setup required.

### Stop 11: Monitoring and schedules

Once deployed to production, the system runs autonomously:

| Schedule | Pipeline | What happens |
|----------|----------|-------------|
| Weekly (Sunday 2am) | Training | Recomputes features, retrains model, evaluates, conditionally registers |
| Every 6 hours | Scoring | Scores unscored transactions, writes predictions to BigQuery |
| Weekly (Monday 8am) | Monitoring | Compares feature distributions (training vs serving), alerts on drift |

Monitoring uses Jensen-Shannon divergence per feature. Thresholds are configured in `monitoring.yaml`. When drift exceeds a threshold, the team gets an email alert — signaling it's time to investigate or retrain.

### Stop 12: The notebook — `notebooks/01_exploratory.ipynb`

The notebook walks through the ML workflow interactively: connect to BigQuery, explore the data, compute features, train a model, evaluate it, iterate on hyperparameters, and log experiments to Vertex AI. It's the best way to build intuition for the data and the feature engineering logic.

### Stop 13: AI coding agent support — `GEMINI.md`

The repo ships with [`GEMINI.md`](../GEMINI.md), a context file designed for AI coding agents (Gemini Code Assist, Claude Code, Cursor, etc.). When an agent reads this file, it learns:

- The architecture and design decisions behind the project
- 20+ gotchas and hard-won learnings (BigQuery decimal types, timezone handling, KFP caching quirks, ARM-to-AMD64 builds, cross-project IAM, and more)
- Code patterns that work correctly with the project's conventions
- The development workflow from edit to production

This means when you ask an agent to add a feature, fix a bug, or extend a pipeline, it avoids the pitfalls that would otherwise cost hours of debugging. If you're adding new gotchas or patterns to the project, update `GEMINI.md` so the next developer (or agent) benefits.

### How it all connects

```
fraud_detector/
├── model.py              ← ML logic (features, training, evaluation, prediction)
├── config.py             ← YAML config loader
├── config/*.yaml         ← parameters (hyperparams, schedules, thresholds)
├── config/sql/*.sql      ← BigQuery query templates
└── pipelines/
    ├── components/*.py   ← thin wrappers: I/O + call model.py
    ├── training_pipeline.py  ← DAG: FE → train → eval → register → monitor
    ├── scoring_pipeline.py   ← DAG: FE → predict → write
    └── submit_pipeline.py    ← CLI: local / cloud / schedule

scripts/                  ← setup, data loading, verification
tests/                    ← unit + integration tests
notebooks/                ← interactive exploration
.github/workflows/        ← CI/CD: PR checks → staging → prod
deployment/terraform/     ← multi-project GCP infrastructure
Dockerfile                ← deps-only container (no application code)
pyproject.toml            ← dependencies + optional groups
GEMINI.md                 ← context file for AI coding agents
Makefile                  ← entry points for everything
```

**Where to look for what**:

| I want to... | Look here |
|--------------|-----------|
| Change the model or features | `fraud_detector/model.py` |
| Change hyperparameters or schedules | `fraud_detector/config/*.yaml` |
| Change what data is queried | `fraud_detector/config/sql/*.sql` |
| Change pipeline orchestration | `fraud_detector/pipelines/` |
| Change dependencies | `pyproject.toml` (then rebuild with `make build-image`) |
| Change CI/CD behavior | `.github/workflows/` |
| Change infrastructure | `deployment/terraform/` |
| Understand the data | `notebooks/01_exploratory.ipynb` |
| Document gotchas for agents | `GEMINI.md` |

---

## Part 2: Make Your First Change

Let's add a new feature, test it, run the pipeline locally, and see how it would flow through CI/CD to production.

The feature we'll add is **time since a customer's previous transaction** (`hours_since_last_tx_customer`) — a useful fraud signal, since fraudsters often make multiple transactions in rapid succession.

### Step 1: Add the feature to `fraud_detector/model.py`

Open `fraud_detector/model.py` — you'll need to make two changes.

**First**, update `feature_columns()` to include the new column:

```python
@staticmethod
def feature_columns(windows: list[int] | None = None) -> list[str]:
    """Return the list of engineered feature column names."""
    if windows is None:
        windows = FraudDetector.ROLLING_WINDOWS
    cols = ["tx_amount"]
    for group in ["customer", "terminal"]:
        for window in windows:
            for agg in ["count", "avg", "max"]:
                cols.append(f"{agg}_tx_amount_{window}d_{group}")
    cols.append("hours_since_last_tx_customer")  # ← add this line
    return cols
```

**Second**, compute the feature in `compute_features()`. Add this block at the end of the method, just before the `logger.info` line:

```python
    # Time since previous transaction (per customer)
    df = df.sort_values(["customer_id", "tx_ts"]).reset_index(drop=True)
    df["hours_since_last_tx_customer"] = (
        df.groupby("customer_id")["tx_ts"]
        .diff()
        .dt.total_seconds()
        .div(3600)
        .fillna(0)
    )

    logger.info("[OK] Feature engineering complete. Shape: %s", df.shape)
    return df
```

### Step 2: Update the tests

Open `tests/unit/test_feature_engineering.py`. Update the feature count assertions (25 → 26, 13 → 14) and add a test for the new feature:

```python
def test_feature_columns():
    """Feature columns should include tx_amount + rolling aggregations."""
    cols = FraudDetector.feature_columns()
    assert "tx_amount" in cols
    assert "hours_since_last_tx_customer" in cols
    # 2 groups * 4 windows * 3 aggs = 24 + tx_amount + hours_since_last = 26
    assert len(cols) == 26


def test_feature_columns_custom_windows():
    """Custom windows should produce the right number of features."""
    cols = FraudDetector.feature_columns(windows=[1, 7])
    # 2 groups * 2 windows * 3 aggs = 12 + tx_amount + hours_since_last = 14
    assert len(cols) == 14
```

Add a new test:

```python
def test_hours_since_last_tx(sample_transactions):
    """hours_since_last_tx_customer should be 0 for first tx, positive otherwise."""
    df = FraudDetector.compute_features(sample_transactions, windows=[1])
    assert "hours_since_last_tx_customer" in df.columns
    assert df["hours_since_last_tx_customer"].isna().sum() == 0
    assert (df["hours_since_last_tx_customer"] >= 0).all()
```

### Step 3: Run the tests

```bash
make test-unit
```

All tests should pass, including the updated counts and the new test.

### Step 4: Run the pipeline locally

```bash
make run-training-local
```

This runs the full training pipeline on your machine — feature engineering, training, evaluation — using real BigQuery data. The new feature is picked up automatically because `train()` and `evaluate()` use `feature_columns()` to determine which columns to include.

Check the logs for the AUC-ROC score and compare it to the baseline (~0.89).

### Step 5: See how it flows to production

At this point you've changed two files. Here's what happens when you push:

```
1. Open a PR
   └─ pr_checks.yaml runs: lint + unit tests + integration tests

2. PR merges to main
   └─ staging.yaml runs:
      ├─ Builds deps image (skipped — deps didn't change)
      ├─ Builds code wheel (new hash — you changed model.py)
      └─ Submits pipelines to staging project

3. Manual approval in GitHub
   └─ deploy-to-prod.yaml runs:
      ├─ Submits pipelines to production project
      └─ Updates cron schedules
```

The new feature flows through automatically:
- **Feature engineering component** calls `FraudDetector.compute_features()` → computes the new column
- **Training component** calls `FraudDetector().train()` → includes it in the training matrix
- **Evaluation component** calls `FraudDetector().evaluate()` → model is scored with it
- **Scoring component** calls `FraudDetector().predict()` → new transactions are scored with it
- **Monitoring** compares feature distributions → drift detection covers the new feature

From two files changed in a single PR, the CI/CD pipeline handles the rest.

### What to try next

- **Change hyperparameters** — edit `fraud_detector/config/training.yaml` (e.g., increase `n_estimators`). No code changes needed.
- **Explore the data** — run `make notebook` and open `notebooks/01_exploratory.ipynb`
- **Submit to Vertex AI** — run `make submit-training` to see the pipeline run on Google Cloud
- **Deploy infrastructure** — run `make setup-prod` to provision staging + prod with Terraform
- **Review the design** — re-read the [Guided Codebase Tour](#part-1-guided-codebase-tour) above for the full architecture
