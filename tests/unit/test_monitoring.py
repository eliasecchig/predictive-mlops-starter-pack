"""Unit tests for the monitoring component logic."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _mock_vertexai():
    """Mock all Vertex AI / monitoring imports used by setup_monitoring_op."""
    with (
        patch.dict("sys.modules", {
            "google.cloud.aiplatform": MagicMock(),
            "vertexai": MagicMock(),
            "vertexai.resources": MagicMock(),
            "vertexai.resources.preview": MagicMock(),
            "vertexai.resources.preview.ml_monitoring": MagicMock(),
            "vertexai.resources.preview.ml_monitoring.spec": MagicMock(),
        }),
    ):
        yield


class TestSetupMonitoringSkipConditions:
    """Test cases where monitoring setup is skipped."""

    def test_skip_when_not_registered(self):
        """Should skip when model was not registered due to low AUC."""
        from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

        result = setup_monitoring_op.python_func(
            project_id="test-project",
            region="us-central1",
            bq_dataset="fraud_detection",
            feature_table="fraud_features",
            predictions_table="fraud_scores",
            model_resource_name="NOT_REGISTERED",
            alert_emails="test@example.com",
            default_drift_threshold=0.3,
            monitoring_schedule="0 8 * * 1",
        )
        assert result == "SKIPPED:NOT_REGISTERED"

    def test_skip_when_local_only(self):
        """Should skip when running locally."""
        from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

        result = setup_monitoring_op.python_func(
            project_id="test-project",
            region="us-central1",
            bq_dataset="fraud_detection",
            feature_table="fraud_features",
            predictions_table="fraud_scores",
            model_resource_name="LOCAL_ONLY",
            alert_emails="test@example.com",
            default_drift_threshold=0.3,
            monitoring_schedule="0 8 * * 1",
        )
        assert result == "SKIPPED:LOCAL_ONLY"


@pytest.mark.usefixtures("_mock_vertexai")
class TestSetupMonitoringExecution:
    """Test cases where monitoring setup runs."""

    def test_creates_monitor_and_schedule(self):
        """Should create a model monitor and schedule when given a valid resource name."""
        mock_monitor = MagicMock()
        mock_monitor.name = "projects/123/locations/us-central1/modelMonitors/456"

        with (
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.list",
                return_value=[],
            ),
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.create",
                return_value=mock_monitor,
            ) as mock_create,
        ):
            from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

            result = setup_monitoring_op.python_func(
                project_id="test-project",
                region="us-central1",
                bq_dataset="fraud_detection",
                feature_table="fraud_features",
                predictions_table="fraud_scores",
                model_resource_name="projects/test-project/locations/us-central1/models/12345",
                alert_emails="user@example.com",
                default_drift_threshold=0.3,
                monitoring_schedule="0 8 * * 1",
            )

        assert result == mock_monitor.name
        mock_create.assert_called_once()
        mock_monitor.create_schedule.assert_called_once()

    def test_deletes_existing_monitors(self):
        """Should delete existing monitors with the same display name before creating a new one."""
        old_monitor = MagicMock()
        old_monitor.name = "projects/123/locations/us-central1/modelMonitors/old"

        new_monitor = MagicMock()
        new_monitor.name = "projects/123/locations/us-central1/modelMonitors/new"

        with (
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.list",
                return_value=[old_monitor],
            ),
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.create",
                return_value=new_monitor,
            ),
        ):
            from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

            result = setup_monitoring_op.python_func(
                project_id="test-project",
                region="us-central1",
                bq_dataset="fraud_detection",
                feature_table="fraud_features",
                predictions_table="fraud_scores",
                model_resource_name="projects/test-project/locations/us-central1/models/12345",
                alert_emails="user@example.com",
                default_drift_threshold=0.3,
                monitoring_schedule="0 8 * * 1",
            )

        old_monitor.delete.assert_called_once()
        assert result == new_monitor.name

    def test_handles_multiple_alert_emails(self):
        """Should parse comma-separated email addresses correctly."""
        mock_monitor = MagicMock()
        mock_monitor.name = "projects/123/locations/us-central1/modelMonitors/456"

        with (
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.list",
                return_value=[],
            ),
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.create",
                return_value=mock_monitor,
            ),
        ):
            from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

            result = setup_monitoring_op.python_func(
                project_id="test-project",
                region="us-central1",
                bq_dataset="fraud_detection",
                feature_table="fraud_features",
                predictions_table="fraud_scores",
                model_resource_name="projects/test-project/locations/us-central1/models/12345",
                alert_emails="a@example.com, b@example.com, c@example.com",
                default_drift_threshold=0.3,
                monitoring_schedule="0 8 * * 1",
            )

        assert result == mock_monitor.name
        # Verify schedule was created (emails are parsed inside the function)
        mock_monitor.create_schedule.assert_called_once()

    def test_non_blocking_on_error(self):
        """Monitoring failure should return error status, not raise."""
        with (
            patch(
                "vertexai.resources.preview.ml_monitoring.ModelMonitor.list",
                side_effect=RuntimeError("API error"),
            ),
        ):
            from fraud_detector.pipelines.components.monitoring_op import setup_monitoring_op

            result = setup_monitoring_op.python_func(
                project_id="test-project",
                region="us-central1",
                bq_dataset="fraud_detection",
                feature_table="fraud_features",
                predictions_table="fraud_scores",
                model_resource_name="projects/test-project/locations/us-central1/models/12345",
                alert_emails="user@example.com",
                default_drift_threshold=0.3,
                monitoring_schedule="0 8 * * 1",
            )

        assert result == "ERROR:monitoring_setup_failed"
