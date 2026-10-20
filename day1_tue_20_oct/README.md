# etl-pipeline
verification code: WTC-FHL8VAFY


A small, well-structured ETL pipeline that extracts data from a public CSV
source, cleans and transforms it with pandas, and loads it into a SQLite
database for analysis.

## Status: in progress — day 1 of 4

Scaffold, tooling and CI are in place, together with `src/config.py` (a registry describing the confirmed and deaths datasets) and a complete **extract** step. **28 tests**, 100% coverage, running fully offline. CI runs lint, tests and smoke tests on Python 3.10–3.13.

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

- **Configure** (`src/config.py`): every path, URL and column name in one
  place. A frozen `Dataset` record describes each series (URL, file paths,
  table, column names), so one pipeline can handle both.
- **Extract** (`src/extract.py`): downloads a CSV with a timeout and an HTTP
  status check, writes it **atomically** (temp file + rename, so an
  interrupted download can never corrupt an existing file) and returns its
  size and SHA-256 checksum. Supports `http(s)://` and `file://` URLs.

Try it:

```bash
python -c "from src import config; from src.extract import extract_from_url; print(extract_from_url(config.DATASETS['confirmed'].source_url, 'data/raw/covid19_confirmed_global.csv'))"
```

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
| 2 | Wed 21 Oct 2026 | Transform step: wide → tidy, cleaning, validation | ⏳ next |
| 3 | Thu 22 Oct 2026 | Load step (idempotent SQLite + audit table) and the CLI | planned |
| 4 | Fri 23 Oct 2026 | Combined view, report, SQL notes, docs, demo — v1.0.0 | planned |

## Folder map

```
etl-pipeline/
├── .github/workflows/ci.yml  # lint + tests (100% coverage) + offline smoke test
├── data/raw/                 # downloaded raw data (gitignored)
├── data/processed/           # cleaned data (gitignored)
├── src/
│   ├── config.py             # paths, URLs, dataset registry
│   └── extract.py            # Step 1: download -> data/raw/
├── tests/
│   ├── conftest.py           # shared offline fixtures
│   ├── fixtures/             # tiny, deliberately messy sample CSVs
│   ├── test_config.py
│   └── test_extract.py
├── pyproject.toml            # ruff + coverage settings
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

## License

MIT
