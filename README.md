# etl-pipeline
verification code: WTC-FHL8VAFY


A small, well-structured ETL pipeline that extracts data from a public CSV
source, cleans and transforms it with pandas, and loads it into a SQLite
database for analysis.

## Status: complete — v1.0.0 (23 Oct 2026)

Extract, transform and load are implemented, tested and documented for two
datasets (confirmed cases and deaths), plus a combined `daily_summary` view
and a Markdown report. The suite (200 tests, 100% coverage) runs offline in
about three seconds, and CI runs lint, tests and smoke tests on Python
3.10–3.13 on every push.

**Demo it in one command:** `./demo.sh` (live data) or `./demo.sh --offline`
(no internet). `DEMO.md` has the talk track.

## Goal

Build a small, well-structured ETL pipeline (Extract → Transform → Load) that:

1. Downloads raw data from a public API or CSV URL.
2. Cleans and validates the data with pandas.
3. Loads the cleaned data into a SQLite database for analysis.

The project is a learning portfolio piece, focused on writing clear,
beginner-explainable code.

## Data source

COVID-19 reported **confirmed cases** and **deaths**, from the
[COVID-19 Data Repository by the Center for Systems Science and Engineering (CSSE) at Johns Hopkins University](https://github.com/CSSEGISandData/COVID-19).

The file is **wide** — one row per location, one column per day:

```
Province/State, Country/Region, Lat, Long, 1/22/20, 1/23/20, 1/24/20, ...
                  Afghanistan, 33.9,  67.7,        0,        0,        5, ...
                   Albania,     41.2,  20.2,        0,        0,        2, ...
```

Both series (`time_series_covid19_confirmed_global.csv` and
`time_series_covid19_deaths_global.csv`) share this layout, so one pipeline
handles either: pick it with `--dataset confirmed` (the default) or
`--dataset deaths`.

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
  the command line, for one dataset or (`--dataset all`) for both.
- **Report** (`src/report.py`): join cases and deaths into the
  `daily_summary` view and write a Markdown report (`--report`).
- **Configure** (`src/config.py`): every path, URL and column name in one
  place, so the pipeline can be re-pointed without editing the logic.

## Quick start

```bash
git clone https://github.com/DemainMan/etl-pipeline.git
cd etl-pipeline

python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements-dev.txt   # runtime + test/lint tools

python -m src.run_pipeline --dataset all   # download, clean, load both series
python -m src.run_pipeline --dataset all --summary   # describe the database
```

`sqlite3` ships with Python, so there is nothing extra to install for the load
step.

### Example output

```
INFO     Dataset: confirmed
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
| `--dataset` | `confirmed` | Which series to process: `confirmed`, `deaths` or `all` |
| `--source` | the dataset's JHU CSV | Source `http(s)://` or `file://` URL |
| `--raw-path` | `data/raw/covid19_<dataset>_global.csv` | Where the raw CSV is saved |
| `--processed-path` | `data/processed/covid19_<dataset>_daily.csv` | Where the cleaned CSV is written |
| `--db` | `pipeline.db` | SQLite database path |
| `--table` | `daily_cases` / `daily_deaths` | Target table name |
| `--start-date` / `--end-date` | none | Keep only rows in this window (inclusive) |
| `--timeout` | `30` | Download timeout in seconds |
| `--skip-extract` | off | Reuse the existing raw CSV instead of downloading |
| `--summary` | off | Print a summary of the database and exit |
| `--report PATH` | none | Also write a Markdown report of the database to `PATH` |
| `--quiet` | off | Only show warnings and errors |

Examples:

```bash
# Load the deaths series into the daily_deaths table
python -m src.run_pipeline --dataset deaths

# Load both series, build the daily_summary view and write a report
python -m src.run_pipeline --dataset all --report report.md

# Report on what is already loaded, without running anything
python -m src.run_pipeline --dataset all --summary --report report.md

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

The deaths dataset produces the same shape in `daily_deaths`, with `deaths`
(cumulative, never negative) and `new_deaths` in place of `confirmed` and
`new_cases`. A live run loads 330,327 rows, the same places and dates as the
confirmed series.

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

## Combined analysis

Once both tables are loaded, the pipeline creates a `daily_summary` **view**
that joins them per place and day and adds a case fatality rate:

| Column | Notes |
|--------|-------|
| `date`, `country`, `province` | the shared key |
| `confirmed`, `new_cases` | from `daily_cases` |
| `deaths`, `new_deaths` | from `daily_deaths` |
| `case_fatality_pct` | `100 × deaths / confirmed`, `NULL` when there are no cases yet |

A view stores no data of its own, so it always matches the tables and a
re-run cannot duplicate it. The view is created automatically by
`--dataset all`, or by whichever single-dataset run loads the second table.

`--dataset all` can't be combined with `--source`, `--raw-path`,
`--processed-path` or `--table`, because each series uses its own source,
files and table.

`--report report.md` writes a Markdown report: what is loaded, the latest
worldwide totals, the top 10 countries with deaths and fatality rate, the
data-quality checks re-run inside SQLite, and the last five runs. From the
live data (latest date 2023-03-09):

```
- Confirmed on 2023-03-09: 676,570,149
- Deaths on 2023-03-09: 6,881,802
- Case fatality rate: 1.02%

| # | Country | Confirmed   | Deaths    | Fatality % |
| 1 | US      | 103,802,702 | 1,123,836 | 1.08       |
| 2 | India   |  44,690,738 |   530,779 | 1.19       |
| 3 | France  |  39,866,718 |   166,176 | 0.42       |
```

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
1       2026-10-22T09:14:05.912438+00:00  330327       330327      success
```

## Tests

```bash
pip install -r requirements-dev.txt   # pytest, pytest-cov, ruff

python -m pytest                      # run the suite
ruff check src tests                  # lint
python -m pytest --cov=src            # coverage (must stay at 100%)
```

200 tests covering each step, the CLI, the report and the pipeline
end-to-end. They run **entirely offline** against
`tests/fixtures/sample_confirmed.csv` and `tests/fixtures/sample_deaths.csv`,
which reproduce every data-quality problem listed above in eight rows each, so
the suite is fast and deterministic. `test_plan.md` explains what is covered and why.

CI runs the lint, the tests with coverage enforced at 100%, and an offline
smoke test on Python 3.10, 3.11, 3.12 and 3.13. Tool settings live in
`pyproject.toml`.

## SQL examples

`sql_notes/analysis_queries.sql` contains analysis queries against the
loaded tables (worst 7-day rolling totals, first-case dates, monthly trends,
downward revisions, fatality rate by country, deaths per month, South Africa
year by year) plus data-quality spot checks, including a join check that
every case row has a matching deaths row:

```bash
sqlite3 pipeline.db < sql_notes/analysis_queries.sql
```

## Folder map

```
etl-pipeline/
├── .github/
│   └── workflows/ci.yml     # lint + tests (100% coverage) + offline smoke tests
├── data/
│   ├── raw/                  # downloaded raw data (gitignored, .gitkeep kept)
│   └── processed/            # cleaned data output (gitignored, .gitkeep kept)
├── src/
│   ├── __init__.py
│   ├── config.py             # paths, URLs, column names, schema
│   ├── extract.py            # Step 1: download -> data/raw/
│   ├── transform.py          # Step 2: clean -> data/processed/
│   ├── load.py               # Step 3: load -> SQLite
│   ├── report.py             # daily_summary view + Markdown report
│   └── run_pipeline.py       # orchestration + CLI
├── sql_notes/
│   └── analysis_queries.sql  # analysis + data-quality queries
├── tests/
│   ├── conftest.py           # shared fixtures (offline, tmp_path based)
│   ├── fixtures/
│   │   ├── sample_confirmed.csv
│   │   └── sample_deaths.csv
│   ├── test_config.py        # dataset registry
│   ├── test_extract.py
│   ├── test_transform.py
│   ├── test_load.py
│   ├── test_pipeline.py      # CLI + end-to-end
│   └── test_report.py        # daily_summary view + report
├── CHANGELOG.md              # release notes
├── DEMO.md                   # how to demo the project (talk track + Q&A)
├── demo.sh                   # guided demo: ./demo.sh or ./demo.sh --offline
├── pyproject.toml            # ruff + coverage settings
├── pytest.ini
├── test_plan.md
├── PROGRESS.md
├── README.md
├── requirements.txt
├── requirements-dev.txt      # pytest-cov + ruff
└── pipeline.db               # SQLite database (generated at runtime, gitignored)
```

## Roadmap

Built in four days — see `PROGRESS.md` for the log:

| Day | Date | Delivered |
|-----|------|-----------|
| 1 | Tue 20 Oct 2026 | Scaffold, tooling, CI, config (dataset registry), extract step |
| 2 | Wed 21 Oct 2026 | Transform step: wide → tidy, cleaning, validation |
| 3 | Thu 22 Oct 2026 | Load step (idempotent SQLite + audit table) and the CLI |
| 4 | Fri 23 Oct 2026 | Combined view, report, SQL notes, docs, demo — v1.0.0 |

Possible next steps: PostgreSQL as an alternative target, scheduling the run
(cron or GitHub Actions on a timer), and a chart of the summary view.

## License

MIT
