"""KFP component — model training."""

from kfp import dsl

from fraud_detector.pipelines import pipeline_component


@pipeline_component()
def train_op(
    project_id: str,
    bq_dataset: str,
    feature_table: str,
    split_date: str,
    read_features_sql: str,
    model: dsl.Output[dsl.Model],
    max_depth: int = 6,
    n_estimators: int = 200,
    learning_rate: float = 0.1,
    scale_pos_weight: float = 10.0,
) -> None:
    """Train XGBoost classifier; model artifact is stored automatically by Vertex."""
    import pandas as pd
    from google.cloud import bigquery

    from fraud_detector import FraudDetector

    client = bigquery.Client(project=project_id)
    query = read_features_sql.format(
        project_id=project_id,
        bq_dataset=bq_dataset,
        feature_table=feature_table,
    )
    df = client.query(query).to_dataframe()
    df["tx_ts"] = pd.to_datetime(df["tx_ts"], utc=True).dt.tz_localize(None)

    train_df, _ = FraudDetector.split(df, split_date)

    xgb_params = {
        "max_depth": max_depth,
        "n_estimators": n_estimators,
        "learning_rate": learning_rate,
        "scale_pos_weight": scale_pos_weight,
        "eval_metric": "auc",
        "objective": "binary:logistic",
    }

    import os

    fd = FraudDetector()
    fd.train(train_df, xgb_params=xgb_params)

    # Save as model.joblib in artifact directory (required by sklearn serving container)
    artifact_dir = os.path.dirname(model.path)
    os.makedirs(artifact_dir, exist_ok=True)
    fd.save_model(os.path.join(artifact_dir, "model.joblib"))

    # Model metadata
    model.metadata["framework"] = "xgboost"
    for k, v in xgb_params.items():
        model.metadata[k] = v
    model.metadata["train_samples"] = len(train_df)
    model.metadata["feature_count"] = len(fd.feature_columns())
    fraud_rate = train_df["tx_fraud"].mean() if "tx_fraud" in train_df.columns else 0.0
    model.metadata["fraud_rate"] = float(fraud_rate)
