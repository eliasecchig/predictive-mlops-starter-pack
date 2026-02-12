"""KFP component — model evaluation."""

from kfp import dsl

from fraud_detector.pipelines import pipeline_component


@pipeline_component()
def evaluate_op(
    project_id: str,
    bq_dataset: str,
    feature_table: str,
    split_date: str,
    read_features_sql: str,
    model: dsl.Input[dsl.Model],
    eval_metrics: dsl.Output[dsl.Metrics],
    classification_metrics: dsl.Output[dsl.ClassificationMetrics],
) -> float:
    """Evaluate trained model on holdout set. Returns AUC-ROC score."""
    import os

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

    fd = FraudDetector()
    model_path = os.path.join(os.path.dirname(model.path), "model.joblib")
    fd.load_model(model_path)
    metrics = fd.evaluate(test_df)

    # Log scalar metrics to Vertex AI Metrics artifact
    eval_metrics.log_metric("auc_roc", metrics["auc_roc"])
    eval_metrics.log_metric("precision_fraud", metrics["precision_fraud"])
    eval_metrics.log_metric("recall_fraud", metrics["recall_fraud"])
    eval_metrics.log_metric("f1_fraud", metrics["f1_fraud"])
    eval_metrics.log_metric("accuracy", metrics["accuracy"])
    eval_metrics.log_metric("test_samples", metrics["test_samples"])
    eval_metrics.log_metric("fraud_rate", metrics["fraud_rate"])

    # Log confusion matrix to ClassificationMetrics artifact
    cm = metrics["confusion_matrix"]
    classification_metrics.log_confusion_matrix(
        categories=["legitimate", "fraud"],
        matrix=cm,
    )

    return metrics["auc_roc"]
