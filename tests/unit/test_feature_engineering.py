"""Unit tests for feature engineering methods."""

import pandas as pd
import pytest

from fraud_detector import FraudDetector


@pytest.fixture
def sample_transactions():
    """Create a small sample transaction DataFrame."""
    return pd.DataFrame(
        {
            "tx_id": range(10),
            "tx_ts": pd.date_range("2023-01-01", periods=10, freq="D"),
            "customer_id": [1, 1, 1, 2, 2, 1, 2, 1, 2, 1],
            "terminal_id": [100, 100, 101, 100, 101, 100, 100, 101, 101, 100],
            "tx_amount": [10.0, 20.0, 30.0, 40.0, 50.0, 15.0, 25.0, 35.0, 45.0, 55.0],
            "tx_fraud": [0, 0, 0, 1, 0, 0, 0, 1, 0, 0],
        }
    )


def test_feature_columns():
    """Feature columns should include tx_amount + rolling aggregations."""
    cols = FraudDetector.feature_columns()
    assert "tx_amount" in cols
    # 2 groups (customer, terminal) * 4 windows * 3 aggs = 24 + 1 (tx_amount) = 25
    assert len(cols) == 25


def test_feature_columns_custom_windows():
    """Custom windows should produce the right number of features."""
    cols = FraudDetector.feature_columns(windows=[1, 7])
    # 2 groups * 2 windows * 3 aggs = 12 + 1 = 13
    assert len(cols) == 13


def test_compute_features_shape(sample_transactions):
    """compute_features should add rolling feature columns."""
    df = FraudDetector.compute_features(sample_transactions, windows=[1, 7])
    feature_cols = FraudDetector.feature_columns(windows=[1, 7])
    for col in feature_cols:
        assert col in df.columns, f"Missing column: {col}"
    assert len(df) == len(sample_transactions)


def test_compute_features_no_nulls_in_tx_amount(sample_transactions):
    """tx_amount should never be null after feature engineering."""
    df = FraudDetector.compute_features(sample_transactions, windows=[1])
    assert df["tx_amount"].isna().sum() == 0


def test_compute_features_rolling_values(sample_transactions):
    """Rolling features for customer_id should be computed."""
    df = FraudDetector.compute_features(sample_transactions, windows=[1])
    assert "count_tx_amount_1d_customer" in df.columns
    assert "avg_tx_amount_1d_customer" in df.columns
    assert "max_tx_amount_1d_customer" in df.columns
