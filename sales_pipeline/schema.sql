PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
    fetched INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
-- One row represents one order line, identified by a source-stable line ID.
CREATE TABLE IF NOT EXISTS sales (
    line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    sold_on TEXT NOT NULL,
    product TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
    currency TEXT NOT NULL CHECK(currency = 'USD'),
    first_run_id INTEGER NOT NULL REFERENCES runs(run_id)
);
CREATE INDEX IF NOT EXISTS sales_by_day ON sales(sold_on);
CREATE TABLE IF NOT EXISTS rejections (
    rejection_id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(run_id),
    source_position INTEGER NOT NULL,
    reason TEXT NOT NULL,
    raw_json TEXT NOT NULL
);
