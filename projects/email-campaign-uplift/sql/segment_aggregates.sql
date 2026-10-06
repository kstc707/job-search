-- Per-segment, per-group sufficient statistics for the lift tests.
-- Input: a table/view named `customers` with the prepared columns (see email_uplift/data.py).
-- One row per (dimension, segment level, campaign group). Python turns these sums into
-- rates, lifts, confidence intervals and p-values (email_uplift/segments.py).
WITH long AS (
    SELECT 'Recency' AS dimension, recency_band AS level, arm, visit, conversion, spend FROM customers
    UNION ALL
    SELECT 'Past-year spend', spend_band, arm, visit, conversion, spend FROM customers
    UNION ALL
    SELECT 'Channel', channel, arm, visit, conversion, spend FROM customers
    UNION ALL
    SELECT 'Customer type', customer_type, arm, visit, conversion, spend FROM customers
    UNION ALL
    SELECT 'Past purchase', past_purchase, arm, visit, conversion, spend FROM customers
    UNION ALL
    SELECT 'Location', zip_code, arm, visit, conversion, spend FROM customers
)
SELECT
    dimension,
    level,
    arm,
    COUNT(*)                AS customers,
    SUM(visit)              AS visits,
    SUM(conversion)         AS conversions,
    SUM(spend)              AS spend_sum,
    SUM(spend * spend)      AS spend_sumsq
FROM long
GROUP BY dimension, level, arm
ORDER BY dimension, level, arm;
