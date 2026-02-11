-- Read the pre-computed feature table.
-- Used by: training pipeline (train + evaluate steps).
SELECT *
FROM `{project_id}.{bq_dataset}.{feature_table}`
