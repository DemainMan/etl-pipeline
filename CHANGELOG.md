# Changelog

All notable changes to this project. Versions follow
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-10-23

First release, built in four days (20–23 Oct 2026).

### Added
- **Extract** (`src/extract.py`): download with a timeout, HTTP status check,
  atomic write and SHA-256 checksum; `http(s)://` and `file://` sources.
- **Transform** (`src/transform.py`): wide → tidy reshape, text clean-up,
  invalid-row and duplicate removal with per-reason counts, daily change,
  validation that stops bad data, optional date window.
- **Load** (`src/load.py`): SQLite table with a `(date, country, province)`
  primary key, idempotent chunked `INSERT OR REPLACE`, `pipeline_runs` audit
  table.
- **Two datasets** via a `Dataset` registry in `src/config.py`: confirmed
  cases (`daily_cases`) and deaths (`daily_deaths`).
- **CLI** (`python -m src.run_pipeline`): `--dataset confirmed|deaths|all`,
  `--start-date/--end-date`, `--skip-extract`, `--summary`, `--report`,
  `--quiet`, `--version`; exit codes 0 / 1 / 130.
- **Combined analysis** (`src/report.py`): `daily_summary` view with a case
  fatality rate, and a Markdown report.
- `sql_notes/analysis_queries.sql`: analysis and data-quality queries.
- 200 offline tests at 100% coverage; GitHub Actions CI on Python 3.10–3.13
  with lint, coverage gate, smoke tests and the offline demo.
- `demo.sh` (guided demo, live or `--offline`) and `DEMO.md` (talk track).

### Verified
- Live `--dataset all`: 330,327 rows in each table, 201 countries,
  2020-01-22 to 2023-03-09; idempotent on re-run.
