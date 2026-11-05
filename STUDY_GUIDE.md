# Build this pipeline yourself

## 1. What you are learning

ETL means **extract, transform, load**. Extract gets data from a source. Transform turns it into trustworthy rows. Load stores those rows where SQL can answer business questions. A pipeline is the repeatable program joining those steps.

This project's input is an order **line**, not an entire order. An order can contain several products; each line has its own `line_id`. Choosing that grain is essential: deduplicating by `order_id` would incorrectly discard other products from the same order.

You need basic Python variables, lists, dictionaries, functions, loops, and exceptions. You can learn the remaining concepts here. Read the files in the order below and run small experiments as you go. No external packages are required: everything imported is in Python's standard library or this project.

## 2. Follow one record through the architecture

```text
synthetic_orders.json
         |
    demo_api.py  (local HTTP server, 4 records per page)
         | HTTP JSON
     extract.py (timeouts, retries, pagination)
         | list of raw Python objects
    transform.py (validate each object and normalize safe differences)
         | clean dictionaries or a reason for rejection
     pipeline.py + schema.sql
         | one SQL transaction
      SQLite database
       /     |       \
    sales   runs   rejections
         |
   daily and product reports
```

`__main__.py` is the entry point and joins these pieces. The demo launches the server in a background thread so the same Python process can make HTTP requests to it. Threads here support the demo; the ETL itself is sequential.

Take L002: product `" Pen "`, currency `" usd "`, quantity 3, price `"1.20"`. Cleaning gives product `"Pen"`, currency `"USD"`, and price 120 cents. Its revenue is `3 * 120 = 360` cents. Cleaning whitespace and letter case is safe under our rules. Inventing a missing price would not be safe, so invalid prices become rejected records.

## 3. File-by-file reading map

| File | What to understand |
| --- | --- |
| `data/synthetic_orders.json` | Eleven deliberately artificial rows, including errors and duplicates. |
| `sales_pipeline/__init__.py` | Marks the directory as a Python package. |
| `sales_pipeline/__main__.py` | Parses commands, configures logs, starts/stops the demo server, prints JSON, returns exit codes. |
| `sales_pipeline/demo_api.py` | Exposes the fixture through HTTP and slices it into pages. |
| `sales_pipeline/extract.py` | Reads all pages and bounds retry and pagination loops. |
| `sales_pipeline/transform.py` | Contains the pure `clean_record` function and ordered SQL field names. |
| `sales_pipeline/schema.sql` | Declares tables, constraints, relationships, and a date index. |
| `sales_pipeline/pipeline.py` | Creates a run, extracts, validates, deduplicates, commits, and reports. |
| `tests/test_pipeline.py` | Tests cleaning, network failures, contract failures, transactions, and a real local HTTP round trip. |
| `examples/queries.sql` | SQL you can edit and run to explore saved data. |
| `examples/first_run.json`, `second_run.json` | Captured CLI output illustrating repeatability. |
| `examples/verification.txt` | Actual verification results for this delivery. |
| `.gitignore` | Keeps generated databases, environments, and Python caches out of future commits. |
| `README.md` | Short operational instructions. |
| `STUDY_GUIDE.md` | This explanation and rebuild workbook. |

`var/` is generated when you run the program. It is not source code. The SQL database is a single file inside it. Relative paths are resolved from your Terminal's current folder, which is why the quick start asks you to enter the project folder first.

## 4. Understand the API contract

An API is an agreed way for programs to communicate. Here the request is:

```text
GET /orders?page=1
```

A response has this shape:

```json
{
  "items": [
    {"line_id":"L001", "order_id":"O001", "sold_on":"2026-01-05",
     "product":"Notebook", "quantity":2, "unit_price":"4.50", "currency":"USD"}
  ],
  "next_page": null
}
```

`null` in JSON becomes `None` in Python. A non-final page supplies the next integer page number. The included server returns up to four items per page, so the eleven-row fixture takes three requests.

