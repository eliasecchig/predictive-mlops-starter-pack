"""KFP component -- conditional model registration."""

from kfp import dsl

from fraud_detector.pipelines import pipeline_component


@pipeline_component()
def register_op(
    project_id: str,
    region: str,
    model_display_name: str,
    model: dsl.Input[dsl.Model],
    auc_roc: float,
    threshold_auc: float,
) -> str:
    """Register model to Vertex AI Model Registry if AUC exceeds threshold."""
    import logging
    from google.cloud import aiplatform

    logger = logging.getLogger(__name__)
    aiplatform.init(project=project_id, location=region)

    logger.info("-" * 60)
    logger.info("[REG] STEP: Model Registration")
    logger.info("-" * 60)

    if auc_roc < threshold_auc:
        logger.warning("[WARN] AUC %.4f < threshold %.4f -- model NOT registered", auc_roc, threshold_auc)
        return "NOT_REGISTERED"

    # Local runs: model.uri is a local path, skip Vertex registration
    if not model.uri.startswith("gs://"):
        logger.info(
            "[LOCAL] Local run -- skipping Vertex registration (AUC %.4f, model at %s)",
            auc_roc,
            model.uri,
        )
        return "LOCAL_ONLY"

    # 1. Search for an existing model with this display name
    # We filter by display_name to find if we've registered this before.
    existing_models = aiplatform.Model.list(
        filter=f'display_name="{model_display_name}"',
        order_by="create_time desc"
    )

    parent_model_id = None
    if existing_models:
        # We found at least one model with this name. 
        # Pick the most recent one to add a version to.
        parent_model_id = existing_models[0].resource_name
        logger.info(f"Found existing model {parent_model_id}. Registering as a new version.")
    else:
        logger.info(f"No model named '{model_display_name}' found. Creating a new Model resource.")
    
    # 2. Upload the model
    # By passing parent_model_id to 'parent_model', Vertex AI handles the versioning logic.
    # artifact_uri must be a directory; model.uri points to the file inside it
    artifact_dir = model.uri.rsplit("/", 1)[0]
    
    registered = aiplatform.Model.upload(
        display_name=model_display_name,
        artifact_uri=artifact_dir,
        serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest",
        parent_model=parent_model_id,  # None = New Model, ID = New Version
        labels={"auc_roc": str(round(auc_roc, 4)).replace(".", "_")},
        version_description=f"Pipeline run AUC: {auc_roc:.4f}",
        is_default_version=False,
    )
    
    logger.info("[OK] Model registered: %s (resource: %s)", model_display_name, registered.resource_name)
    return registered.resource_name
