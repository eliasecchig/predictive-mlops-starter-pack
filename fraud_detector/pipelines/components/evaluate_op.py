"""KFP component — model evaluation."""

from kfp import dsl

from fraud_detector.pipelines import get_base_image


@dsl.component(base_image=get_base_image(), install_kfp_package=False)
def evaluate_op(
    project_id: str,
    bq_dataset: str,
    feature_table: str,
    split_date: str,
    read_features_sql: str,
    model: dsl.Input[dsl.Model],
) -> float:
    """Evaluate trained model on holdout set. Returns AUC-ROC score."""
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

    _, test_df = FraudDetector.split(df, split_date)

    import os

    fd = FraudDetector()
    # train_op saves as model.joblib in the artifact directory
    model_path = os.path.join(os.path.dirname(model.path), "model.joblib")
    fd.load_model(model_path)
    metrics = fd.evaluate(test_df)
    return metrics["auc_roc"]
