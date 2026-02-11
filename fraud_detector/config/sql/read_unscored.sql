-- Read feature rows that have not yet been scored.
-- Used by: scoring pipeline (predict step).
SELECT f.*
FROM `{project_id}.{bq_dataset}.{feature_table}` AS f
LEFT JOIN `{project_id}.{bq_dataset}.{predictions_table}` AS p
    ON f.tx_id = p.tx_id
WHERE p.tx_id IS NULL
