"""KFP component — write predictions to BigQuery (logging step)."""

from kfp import dsl

from fraud_detector.pipelines import get_base_image


@dsl.component(base_image=get_base_image(), install_kfp_package=False)
def write_predictions_op(
    project_id: str,
    bq_dataset: str,
    predictions_table: str,
    scored_count: int,
) -> str:
    """Log the scoring result. Actual writes happen in predict_op."""
    import logging

    logger = logging.getLogger(__name__)

    table_ref = f"{project_id}.{bq_dataset}.{predictions_table}"
    logger.info("Scoring complete. %d rows written to %s", scored_count, table_ref)
    return table_ref
