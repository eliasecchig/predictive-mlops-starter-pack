"""Compile and submit KFP pipelines to Vertex AI (or run locally)."""

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

from fraud_detector.config import load_config, load_sql

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Container image management
# ---------------------------------------------------------------------------


def _compute_source_hash() -> str:
    """Compute a content-based hash of source files for image tagging.

    Hashes Dockerfile, pyproject.toml, uv.lock, and all Python source files
    under fraud_detector/. If any of these change, the hash changes and a
    new image is built.
    """
    h = hashlib.sha256()
    for name in ["Dockerfile", "pyproject.toml", "uv.lock"]:
        path = PROJECT_ROOT / name
        if path.exists():
            h.update(path.read_bytes())
    for path in sorted(PROJECT_ROOT.glob("fraud_detector/**/*.py")):
        h.update(str(path.relative_to(PROJECT_ROOT)).encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _get_image_uri(tag: str) -> str:
    """Build the full Artifact Registry image URI."""
    region = os.environ.get("REGION", "us-central1")
    cicd_project = os.environ.get("CICD_PROJECT_ID") or os.environ.get("PROJECT_ID", "")
    return f"{region}-docker.pkg.dev/{cicd_project}/fraud-detector-docker/fraud-detector:{tag}"


def _image_exists(image_uri: str) -> bool:
    """Check if a Docker image tag already exists in Artifact Registry."""
    image_path, tag = image_uri.rsplit(":", 1)
    result = subprocess.run(
        ["gcloud", "artifacts", "docker", "tags", "list", image_path, f"--filter=tag={tag}", "--format=value(tag)"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and tag in result.stdout


def _docker_available() -> bool:
    """Check if the local Docker daemon is running."""
    result = subprocess.run(["docker", "info"], capture_output=True)
    return result.returncode == 0


def _build_and_push(image_uri: str) -> None:
    """Build and push the pipeline container image.

    Prefers local Docker (faster) and falls back to Cloud Build.
    Always targets linux/amd64 since Vertex AI runs on AMD64.
    """
    registry = image_uri.split("/")[0]
    cicd_project = os.environ.get("CICD_PROJECT_ID") or os.environ.get("PROJECT_ID", "")

    if _docker_available():
        print(f"Building with Docker: {image_uri}")
        subprocess.run(
            ["gcloud", "auth", "configure-docker", registry, "--quiet"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["docker", "buildx", "build", "--platform", "linux/amd64", "-t", image_uri, "--push", str(PROJECT_ROOT)],
            check=True,
        )
    else:
        print(f"Building with Cloud Build: {image_uri}")
        subprocess.run(
            ["gcloud", "builds", "submit", "--tag", image_uri, "--project", cicd_project, "--quiet", str(PROJECT_ROOT)],
            check=True,
        )

    print(f"Image ready: {image_uri}")


def ensure_image() -> None:
    """Ensure the pipeline container image is built and pushed.

    - If IMAGE_TAG is already set (CI/CD), uses it as-is — no build.
    - Otherwise computes a content hash, checks Artifact Registry,
      and builds only if the image doesn't exist yet.
    - Prefers local Docker over Cloud Build for speed.
    """
    if os.environ.get("IMAGE_TAG"):
        return  # CI/CD already built and tagged the image

    tag = _compute_source_hash()
    image_uri = _get_image_uri(tag)

    if _image_exists(image_uri):
        print(f"Image up to date: {image_uri}")
    else:
        _build_and_push(image_uri)

    # Set for BASE_IMAGE resolution when pipeline modules are imported
    os.environ["IMAGE_TAG"] = tag


# ---------------------------------------------------------------------------
# Pipeline compilation and execution
# ---------------------------------------------------------------------------


def _resolve_sql(config: dict) -> dict[str, str]:
    """Load all SQL templates referenced in the config's ``sql`` block."""
    return {key: load_sql(filename) for key, filename in config.get("sql", {}).items()}


def _enable_caching(config: dict) -> bool:
    """Return caching flag: enabled by default, disabled for prod."""
    env = os.environ.get("ENVIRONMENT", "dev").lower()
    if env == "prod":
        return False
    return config.get("enable_caching", True)


def compile_pipeline(pipeline_name: str) -> str:
    """Compile a pipeline and return the path to the compiled JSON."""
    from kfp import compiler

    if pipeline_name == "training":
        from fraud_detector.pipelines.training_pipeline import training_pipeline

        pipeline_func = training_pipeline
    elif pipeline_name == "scoring":
        from fraud_detector.pipelines.scoring_pipeline import scoring_pipeline

        pipeline_func = scoring_pipeline
    else:
        raise ValueError(f"Unknown pipeline: {pipeline_name}")

    output_path = f"{pipeline_name}_pipeline.json"
    compiler.Compiler().compile(pipeline_func=pipeline_func, package_path=output_path)
    print(f"Pipeline compiled: {output_path}")
    return output_path


def run_local(pipeline_name: str, config: dict) -> None:
    """Run a pipeline locally using KFP local runner."""
    from kfp import local

    local.init(runner=local.SubprocessRunner(use_venv=False))

    sql = _resolve_sql(config)

    if pipeline_name == "training":
        from fraud_detector.pipelines.training_pipeline import training_pipeline

        xgb_params = config.get("xgb_params", {})
        training_pipeline(
            project_id=config["project_id"],
            region=config["region"],
            bq_dataset=config["bq_dataset"],
            feature_table=config.get("feature_table", "fraud_features"),
            model_display_name=config["model_display_name"],
            split_date=config.get("train_test_split_date", "2023-06-01"),
            threshold_auc=config.get("eval_threshold_auc", 0.85),
            read_raw_sql=sql["read_raw"],
            read_features_sql=sql["read_features"],
            max_depth=xgb_params.get("max_depth", 6),
            n_estimators=xgb_params.get("n_estimators", 200),
            learning_rate=xgb_params.get("learning_rate", 0.1),
            scale_pos_weight=float(xgb_params.get("scale_pos_weight", 10.0)),
        )
    elif pipeline_name == "scoring":
        from fraud_detector.pipelines.scoring_pipeline import scoring_pipeline

        scoring_pipeline(
            project_id=config["project_id"],
            region=config["region"],
            bq_dataset=config["bq_dataset"],
            feature_table=config.get("feature_table", "fraud_features"),
            model_display_name=config["model_display_name"],
            predictions_table=config.get("predictions_table", "fraud_scores"),
            read_raw_sql=sql["read_raw"],
            read_unscored_sql=sql["read_unscored"],
        )


def submit_to_vertex(
    pipeline_name: str,
    config: dict,
    schedule_only: bool = False,
    cron_schedule: str | None = None,
) -> None:
    """Submit a compiled pipeline to Vertex AI."""
    from google.cloud import aiplatform

    project_id = config["project_id"]
    region = config["region"]
    aiplatform.init(project=project_id, location=region)

    compiled_path = compile_pipeline(pipeline_name)
    sql = _resolve_sql(config)
    caching = _enable_caching(config)

    # Build pipeline params from config
    if pipeline_name == "training":
        xgb_params = config.get("xgb_params", {})
        params = {
            "project_id": project_id,
            "region": region,
            "bq_dataset": config["bq_dataset"],
            "feature_table": config.get("feature_table", "fraud_features"),
            "model_display_name": config["model_display_name"],
            "split_date": config.get("train_test_split_date", "2023-06-01"),
            "threshold_auc": config.get("eval_threshold_auc", 0.85),
            "read_raw_sql": sql["read_raw"],
            "read_features_sql": sql["read_features"],
            "max_depth": xgb_params.get("max_depth", 6),
            "n_estimators": xgb_params.get("n_estimators", 200),
            "learning_rate": xgb_params.get("learning_rate", 0.1),
            "scale_pos_weight": xgb_params.get("scale_pos_weight", 10.0),
        }
    else:
        params = {
            "project_id": project_id,
            "region": region,
            "bq_dataset": config["bq_dataset"],
            "feature_table": config.get("feature_table", "fraud_features"),
            "model_display_name": config["model_display_name"],
            "predictions_table": config.get("predictions_table", "fraud_scores"),
            "read_raw_sql": sql["read_raw"],
            "read_unscored_sql": sql["read_unscored"],
        }

    pipeline_root = f"gs://{project_id}-fraud-detector-pipeline-root"
    display_name = config.get("pipeline_name", f"fraud-detector-{pipeline_name}")
    pipeline_sa = os.environ.get("PIPELINE_SA_EMAIL")

    if schedule_only:
        schedule = cron_schedule or config.get("schedule", "0 2 * * 0")

        job = aiplatform.PipelineJob(
            display_name=display_name,
            template_path=compiled_path,
            pipeline_root=pipeline_root,
            parameter_values=params,
            enable_caching=caching,
        )

        job.create_schedule(
            display_name=f"{display_name}-schedule",
            cron=schedule,
            service_account=pipeline_sa,
        )
        print(f"Schedule created: {display_name} — cron: {schedule}")
    else:
        job = aiplatform.PipelineJob(
            display_name=display_name,
            template_path=compiled_path,
            pipeline_root=pipeline_root,
            parameter_values=params,
            enable_caching=caching,
        )
        job.submit(service_account=pipeline_sa)
        print(f"Pipeline submitted: {display_name}")


def main():
    parser = argparse.ArgumentParser(description="Submit KFP pipelines")
    parser.add_argument("--pipeline", required=True, choices=["training", "scoring"], help="Pipeline to run")
    parser.add_argument("--local", action="store_true", help="Run locally instead of submitting to Vertex AI")
    parser.add_argument("--schedule-only", action="store_true", help="Create/update schedule without running")
    parser.add_argument("--cron-schedule", type=str, help="Override cron schedule")
    parser.add_argument("--compile-only", action="store_true", help="Compile pipeline without submitting")
    args = parser.parse_args()

    config = load_config(args.pipeline)

    if args.compile_only:
        # Set IMAGE_TAG for correct image URI in compiled output, but don't build
        if not os.environ.get("IMAGE_TAG"):
            os.environ["IMAGE_TAG"] = _compute_source_hash()
        compile_pipeline(args.pipeline)
    elif args.local:
        run_local(args.pipeline, config)
    else:
        ensure_image()  # Build + push if needed, sets IMAGE_TAG
        submit_to_vertex(args.pipeline, config, schedule_only=args.schedule_only, cron_schedule=args.cron_schedule)


if __name__ == "__main__":
    main()
