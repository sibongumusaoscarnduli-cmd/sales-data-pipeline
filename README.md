# Sales data pipeline

A Python ETL pipeline that fetches sales from a paginated HTTP API, validates each record, and loads SQLite. Includes retry handling, rejected-record logs, duplicate-safe reruns, and daily-sales and top-products reports.

The bundled API serves **synthetic sales data** locally. No credentials or third-party packages are needed.

## Run

Requires Python 3.9 or newer. From the project folder:

```sh
python3 -m sales_pipeline demo
python3 -m sales_pipeline report
python3 -m unittest discover -s tests -v
```

The demo creates `var/sales.db`. Run it again to check duplicate handling: the first run inserts four sales; the second inserts none. Both reject six invalid or conflicting records. Total revenue stays at USD 29.10.

## Use the API separately

```sh
# Terminal 1
python3 -m sales_pipeline serve --port 8765

# Terminal 2
python3 -m sales_pipeline run --base-url http://127.0.0.1:8765
```

Use `--db var/experiment.db` after `demo`, `run`, or `report` for a separate database. Stop the server with Ctrl+C.

## Project layout

- `sales_pipeline/`: API client, validation, SQL schema, loading, and CLI.
- `data/`: synthetic input, including duplicates and invalid records.
- `tests/`: validation, retries, rollback, and HTTP-to-SQL tests.
- `examples/`: captured output and useful SQL queries.

## Data rules

Sales use unique line IDs and integer USD cents. Identical reruns are skipped; conflicting IDs are rejected for review. Rejections are recorded per run. All sales in a run commit together or roll back on an unexpected failure.

This is a small-data learning project: extraction uses memory, only USD and positive quantities are supported, and source corrections require review. Run one writer at a time. Publishing this repository does not host the API.
