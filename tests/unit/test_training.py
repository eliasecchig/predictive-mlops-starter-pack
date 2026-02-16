"""Unit tests for training methods."""

import tempfile
from pathlib import Path

import joblib
import pandas as pd
import pytest
from xgboost import XGBClassifier

from fraud_detector import FraudDetector


@pytest.fixture
def fd():
    """Create a FraudDetector instance for testing."""
    return FraudDetector()


@pytest.fixture
def sample_feature_df():
    """Create a sample feature DataFrame with all required columns."""
    n = 200
    feature_cols = FraudDetector.feature_columns(windows=[1, 7])
    data = {
        "tx_ts": pd.date_range("2023-01-01", periods=n, freq="D"),
        "tx_fraud": [0] * 180 + [1] * 20,
    }
    import numpy as np

    rng = np.random.RandomState(42)
    for col in feature_cols:
        data[col] = rng.rand(n)
    return pd.DataFrame(data)


def test_split(sample_feature_df):
    """Split should separate data by date."""
    train, test = FraudDetector.split(sample_feature_df, "2023-06-01")
    assert len(train) > 0
    assert len(test) > 0
    assert train["tx_ts"].max() < pd.Timestamp("2023-06-01")
    assert test["tx_ts"].min() >= pd.Timestamp("2023-06-01")


def test_train(fd, sample_feature_df):
    """Model should train without errors and be an XGBClassifier."""
    feature_cols = FraudDetector.feature_columns(windows=[1, 7])
    fd.train(sample_feature_df, xgb_params={"n_estimators": 10, "max_depth": 3}, feature_cols=feature_cols)
    assert isinstance(fd.model, XGBClassifier)


def test_evaluate(fd, sample_feature_df):
    """Evaluation should return expected metric keys."""
    feature_cols = FraudDetector.feature_columns(windows=[1, 7])
    train, test = FraudDetector.split(sample_feature_df, "2023-06-01")
    fd.train(train, xgb_params={"n_estimators": 10, "max_depth": 3}, feature_cols=feature_cols)
    metrics = fd.evaluate(test, feature_cols=feature_cols)

    assert "auc_roc" in metrics
    assert "precision_fraud" in metrics
    assert "recall_fraud" in metrics
    assert "confusion_matrix" in metrics
    assert 0 <= metrics["auc_roc"] <= 1


def test_save_model(fd):
    """Model should be saveable and loadable."""
    import numpy as np

    fd.model = XGBClassifier(n_estimators=5)
    X = np.random.rand(20, 3)
    y = np.array([0] * 15 + [1] * 5)
    fd.model.fit(X, y)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/model.joblib"
        fd.save_model(path)
        assert Path(path).exists()
        loaded = joblib.load(path)
        assert isinstance(loaded, XGBClassifier)
