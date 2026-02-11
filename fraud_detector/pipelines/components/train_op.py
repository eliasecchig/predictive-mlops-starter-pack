"""KFP component — model training."""

from kfp import dsl

from fraud_detector.pipelines import get_base_image


@dsl.component(base_image=get_base_image(), install_kfp_package=False)
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
    model.metadata["framework"] = "xgboost"
