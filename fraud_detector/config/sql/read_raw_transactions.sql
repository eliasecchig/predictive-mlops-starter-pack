-- Read raw transactions joined with fraud labels.
-- Used by: training pipeline (feature engineering step).
SELECT
    t.tx_id,
    t.tx_ts,
    t.customer_id,
    t.terminal_id,
    t.tx_amount,
    COALESCE(l.tx_fraud, 0) AS tx_fraud
FROM `{project_id}.{bq_dataset}.tx` AS t
LEFT JOIN `{project_id}.{bq_dataset}.txlabels` AS l
    ON t.tx_id = l.tx_id
ORDER BY t.tx_ts
