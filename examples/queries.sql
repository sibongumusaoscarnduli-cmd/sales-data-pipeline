-- Money remains in exact integer cents in storage and calculations.
SELECT sold_on, currency, SUM(quantity) AS units,
       SUM(quantity * unit_price_cents) AS revenue_cents
FROM sales GROUP BY sold_on, currency ORDER BY sold_on;

SELECT product, currency, SUM(quantity) AS units,
       SUM(quantity * unit_price_cents) AS revenue_cents
FROM sales GROUP BY product, currency
ORDER BY revenue_cents DESC, product LIMIT 10;

SELECT run_id, status, fetched, inserted, duplicates, rejected, error
FROM runs ORDER BY run_id;

SELECT run_id, source_position, reason, raw_json
FROM rejections ORDER BY rejection_id;