`urlopen` opens the URL with a timeout. `with` closes the response even if reading fails. `json.load` turns the body into Python dictionaries and lists. Extraction checks the envelope separately from individual records: a malformed envelope stops the entire run; a bad individual record is quarantined during transformation.

The inner loop tries each page up to three times by default, with 0.2 and 0.4 second delays. It retries timeouts, connection errors, HTTP 429, and HTTP 5xx responses. A 404 is not retried. Bad JSON is not retried. The timeout is a network operation timeout, not a total whole-run deadline. This simple implementation does not honor `Retry-After`, add jitter, stream large responses, or apply a total byte limit. Those are sensible later improvements.

The outer loop limits extraction to 100 pages and requires strictly increasing consecutive page numbers. These checks stop loops or silent truncation. If page 3 fails, pages 1 and 2 are not loaded. Fetching everything before loading makes this guarantee easy to understand at the cost of memory.

## 5. Read the cleaning code

`clean_record(raw)` is a pure function: its output depends on its input, and it performs no network or database operations. It builds a new dictionary rather than changing the original. This makes it easy to test and preserves the original rejected data.

Rules:

- IDs and product names must be nonempty strings. Leading/trailing whitespace is removed. Product case is preserved: `Pen` and `pen` are distinct names in this simplified model.
- Dates must be real calendar dates written exactly as `YYYY-MM-DD`. The standard `date` parser catches impossible days.
- Quantity must be an integer from 1 through 1,000,000. `type(quantity) is int` deliberately excludes `True`, because Python otherwise treats booleans as integers.
- Prices must arrive as decimal strings, be finite and nonnegative, and be at most 1,000,000. Multiplying by 100 must produce whole cents. A value such as `1.230` is accepted because it represents exactly 123 cents; `1.234` is rejected.
- Currency is trimmed, uppercased, and required to be USD. This avoids adding unrelated currencies together.

`Decimal` interprets text such as `"1.20"` exactly. Ordinary floating-point arithmetic can produce small representation errors. Integer cents make SQL sums exact, though extremely large total datasets could eventually exceed SQLite's integer range. Quantity and price bounds constrain individual rows, not unlimited aggregate size.

A `ValueError` is the explicit signal for a bad record. The pipeline catches that error, stores the reason and raw JSON, and continues. Unexpected programming or database errors abort the load instead of being mislabeled as bad data. Extra source fields are ignored; required fields must satisfy the rules.

## 6. Understand the database and safe reruns

`schema.sql` uses `CREATE TABLE IF NOT EXISTS`, allowing repeated setup. It is initial schema setup, not a migration system for future schema changes. `sales.line_id` is a primary key: SQL cannot store two rows with the same ID.

`runs` stores each attempt and its counts. `sales.first_run_id` points to the successful run that first inserted the row. `rejections.run_id` points to the run that encountered the bad record. These are foreign keys; they are enabled on the pipeline's connection. When opening SQLite manually, enable `PRAGMA foreign_keys = ON` before writes too.

For each clean row the pipeline looks for an existing `line_id`:

1. No match: insert it.
2. Exact same cleaned values: count a duplicate and skip insertion.
3. Same ID, different cleaned values: reject it for review. Never silently replace earlier sales.

This makes repeated input **idempotent for sales**: rerunning does not inflate sales totals. Audit rows still accumulate. Within the fixture, the second L001 matches the first, while the final L001 has quantity 99 and is rejected. This policy is first-valid-value-wins, so changing source order can affect which conflicting version is retained on an initially empty database. Real source corrections need an explicit update/versioning policy.

`with db:` is a transaction boundary. A successful block commits all its changes. An unexpected exception rolls the block back. Creating the initial `running` entry is a separate committed transaction. Sales, rejection records, and the success summary are then committed together. On failure a separate update marks the run `failed`. Failed-run inserted/rejected counts remain zero because those writes were rolled back; `fetched` records the completed extraction count. If extraction fails partway, fetched is zero because no complete extraction returned.

