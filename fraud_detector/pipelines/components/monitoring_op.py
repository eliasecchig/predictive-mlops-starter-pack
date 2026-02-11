"""KFP component — Vertex AI Model Monitoring v2 setup."""

from kfp import dsl

from fraud_detector.pipelines import get_base_image


@dsl.component(base_image=get_base_image(), install_kfp_package=False)
def setup_monitoring_op(
    project_id: str,
    region: str,
    bq_dataset: str,
    feature_table: str,
    predictions_table: str,
    model_resource_name: str,
    alert_emails: str,
    default_drift_threshold: float = 0.3,
    monitoring_schedule: str = "0 8 * * 1",
) -> str:
    """Set up Vertex AI Model Monitoring v2 for a registered model.

    Configures feature drift detection (Jensen-Shannon divergence) comparing
    the training features table against the predictions/scores table.

    Args:
        project_id: GCP project ID.
        region: GCP region.
        bq_dataset: BigQuery dataset name.
        feature_table: BigQuery table with training features (baseline).
        predictions_table: BigQuery table with prediction outputs (target).
        model_resource_name: Full Vertex AI model resource name from register_op.
        alert_emails: Comma-separated email addresses for drift alerts.
        default_drift_threshold: Default Jensen-Shannon divergence threshold.
        monitoring_schedule: Cron expression for monitoring schedule.

    Returns:
        Monitor resource name, or skip/error status string.
    """
    import logging

    logger = logging.getLogger(__name__)

    # Skip if model was not registered
    if model_resource_name in ("NOT_REGISTERED", "LOCAL_ONLY"):
        logger.info("Skipping monitoring setup — model status: %s", model_resource_name)
        return f"SKIPPED:{model_resource_name}"

    try:
        from google.cloud import aiplatform
        from vertexai.resources.preview.ml_monitoring import (
            ModelMonitor,
            ModelMonitoringSchema,
            spec as monitoring_spec,
        )

        from fraud_detector import FraudDetector

        aiplatform.init(project=project_id, location=region)

        # Build schema: all feature columns are float, plus prediction field
        feature_cols = FraudDetector.feature_columns()
        feature_fields = {col: "float" for col in feature_cols}
        feature_fields["fraud_probability"] = "float"

        schema = ModelMonitoringSchema(
            feature_fields=feature_fields,
            prediction_fields={"fraud_prediction": "integer"},
        )

        # Extract model ID from resource name for display name
        # Format: projects/.../models/<model_id> or projects/.../models/<model_id>/versions/<ver>
        model_id = model_resource_name.split("/models/")[-1].split("/")[0]
        monitor_display_name = f"fraud-detector-monitor-{model_id}"

        # Clean up any existing monitor with the same display name
        existing_monitors = ModelMonitor.list(
            filter=f'display_name="{monitor_display_name}"',
        )
        for old_monitor in existing_monitors:
            logger.info("Deleting existing monitor: %s", old_monitor.name)
            old_monitor.delete()

        # Create model monitor
        monitor = ModelMonitor.create(
            project=project_id,
            location=region,
            display_name=monitor_display_name,
            model_name=model_resource_name,
            model_monitoring_schema=schema,
        )
        logger.info("Model monitor created: %s", monitor.name)

        # Configure data drift detection spec
        drift_spec = monitoring_spec.DataDriftSpec(
            default_categorical_alert_condition=monitoring_spec.AlertCondition(
                threshold=default_drift_threshold,
            ),
            default_numeric_alert_condition=monitoring_spec.AlertCondition(
                threshold=default_drift_threshold,
            ),
        )

        # Parse email list
        emails = [e.strip() for e in alert_emails.split(",") if e.strip()]
        notification_spec = monitoring_spec.NotificationSpec(
            email_config=monitoring_spec.EmailConfig(user_emails=emails),
        )

        # BigQuery data sources
        baseline_uri = f"bq://{project_id}.{bq_dataset}.{feature_table}"
        target_uri = f"bq://{project_id}.{bq_dataset}.{predictions_table}"

        output_spec = monitoring_spec.OutputSpec(
            gcs_base_dir=f"gs://{project_id}-fraud-detector-pipeline-root/monitoring",
        )

        # Create scheduled monitoring run
        monitor.create_schedule(
            display_name=f"{monitor_display_name}-schedule",
            cron=monitoring_schedule,
            baseline_dataset=monitoring_spec.MonitoringInput(
                endpoints=[],
                batch_input=monitoring_spec.BatchInput(bigquery_uri=baseline_uri),
            ),
            target_dataset=monitoring_spec.MonitoringInput(
                endpoints=[],
                batch_input=monitoring_spec.BatchInput(bigquery_uri=target_uri),
            ),
            data_drift_spec=drift_spec,
            notification_spec=notification_spec,
            output_spec=output_spec,
        )
        logger.info("Monitoring schedule created for %s", monitor.name)

        return monitor.name

    except Exception:
        logger.exception("Monitoring setup failed (non-blocking)")
        return "ERROR:monitoring_setup_failed"
