# etl-pipeline
verification code: WTC-FHL8VAFY


A small, well-structured ETL pipeline that extracts data from a public CSV
source, cleans and transforms it with pandas, and loads it into a SQLite
database for analysis.

## Status: in progress — day 2 of 4

Extract and **transform** are complete: the raw wide CSV becomes a clean, tidy, validated CSV in `data/processed/`. **84 tests**, 100% coverage, running fully offline. CI runs lint, tests and smoke tests on Python 3.10–3.13.

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
handles either: each is described by a `Dataset` record in `src/config.py`.

The transform step reshapes that into a **tidy** format — one row per
place per day — which is what makes the later SQL useful.

## Architecture

```
CSV URL ──► [extract.py] ──► data/raw/ ──► [transform.py] ──► data/processed/ ──► [load.py] ──► SQLite (pipeline.db)
```

### Done so far

- **Configure** (`src/config.py`): paths, URLs and the dataset registry.
- **Extract** (`src/extract.py`): timeout, HTTP check, atomic write, SHA-256.
- **Transform** (`src/transform.py`): a readable checklist —
  read → rename → normalise text → melt wide to long → parse dates → coerce
  numbers → drop invalid rows → de-duplicate → add the daily change →
  **validate** → write. If validation fails, nothing is written.

Try it (after the extract command):

```bash
python -c "from src.transform import transform; print(transform(dataset='confirmed'))"
# -> data/processed/covid19_confirmed_daily.csv (330,327 rows)
```

## Data model

`data/processed/covid19_confirmed_daily.csv` (and, from day 3, the same shape in SQLite):

| Column | Type | Notes |
|--------|------|-------|
| `date` | TEXT | `YYYY-MM-DD`, so SQLite sorts it chronologically |
| `country` | TEXT | e.g. `Germany` |
| `province` | TEXT | e.g. `Bavaria`; `Unknown` when the source was blank |
| `latitude` | REAL | nullable — the source is missing 2 coordinates |
| `longitude` | REAL | nullable |
| `confirmed` | INTEGER | cumulative cases, never negative |
| `new_cases` | INTEGER | change since the previous day |

The load step (day 3) will use `(date, country, province)` as the primary key.

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
property of the source data rather than a bug, and the SQL notes (day 4) will measure it. For the same reason, `new_cases`
is computed across the dates that survive, so on a gapped day it can span more
than 24 hours, and it can be negative.

## Quick start

```bash
git clone https://github.com/DemainMan/etl-pipeline.git
cd etl-pipeline

python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows

pip install -r requirements-dev.txt   # pandas, requests, pytest, pytest-cov, ruff

python -m pytest                      # run the tests
ruff check src tests                  # lint
python -m pytest --cov=src            # coverage (must stay at 100%)
```

## Plan

| Day | Date | Work | Status |
|-----|------|------|--------|
| 1 | Tue 20 Oct 2026 | Scaffold, tooling, CI, config (dataset registry), extract step | ✅ done |
| 2 | Wed 21 Oct 2026 | Transform step: wide → tidy, cleaning, validation | ✅ done |
| 3 | Thu 22 Oct 2026 | Load step (idempotent SQLite + audit table) and the CLI | ⏳ next |
| 4 | Fri 23 Oct 2026 | Combined view, report, SQL notes, docs, demo — v1.0.0 | planned |

## License

MIT