SQL `?` placeholders pass values separately from query text. This handles quoting safely. The column names assembled into SQL come from the fixed `FIELDS` tuple, never source data.

Use one process at a time. SQLite locks and primary keys prevent silent duplicate inserts, but this teaching project does not implement scheduling, lock retries, migrations, or crash recovery. A forced kill may leave a `running` entry. Disk failure can also prevent the failure audit itself from being written.

## 7. Read the reports

A line's revenue is `quantity * unit_price_cents`. Daily sales use `GROUP BY sold_on, currency`. Top products use `GROUP BY product, currency` and descending revenue, with product name as a deterministic tie-breaker. The query returns at most ten products. These are gross item revenues: no tax, shipping, discounts, refunds, or profit calculations are represented.

For the bundled valid rows:

| Product | Units | Revenue cents |
| --- | ---: | ---: |
| Notebook | 3 | 1350 |
| Mug | 1 | 1200 |
| Pen | 3 | 360 |

Sum: 7 units and 2910 cents. January 5 contains Notebook 900 + Pen 360 = 1260 cents. January 6 contains Mug 1200 + Notebook 450 = 1650 cents.

## 8. Run and test with confidence

Run the README commands before changing anything. A new demo database gives 4 inserted, 1 duplicate, 6 rejected. Rerun gives 0 inserted, 5 duplicates, 6 rejected. In both cases fetched equals inserted + duplicates + rejected. The rejection table has twelve rows after two runs, while sales still has four.

`unittest` discovers `test_` methods in the tests folder. `assertEqual` checks an actual result against an expected one. `assertRaises` verifies a failure is intentional. `subTest` labels multiple input variants.

`patch` replaces a dependency just for a test. Network unit tests supply fake HTTP responses or exceptions, making retries fast and repeatable. They also replace `time.sleep` so no real backoff delay is needed. These tests verify timeout configuration and timeout-error handling; they do not measure real network timing. The end-to-end test uses a real loopback HTTP server and temporary SQLite database, then repeats the entire run and checks revenue. The rollback test inserts a valid row before forcing a programming error on the next row; it checks that even the first insert disappeared.

Temporary directories isolate tests from your saved data. Expected failures print stack traces through the logger; look for `OK` at the end. A test suite reporting zero tests is not a successful verification of this project.

Troubleshooting:

- `No module named sales_pipeline`: change into the folder containing README and the package.
- `python3` not found: Python must be installed before these commands work.
- Address already in use: use `serve --port 8766` and the corresponding URL. `demo` automatically picks an available port.
- Connection refused: start `serve` first or use `demo`.
- Local networking denied: the execution environment must allow listening on loopback. No public network access is needed.
- Database locked: stop any other process writing the same database and rerun.
- More duplicates than expected: you are using an existing database. Use a new `--db` filename for a fresh experiment.
- Report command fails before the first run: create the database with `demo` or `run` first.

## 9. Rebuild workbook

Create a separate folder for your rebuild, keeping this version as a reference. Work through one checkpoint at a time. Try each exercise before reading its answer.

### Exercise A — one clean row

Write a function that accepts a dictionary, strips product whitespace, validates positive integer quantity, and returns a new dictionary. Add date and currency checks, then exact cents conversion. Run it on the L002 record.

**Checkpoint:** product `Pen`, quantity 3, currency USD, price 120 cents. Invalid quantity should raise `ValueError`; the original input should still contain whitespace. Compare your code with `clean_record` only after trying.

### Exercise B — turn a fixture into an API

Start with the provided JSON file. Write an HTTP handler that returns its first four rows. Add page parsing and `next_page`.

