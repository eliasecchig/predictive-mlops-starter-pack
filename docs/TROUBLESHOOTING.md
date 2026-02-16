# Troubleshooting Guide

Common issues and solutions when working with the Predictive MLOps Demo.

## Installation & Setup

### uv not found

**Error**: `command not found: uv`

**Solution**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Restart your terminal or run:
source ~/.bashrc  # or ~/.zshrc
```

### Permission denied errors

**Error**: `PermissionError: [Errno 13] Permission denied`

**Solution**: Authenticate with Google Cloud:
```bash
gcloud auth login
gcloud auth application-default login
```

### PROJECT_ID not set

**Error**: `KeyError: 'PROJECT_ID'` or `PROJECT_ID is not set`

**Solution**: Export your project ID:
```bash
export PROJECT_ID=your-project-id
gcloud config set project $PROJECT_ID
```

## BigQuery Issues

### Dataset does not exist

**Error**: `google.api_core.exceptions.NotFound: 404 Dataset not found`

**Solution**: Run the data setup script:
```bash
make setup-data
```

### Decimal type errors in XGBoost

**Error**: `ValueError: could not convert string to float: Decimal('123.45')`

**Solution**: This should be handled in the code. If you see this, ensure you're using `.astype(float)` after `.fillna(0)`:
```python
X = df[feature_cols].fillna(0).astype(float)
```

### Timezone-aware timestamp errors

**Error**: `TypeError: Cannot compare tz-naive and tz-aware timestamps`

**Solution**: Strip timezone after loading from BigQuery:
```python
df["tx_ts"] = pd.to_datetime(df["tx_ts"], utc=True).dt.tz_localize(None)
```

## Vertex AI Pipeline Issues

### Pipeline submission fails

**Error**: `google.api_core.exceptions.PermissionDenied: 403 Permission denied`

**Solution**: Enable required APIs:
```bash
gcloud services enable \
  aiplatform.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com
```

### Container image not found

**Error**: `ImagePullBackOff` or `Failed to pull image`

**Solution**: Build and push the container image:
```bash
# For Intel/AMD
make build-image

# For ARM Mac
docker buildx create --use --name multiarch-builder
make build-image
```

### Pipeline hangs on "Creating PipelineJob"

**Cause**: First-time Vertex AI usage in a project requires metadata store initialization.

**Solution**: Wait 2-3 minutes for automatic initialization, or trigger it manually:
```python
from google.cloud import aiplatform
aiplatform.init(project="your-project", location="us-central1")
aiplatform.Experiment.create("temp-experiment")
```

### "No module named 'fraud_detector'" in pipeline

**Error**: Component fails with `ModuleNotFoundError: No module named 'fraud_detector'`

**Solution**: Publish the code wheel to Artifact Registry:
```bash
make setup-ar-python
make publish-wheel
```

### Pipeline components fail with type mismatch

**Error**: `InconsistentTypeException: Argument type mismatch`

**Cause**: KFP v2 has strict type checking. If a parameter is `float`, you must pass `float(value)`, not `int`.

**Solution**: In config files, use explicit floats:
```yaml
# ❌ Wrong
learning_rate: 0.1
threshold: 0.5

# ✅ Correct (if parameter type is float)
learning_rate: 0.1
threshold: 0.5
```

And in Python:
```python
threshold = float(config["threshold"])  # Not just config["threshold"]
```

## Docker & Container Issues

### ARM Mac builds fail

**Error**: Vertex AI rejects image with `exec format error`

**Cause**: ARM images don't run on Vertex AI's AMD64 infrastructure.

**Solution**: Use buildx with explicit platform:
```bash
docker buildx create --use --name multiarch-builder
docker buildx inspect --bootstrap

# Build for AMD64
export IMAGE_TAG=latest
make build-image
```

### Docker daemon not running

**Error**: `Cannot connect to the Docker daemon`

**Solution**: Start Docker Desktop or the Docker daemon:
```bash
# Mac: Open Docker Desktop app
# Linux: sudo systemctl start docker
```

### Permission denied when pushing to Artifact Registry

**Error**: `denied: Permission "artifactregistry.repositories.uploadArtifacts" denied`

**Solution**: Authenticate Docker with Artifact Registry:
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
```

## Terraform Issues

### GitHub provider authentication fails

**Error**: `Error: GET https://api.github.com/user: 401 Bad credentials`

**Solution**: Set GitHub token with correct scopes:
```bash
# Create token at https://github.com/settings/tokens
# Needs: repo, workflow scopes
export GITHUB_TOKEN=ghp_your_token_here
```

### Workload Identity Federation setup fails

**Error**: `Error creating WorkloadIdentityPoolProvider: googleapi: Error 409: Requested entity already exists`

**Solution**: This is safe to ignore if running `terraform apply` multiple times. Or:
```bash
terraform import google_iam_workload_identity_pool.github_pool \
  projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-wif-pool
```

