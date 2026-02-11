"""KFP component — feature engineering."""

from kfp import dsl

from fraud_detector.pipelines import get_base_image


@dsl.component(base_image=get_base_image(), install_kfp_package=False)
def feature_engineering_op(
    project_id: str,
    bq_dataset: str,
    feature_table: str,
    read_raw_sql: str,
) -> str:
    """Read raw data from BQ, compute rolling features, write feature table back to BQ."""
    import pandas as pd
    from google.cloud import bigquery

    from fraud_detector import FraudDetector

    client = bigquery.Client(project=project_id)

    query = read_raw_sql.format(project_id=project_id, bq_dataset=bq_dataset)
    df = client.query(query).to_dataframe()
    df["tx_ts"] = pd.to_datetime(df["tx_ts"])

    df = FraudDetector.compute_features(df)

    table_ref = f"{project_id}.{bq_dataset}.{feature_table}"
    from google.cloud.bigquery import LoadJobConfig

    job_config = LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    return table_ref
