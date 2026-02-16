"""Vertex AI Pipeline definitions."""

import os


def get_base_image() -> str:
    """Return the container image URI, reading IMAGE_TAG at call time."""
    region = os.environ.get("REGION", "us-central1")
    cicd_project = os.environ.get("CICD_PROJECT_ID") or os.environ.get("PROJECT_ID", "")
    tag = os.environ.get("IMAGE_TAG", "latest")
    return f"{region}-docker.pkg.dev/{cicd_project}/fraud-detector-docker/fraud-detector:{tag}"


def get_ar_index_url() -> str:
    """Return the Artifact Registry Python simple index URL."""
    region = os.environ.get("REGION", "us-central1")
    project = os.environ.get("CICD_PROJECT_ID") or os.environ.get("PROJECT_ID", "")
    return f"https://{region}-python.pkg.dev/{project}/fraud-detector-python/simple/"


def get_code_package() -> str:
    """Return the pinned fraud-detector package specifier."""
    version = os.environ.get("CODE_VERSION", "0.1.0")
    return f"fraud-detector=={version}"


def pipeline_component(**kwargs):
    """Decorator wrapping ``dsl.component`` with project defaults.

    Sets base_image, disables KFP package install, and configures
    ``packages_to_install`` to pull the fraud-detector wheel from
    Artifact Registry with ``--no-deps`` (all deps are in the base image).

    Any extra ``kwargs`` are forwarded to ``dsl.component()``.
    """
    from kfp import dsl

    kwargs.setdefault("base_image", get_base_image())
    kwargs.setdefault("install_kfp_package", False)
    kwargs.setdefault("packages_to_install", ["--no-deps", get_code_package()])
    kwargs.setdefault("pip_index_urls", [get_ar_index_url()])

    return dsl.component(**kwargs)
