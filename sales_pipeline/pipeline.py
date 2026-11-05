"""Coordinate extraction, cleaning, an atomic SQL load, and run accounting."""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .extract import fetch_orders
from .transform import clean_record, FIELDS

LOG = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(database):
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.executescript(Path(__file__).with_name('schema.sql').read_text())
    return connection


def run_pipeline(base_url, database, **fetch_options):
    db = connect(database)
    try:
        with db:
            run_id = db.execute("INSERT INTO runs(started_at,status) VALUES (?, 'running')", (now(),)).lastrowid
        counts = dict(fetched=0, inserted=0, duplicates=0, rejected=0)
        try:
            records = fetch_orders(base_url, **fetch_options)
            counts['fetched'] = len(records)
            # Sales, rejection details, and the success summary commit together.
            with db:
                for position, raw in enumerate(records, 1):
                    try:
                        row = clean_record(raw)
                        existing = db.execute('SELECT ' + ','.join(FIELDS) + ' FROM sales WHERE line_id=?', (row['line_id'],)).fetchone()
                        if existing is not None:
                            if dict(existing) != row:
                                raise ValueError('line_id already exists with different values; review source correction')
                            counts['duplicates'] += 1
                            continue
                        db.execute('INSERT INTO sales (' + ','.join(FIELDS) + ',first_run_id) VALUES (?,?,?,?,?,?,?,?)',
                                   tuple(row[key] for key in FIELDS) + (run_id,))
                        counts['inserted'] += 1
                    except ValueError as exc:
                        db.execute('INSERT INTO rejections(run_id,source_position,reason,raw_json) VALUES (?,?,?,?)',
                                   (run_id, position, str(exc), json.dumps(raw, ensure_ascii=False)))
                        counts['rejected'] += 1
                db.execute("UPDATE runs SET finished_at=?, status='success', fetched=?, inserted=?, duplicates=?, rejected=? WHERE run_id=?",
                           (now(), counts['fetched'], counts['inserted'], counts['duplicates'], counts['rejected'], run_id))
        except Exception as exc:
            # The load transaction has rolled back. Persist a separate failure audit.
            with db:
                db.execute("UPDATE runs SET finished_at=?, status='failed', fetched=?, error=? WHERE run_id=?",
                           (now(), counts['fetched'], str(exc), run_id))
            LOG.exception('Run %s failed; no sales from this run were committed', run_id)
            raise
        summary = dict(run_id=run_id, status='success', **counts)
        LOG.info('Run summary: %s', summary)
        return summary
    finally:
        db.close()


def reports(database):
    if not Path(database).is_file():
        raise ValueError('Database does not exist; run the pipeline first')
    db = sqlite3.connect(str(database))
    db.row_factory = sqlite3.Row
    try:
        daily = db.execute("SELECT sold_on, currency, SUM(quantity) AS units, SUM(quantity * unit_price_cents) AS revenue_cents FROM sales GROUP BY sold_on, currency ORDER BY sold_on").fetchall()
        products = db.execute("SELECT product, currency, SUM(quantity) AS units, SUM(quantity * unit_price_cents) AS revenue_cents FROM sales GROUP BY product, currency ORDER BY revenue_cents DESC, product LIMIT 10").fetchall()
        return {'daily_sales': [dict(row) for row in daily], 'top_products': [dict(row) for row in products]}
    finally:
        db.close()
