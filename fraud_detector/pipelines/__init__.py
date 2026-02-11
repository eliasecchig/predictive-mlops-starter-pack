"""Vertex AI Pipeline definitions."""

import os


def get_base_image() -> str:
    """Return the container image URI, reading IMAGE_TAG at call time."""
    region = os.environ.get("REGION", "us-central1")
    cicd_project = os.environ.get("CICD_PROJECT_ID") or os.environ.get("PROJECT_ID", "")
    tag = os.environ.get("IMAGE_TAG", "latest")
    return f"{region}-docker.pkg.dev/{cicd_project}/fraud-detector-docker/fraud-detector:{tag}"
