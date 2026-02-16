"""Integration tests for scoring methods.

These tests require a GCP project with BigQuery access.
Set PROJECT_ID environment variable before running.
"""

import os

import pandas as pd
import pytest

# Skip all tests if no project ID is set
pytestmark = pytest.mark.skipif(
    not os.environ.get("PROJECT_ID"),
    reason="PROJECT_ID not set — skipping integration tests",
)


def test_batch_predict_produces_output():
    """predict should add fraud_probability and fraud_prediction columns."""
    import numpy as np
    from xgboost import XGBClassifier

    from fraud_detector import FraudDetector

    fd = FraudDetector()

    # Create a small model
    feature_cols = FraudDetector.feature_columns(windows=[1, 7])
    fd.model = XGBClassifier(n_estimators=5, max_depth=2)
    rng = np.random.RandomState(42)
    X = rng.rand(50, len(feature_cols))
    y = np.array([0] * 40 + [1] * 10)
    fd.model.fit(X, y)

    # Create sample data
    data = {"tx_id": range(10), "tx_ts": pd.date_range("2023-01-01", periods=10)}
    for col in feature_cols:
        data[col] = rng.rand(10)
    df = pd.DataFrame(data)

    result = fd.predict(df, feature_cols=feature_cols)
    assert "fraud_probability" in result.columns
    assert "fraud_prediction" in result.columns
    assert "scored_at" in result.columns
    assert len(result) == 10
    assert result["fraud_probability"].between(0, 1).all()
