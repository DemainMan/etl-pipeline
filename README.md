# etl-pipeline

A small, well-structured ETL pipeline that extracts data from a public CSV
source, cleans and transforms it with pandas, and loads it into a SQLite
database for analysis.

## Status: complete

All three steps are implemented, tested and documented. The suite
(`143 tests`) runs offline in about three seconds, and CI runs it on every push.

## Goal

Build a small, well-structured ETL pipeline (Extract → Transform → Load) that:

1. Downloads raw data from a public API or CSV URL.
2. Cleans and validates the data with pandas.
3. Loads the cleaned data into a SQLite database for analysis.

The project is a learning portfolio piece, focused on writing clear,
beginner-explainable code.

## Data source

COVID-19 reported cases, from the
[COVID-19 Data Repository by the Johns Hopkins Center for Health Security](https://github.com/CSSEGISandData/COVID-19).

The file is **wide** — one row per location, one column per day:

```
Province/State, Country/Region, Lat, Long, 1/22/20, 1/23/20, 1/24/20, ...
                  Afghanistan, 33.9,  67.7,        0,        0,        5, ...
                   Albania,     41.2,  20.2,        0,        0,        2, ...
```

The transform step reshapes that into a **tidy** format — one row per
place per day — which is what makes the later SQL useful.

## Architecture

```
CSV URL ──► [extract.py] ──► data/raw/ ──► [transform.py] ──► data/processed/ ──► [load.py] ──► SQLite (pipeline.db)
```

- **Extract** (`src/extract.py`): download the raw CSV and save it to
  `data/raw/`. Uses a timeout, checks the HTTP status, writes the file
  atomically so an interrupted run cannot leave a corrupt input, and returns a
  SHA-256 checksum. Supports `http(s)://` and `file://` URLs.
- **Transform** (`src/transform.py`): read the raw CSV, clean it with pandas
  and write the result to `data/processed/`.
- **Load** (`src/load.py`): insert the cleaned rows into SQLite idempotently.
- **Orchestrate** (`src/run_pipeline.py`): run the three steps in order from
  the command line.
- **Configure** (`src/config.py`): every path, URL and column name in one
  place, so the pipeline can be re-pointed without editing the logic.

## Quick start

```bash
git clone https://github.com/DemainMan/etl-pipeline.git
cd etl-pipeline

python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements.txt

python -m src.run_pipeline          # download, clean, load
python -m src.run_pipeline --summary  # describe the database
```

`sqlite3` ships with Python, so there is nothing extra to install for the load
step.

### Example output

```
INFO     Step 1/3  EXTRACT    https://raw.githubusercontent.com/CSSEGISandData/COVID-19/...
INFO     Saved data/raw/covid19_confirmed_global.csv (1,819,904 bytes, sha256=e6234a59eec4...)
INFO     Step 2/3  TRANSFORM  data/raw/covid19_confirmed_global.csv
INFO     Cleaned 289 raw row(s) into 330327 output row(s) -> data/processed/covid19_confirmed_daily.csv
INFO     Step 3/3  LOAD       pipeline.db
INFO     Load complete: 330327 rows written, 330327 total in daily_cases

==============================================================
Pipeline finished in 5.39s
==============================================================

pipeline.db:daily_cases — 330,327 rows, 201 countries, dates 2020-01-22 to 2023-03-09
```

### CLI options

| Flag | Default | Purpose |
|------|---------|---------|
| `--source` | JHU confirmed-cases CSV | Source `http(s)://` or `file://` URL |
| `--raw-path` | `data/raw/covid19_confirmed_global.csv` | Where the raw CSV is saved |
| `--processed-path` | `data/processed/covid19_confirmed_daily.csv` | Where the cleaned CSV is written |
| `--db` | `pipeline.db` | SQLite database path |
| `--table` | `daily_cases` | Target table name |
| `--start-date` / `--end-date` | none | Keep only rows in this window (inclusive) |
| `--timeout` | `30` | Download timeout in seconds |
| `--skip-extract` | off | Reuse the existing raw CSV instead of downloading |
| `--summary` | off | Print a summary of the database and exit |
| `--quiet` | off | Only show warnings and errors |

Examples:

```bash
# One year of data only
python -m src.run_pipeline --start-date 2021-01-01 --end-date 2021-12-31

# Re-run without hitting the network (e.g. while iterating on the transform)
python -m src.run_pipeline --skip-extract

# Run entirely offline from a local copy
python -m src.run_pipeline --source file:///tmp/local_copy.csv
```

## Data model

`data/processed/covid19_confirmed_daily.csv`, and the same shape in SQLite:

| Column | Type | Notes |
|--------|------|-------|
| `date` | TEXT | `YYYY-MM-DD`, so SQLite sorts it chronologically |
| `country` | TEXT | e.g. `Germany` |
| `province` | TEXT | e.g. `Bavaria`; `Unknown` when the source was blank |
| `latitude` | REAL | nullable — the source is missing 2 coordinates |
| `longitude` | REAL | nullable |
| `confirmed` | INTEGER | cumulative cases, never negative |
| `new_cases` | INTEGER | change since the previous day |

Primary key: `(date, country, province)`. Indexed on `date` and `country`.

## What the transform actually fixes

Two problems are real in the live dataset, and the rest are defensive rules
that keep the pipeline honest if the source changes:

| Problem | Where | Handling |
|---------|-------|----------|
| Blank `Province/State` | 198 of 289 raw rows (227,457 of 330,327 output rows) | Replaced with `Unknown` |
| Missing `Lat`/`Long` | 2 raw locations (2,286 output rows) | Kept, stored as `NULL` (not used as a key) |
| Wide one-column-per-day layout | 1,143 date columns | Melted to one row per day |
| Negative case counts | none in the live file, but possible if the source revises history | Row dropped |
| Rows with a blank `Country/Region` | none in the live file | Row dropped |
| Duplicate place/date pairs | none in the live file | De-duplicated, last value wins |

So a full run of the live dataset currently drops nothing — the cleaning rules
earn their place by protecting the load step, not by fixing today's data. The
test fixture reproduces all six cases in eight rows so the rules stay tested.

`validate()` then enforces the invariants the load step relies on: no nulls in
the key columns, no negative `confirmed` values, and no duplicate keys. If a
rule is broken the pipeline stops rather than writing bad data.

### A caveat worth knowing

The source revises history, so a place's cumulative total can fall on a later
day than it rose. Those corrections are small, and 362 of 330,327 output rows
(0.11%) show the cumulative series dipping — usually by 1–6 cases, the largest
being 349,116, where a reporting change rewrote a national total. It is a
property of the source data rather than a bug, and query 8d in
`sql_notes/analysis_queries.sql` measures it. For the same reason, `new_cases`
is computed across the dates that survive, so on a gapped day it can span more
than 24 hours, and it can be negative.

## Idempotency

Re-running the pipeline does **not** duplicate data. Rows are written with
`INSERT OR REPLACE` against the `(date, country, province)` primary key: an
existing row is updated, a new row is inserted. Two runs leave exactly the same
table contents, which is asserted both in the unit tests and end-to-end.

Each run is also appended to a `pipeline_runs` audit table:

```bash
sqlite3 pipeline.db "SELECT * FROM pipeline_runs ORDER BY run_id DESC LIMIT 5;"
```

```
run_id  started_at                       rows_loaded  total_rows  status
------  -------------------------------  -----------  ----------  -------
1       2026-09-28T07:13:05.912438+00:00  330327       330327      success
```

## Tests

```bash
python -m pytest
```

143 tests covering each step, the CLI, and the pipeline end-to-end. They run
**entirely offline** against `tests/fixtures/sample_confirmed.csv`, which
reproduces every data-quality problem listed above in eight rows, so the suite
is fast and deterministic. `test_plan.md` explains what is covered and why.

## SQL examples

`sql_notes/analysis_queries.sql` contains nine analysis queries against the
loaded table (worst 7-day rolling totals, first-case dates, monthly trends,
downward revisions) plus four data-quality spot checks:

```bash
sqlite3 pipeline.db < sql_notes/analysis_queries.sql
```

## Folder map

```
etl-pipeline/
├── .github/
│   └── workflows/ci.yml     # runs pytest + an offline pipeline smoke test
├── data/
│   ├── raw/                  # downloaded raw data (gitignored, .gitkeep kept)
│   └── processed/            # cleaned data output (gitignored, .gitkeep kept)
├── src/
│   ├── __init__.py
│   ├── config.py             # paths, URLs, column names, schema
│   ├── extract.py            # Step 1: download -> data/raw/
│   ├── transform.py          # Step 2: clean -> data/processed/
│   ├── load.py               # Step 3: load -> SQLite
│   └── run_pipeline.py       # orchestration + CLI
├── sql_notes/
│   └── analysis_queries.sql  # analysis + data-quality queries
├── tests/
│   ├── conftest.py           # shared fixtures (offline, tmp_path based)
│   ├── fixtures/
│   │   └── sample_confirmed.csv
│   ├── test_extract.py
│   ├── test_transform.py
│   ├── test_load.py
│   └── test_pipeline.py      # end-to-end
├── pytest.ini
├── test_plan.md
├── PROGRESS.md
├── README.md
├── requirements.txt
└── pipeline.db               # SQLite database (generated at runtime, gitignored)
```

## Roadmap

See `PROGRESS.md` for the day-by-day log. The 32-day plan (Aug 24 – Sep 24,
2026) covered the scaffold in phases 1–5 and the pipeline itself in phases
6–9; all phases are now complete.

## License

MIT