### Service account already exists

**Error**: `Error creating ServiceAccount: googleapi: Error 409: Service account already exists`

**Solution**: Import the existing resource:
```bash
terraform import google_service_account.pipeline_sa \
  projects/PROJECT_ID/serviceAccounts/pipeline-sa@PROJECT_ID.iam.gserviceaccount.com
```

## GitHub Actions / CI/CD Issues

### Workflow fails with "Unable to get ACTIONS_ID_TOKEN_REQUEST_URL"

**Cause**: Workload Identity Federation not configured or permissions not granted.

**Solution**:
1. Verify WIF pool and provider exist in GCP Console
2. Check GitHub Actions settings allow token issuance
3. Ensure workflow has `permissions: id-token: write`

### "Repository not found" when Terraform tries to set secrets

**Cause**: GitHub token doesn't have `repo` scope or wrong repository name.

**Solution**: Update `env.tfvars`:
```hcl
repository_owner = "your-actual-github-username"  # Not organization
repository_name  = "predictive_mlops_demo"         # Exact repo name
```

### Cloud Build can't stream logs

**Error**: Build succeeds but logs don't show in CI

**Cause**: WIF token can't read Cloud Logging.

**Solution**: This is expected. Use `--async` and poll:
```bash
BUILD_ID=$(gcloud builds submit --async --format='value(id)')
gcloud builds describe $BUILD_ID --project=PROJECT_ID
```

## Python / Dependency Issues

### uv.lock conflicts

**Error**: `error: Failed to download distributions`

**Solution**: Regenerate the lockfile:
```bash
uv lock --upgrade
```

### ImportError after adding new dependency

**Cause**: Dependency not in `pyproject.toml`.

**Solution**: Add it and sync:
```bash
uv add package-name
uv sync
```

### Tests fail with "No module named 'pytest'"

**Cause**: Virtual environment not activated or dependencies not installed.

**Solution**:
```bash
make install
# OR
uv sync --all-extras
```

## Local Pipeline Execution Issues

### SubprocessRunner fails with "venv creation failed"

**Solution**: Use `use_venv=False` in submit_pipeline.py:
```python
runner = SubprocessRunner(use_venv=False)
```

### "docker" module not found in local execution

**Cause**: KFP requires the `docker` package even for SubprocessRunner.

**Solution**: It's in `pyproject.toml` under `pipelines` extra:
```bash
uv sync --extra pipelines
```

## Model Training Issues

### Low AUC score (< 0.5)

**Cause**: Possible data issues or feature engineering problems.

**Debug steps**:
1. Check class distribution: `df['tx_fraud'].value_counts()`
2. Verify features aren't all zeros: `df[feature_cols].describe()`
3. Check train/test split date aligns with data range
4. Ensure `scale_pos_weight` is set correctly

### Model not registered to registry

**Cause**: AUC below `eval_threshold_auc` in config.

**Solution**: Check the threshold in `fraud_detector/config/training.yaml`:
```yaml
eval_threshold_auc: 0.3  # Lower this for testing
```

### OOM (Out of Memory) errors

**Cause**: Dataset too large for local execution.

**Solution**:
- Use smaller sample: `make setup-data` (10K rows)
- Submit to Vertex AI instead: `make submit-training`
- Increase pipeline component memory in component decorator

## Monitoring Issues

### Model Monitoring job not created

**Cause**: Model not registered to Model Registry.

**Solution**: Ensure model is registered first:
```bash
# Check if model exists
gcloud ai models list --region=us-central1 --project=$PROJECT_ID
```

### Drift alerts not sending

**Cause**: Alert email not configured or drift threshold not exceeded.

**Solution**: Update `fraud_detector/config/monitoring.yaml`:
```yaml
alert_emails:
  - your-email@example.com

drift_thresholds:
  tx_amount: 0.1  # Lower threshold to trigger more easily
```

## Performance Issues

### Feature engineering very slow

**Cause**: Rolling window computation is O(n log n) per group.

**Solutions**:
- Use smaller sample for development
- Switch to SQL-based features in BigQuery
- Use BigFrames (pandas API on BigQuery)
- Distribute with Dataproc

### Pipeline takes too long

**Cause**: Sequential execution or large data volume.

**Solutions**:
- Enable caching: `enable_caching: true` in config
- Use BigQuery native features (SQL) instead of pandas
- Increase machine types in component definitions
- Parallelize independent steps

## Getting More Help

1. **Check the logs**:
   - Local: `local_outputs/*/logs/`
   - Vertex AI: Pipeline UI → Component → Logs tab

2. **Enable debug logging**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **Search existing issues**: https://github.com/your-org/predictive_mlops_demo/issues

4. **Open a new issue**: Include:
   - Error message (full traceback)
   - Steps to reproduce
   - Environment (OS, Python version, gcloud version)
   - Config files used

5. **Ask in discussions**: https://github.com/your-org/predictive_mlops_demo/discussions
