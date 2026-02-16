"""KFP Batch Scoring Pipeline definition."""

from kfp import dsl

from fraud_detector.pipelines.components.feature_engineering_op import feature_engineering_op
from fraud_detector.pipelines.components.predict_op import predict_op
from fraud_detector.pipelines.components.write_predictions_op import write_predictions_op


@dsl.pipeline(
    name="fraud-detector-scoring",
    description="Scoring pipeline: feature engineering → predict → write predictions",
)
def scoring_pipeline(
    project_id: str,
    region: str = "us-central1",
    bq_dataset: str = "fraud_detection",
    feature_table: str = "fraud_features",
    model_display_name: str = "fraud-detector-xgb",
    predictions_table: str = "fraud_scores",
    read_raw_sql: str = "",
    read_unscored_sql: str = "",
):
    # Step 1: Feature engineering (ensures features are up-to-date)
    fe_task = feature_engineering_op(
        project_id=project_id,
        bq_dataset=bq_dataset,
        feature_table=feature_table,
        read_raw_sql=read_raw_sql,
    )

    # Step 2: Predict
    predict_task = predict_op(
        project_id=project_id,
        region=region,
        bq_dataset=bq_dataset,
        feature_table=feature_table,
        predictions_table=predictions_table,
        model_display_name=model_display_name,
        read_unscored_sql=read_unscored_sql,
    ).after(fe_task)

    # Step 3: Log result
    write_predictions_op(
        project_id=project_id,
        bq_dataset=bq_dataset,
        predictions_table=predictions_table,
        scored_count=predict_task.outputs["Output"],
    ).after(predict_task)