**Checkpoint:** pages 1, 2, 3 have 4, 4, 3 rows. The last `next_page` is null. The slicing formula is `start = (page - 1) * 4`; the slice is `records[start:start + 4]`. Bind to `127.0.0.1`, keeping the learning server local.

### Exercise C — extract multiple pages

Write one request first. Parse its JSON and print the items count. Then loop until `next_page` is null. Reject malformed envelopes and page loops.

**Checkpoint:** eleven records are returned in source order. Replacing `next_page` with the current page raises an error instead of looping forever. Compare with `fetch_orders`.

### Exercise D — store valid rows

Create a SQLite table with the seven clean fields. Insert values using placeholders. Select all rows back. Add a primary key, then duplicate checking and conflicting-value rejection.

**Checkpoint:** after all fixture records, four sales exist. Repeating the input still leaves four. Using only `INSERT OR IGNORE` is insufficient: it would hide conflicting IDs without an explanation.

### Exercise E — retain rejected input

Add a rejections table containing run ID, source position, reason, and raw JSON. Catch only the expected validation errors around each record.

**Checkpoint:** six rejections per run: negative quantity, impossible date, nonfinite price, empty product, unsupported currency, and conflicting L001. The repeated identical L001 is a duplicate, not a rejection.

### Exercise F — add transactions and run history

Create a run before extraction. Wrap all loads in one transaction. Force an unexpected exception after inserting one valid row.

**Checkpoint:** zero new sales remain and run status is failed. An error during extraction must also leave pre-existing sales untouched. Compare against the two failure tests in `PipelineTests`.

### Exercise G — retries without hiding failures

Retry a temporary 503 response, then simulate a successful response. Add increasing delays, a maximum attempt count, and a timeout.

**Checkpoint:** a 503 followed by success makes two requests. Three timeouts produce failure after three requests, not an infinite loop. A 404 makes only one request. Add a new test before changing behavior.

### Exercise H — write your own SQL report

Compute total revenue and revenue per product. Then filter daily sales to January 6.

**Answer:** total revenue is 2910 cents. The date-filtered query is:

```sql
SELECT SUM(quantity * unit_price_cents) AS revenue_cents
FROM sales WHERE sold_on = '2026-01-06';
```

It returns 1650. Add `GROUP BY product` to a product query, not the date-only total query.

### Exercise I — extend the data safely

In your rebuild copy, append a new unique line L005 for two mugs at USD 12.00 on January 7. Keep all other rows unchanged. Run into an existing database from the original demo.

**Checkpoint:** fetched 12, inserted 1, duplicates 5, rejected 6. Sales contains five rows, total revenue becomes 5310 cents, and January 7 revenue is 2400 cents. A second run inserts zero. Change L005's price afterward: it should be rejected as a conflicting ID, not silently overwrite history.

## 10. Explain the project independently

Practice answering these without reading the source:

- Why is line ID the primary key instead of order ID? One order can have multiple lines.
- Why keep invalid data? You need enough evidence to repair the source and explain omissions.
- Why can a run succeed with rejected records? Success means the pipeline completed under its rules; counts expose data-quality problems separately.
- Why use integer cents? Exact arithmetic and explicit currency semantics.
- Why extract everything before loading? Easy all-or-nothing behavior, with a memory tradeoff.
- Why is mocking not enough? A real HTTP-to-SQL test catches integration mistakes mocks may conceal.
- What makes reruns safe? Stable source IDs, equality checks, a primary key, and transaction boundaries.

A truthful portfolio description: “Built a Python ETL pipeline against a synthetic local sales API with pagination, bounded retries, validation, rejected-record auditing, duplicate-safe SQLite loading, SQL reporting, and automated tests.” Do not describe the fixture as real customer data.

For a later version, choose one addition at a time: a real API adapter, incremental date windows, product IDs, explicit refund handling, or source correction history. A public API will have its own contract and availability; map it to this project's fields rather than assuming its data is already sales data. First write a test describing the behavior you want, then implement it.
