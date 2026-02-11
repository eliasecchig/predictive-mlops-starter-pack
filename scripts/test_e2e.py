"""End-to-end test: feature engineering → training → scoring.

Runs the full fraud_detector package against real BigQuery data.
"""

import logging
import os
import sys
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ID = os.environ.get("PROJECT_ID", "asp-test-dev")
os.environ["PROJECT_ID"] = PROJECT_ID

import pandas as pd
from google.cloud import bigquery

from fraud_detector import FraudDetector, load_config, load_sql


def main():
    config = load_config("training")
    bq_dataset = config["bq_dataset"]
    sql = {key: load_sql(fname) for key, fname in config["sql"].items()}
    client = bigquery.Client(project=PROJECT_ID)
    fd = FraudDetector()

    # ═══════════════════════════════════════════════════════════════════
    # Step 1: Feature Engineering
    # ═══════════════════════════════════════════════════════════════════
    logger.info("=" * 60)
    logger.info("STEP 1: FEATURE ENGINEERING")
    logger.info("=" * 60)

    query = sql["read_raw"].format(project_id=PROJECT_ID, bq_dataset=bq_dataset)
    df = client.query(query).to_dataframe()
    df["tx_ts"] = pd.to_datetime(df["tx_ts"])
    logger.info("Raw data shape: %s", df.shape)
    logger.info("Date range: %s to %s", df["tx_ts"].min(), df["tx_ts"].max())
    logger.info("Fraud rate: %.2f%%", df["tx_fraud"].mean() * 100)

    df = FraudDetector.compute_features(df)
    feature_cols = FraudDetector.feature_columns()
    logger.info("Features computed. Shape: %s", df.shape)
    logger.info("Feature columns (%d): %s", len(feature_cols), feature_cols[:5])

    table_ref = f"{PROJECT_ID}.{bq_dataset}.fraud_features"
    job = client.load_table_from_dataframe(df, table_ref)
    job.result()
    logger.info("Features written to BQ")

    # ═══════════════════════════════════════════════════════════════════
    # Step 2: Training
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 2: MODEL TRAINING")
    logger.info("=" * 60)

    feature_table = config.get("feature_table", "fraud_features")
    query = sql["read_features"].format(
        project_id=PROJECT_ID, bq_dataset=bq_dataset, feature_table=feature_table,
    )
    df = client.query(query).to_dataframe()
    df["tx_ts"] = pd.to_datetime(df["tx_ts"], utc=True).dt.tz_localize(None)

    split_date = config.get("train_test_split_date", "2023-06-01")
    train_df, test_df = FraudDetector.split(df, split_date)

    xgb_params = config.get("xgb_params", {})
    fd.train(train_df, xgb_params=xgb_params)
    logger.info("Model trained")

    metrics = fd.evaluate(test_df)
    logger.info("")
    logger.info("--- EVALUATION RESULTS ---")
    logger.info("  AUC-ROC:   %.4f", metrics["auc_roc"])
    logger.info("  Precision: %.4f", metrics["precision_fraud"])
    logger.info("  Recall:    %.4f", metrics["recall_fraud"])
    logger.info("  F1:        %.4f", metrics["f1_fraud"])
    logger.info("  Test size: %d", metrics["test_samples"])
    logger.info("  Fraud rate: %.2f%%", metrics["fraud_rate"] * 100)
    logger.info("  Confusion matrix: %s", metrics["confusion_matrix"])

    threshold = config.get("eval_threshold_auc", 0.85)
    if metrics["auc_roc"] >= threshold:
        logger.info("  ✓ PASS: AUC %.4f >= threshold %.4f", metrics["auc_roc"], threshold)
    else:
        logger.info("  ✗ BELOW THRESHOLD: AUC %.4f < %.4f (model would NOT be registered)", metrics["auc_roc"], threshold)

    # Save model locally
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = f"{tmpdir}/model.joblib"
        fd.save_model(model_path)
        logger.info("Model saved to %s", model_path)

    # ═══════════════════════════════════════════════════════════════════
    # Step 3: Batch Scoring (local)
    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("=" * 60)
    logger.info("STEP 3: BATCH SCORING (local)")
    logger.info("=" * 60)

    scored_df = fd.predict(test_df)
    logger.info("Scored %d transactions", len(scored_df))
    logger.info("Fraud predictions: %d (%.1f%%)",
                scored_df["fraud_prediction"].sum(),
                scored_df["fraud_prediction"].mean() * 100)
    logger.info("Score distribution:")
    logger.info("  Mean probability: %.4f", scored_df["fraud_probability"].mean())
    logger.info("  Max probability:  %.4f", scored_df["fraud_probability"].max())
    logger.info("  Min probability:  %.4f", scored_df["fraud_probability"].min())

    # ═══════════════════════════════════════════════════════════════════
    logger.info("")
    logger.info("=" * 60)
    logger.info("E2E TEST COMPLETE")
    logger.info("=" * 60)
    logger.info("  Data: %d transactions, %.1f%% fraud", len(df), df["tx_fraud"].mean() * 100)
    logger.info("  Features: %d columns", len(feature_cols))
    logger.info("  Model AUC: %.4f", metrics["auc_roc"])
    logger.info("  Scored: %d transactions", len(scored_df))


if __name__ == "__main__":
    main()
