# Progress log

Fresh start on Tue 20 Oct 2026. The earlier attempt is kept in git history
under the tag `backup-before-reset-2026-10-20`.

- **Tue 20 Oct 2026 (Day 1)**: Old code removed; scaffold and tooling
  (ruff, pytest-cov with a 100% coverage gate, GitHub Actions on Python
  3.10–3.13). `src/config.py` with a `Dataset` registry for confirmed cases
  and deaths. `src/extract.py`: download with a timeout and HTTP check,
  atomic write, SHA-256, `http(s)://` and `file://`. Two deliberately messy
  fixtures. **28 tests**, 100% coverage.
- **Wed 21 Oct 2026 (Day 2)**: `src/transform.py` — wide → tidy melt,
  blank provinces → `Unknown`, whitespace trimmed, invalid rows dropped with
  per-reason counts, duplicates removed (last wins), daily change column,
  `validate()` that stops bad data, optional date window. Works for both
  datasets. Live check: 289 raw rows → 330,327 tidy rows per dataset.
  **84 tests**, 100% coverage.
- **Thu 22 Oct 2026 (Day 3)**: `src/load.py` — SQLite schema with a
  `(date, country, province)` primary key, chunked `INSERT OR REPLACE`
  (idempotent), `pipeline_runs` audit table that records failures honestly.
  `src/run_pipeline.py` — CLI with `--dataset confirmed|deaths|all`, date
  window, `--skip-extract`, `--summary`; exit codes 0 / 1 / 130. Live run:
  330,327 rows in each table, 201 countries, 2020-01-22 to 2023-03-09; a
  second run leaves the counts unchanged. **172 tests**, 100% coverage.
- **Fri 23 Oct 2026 (Day 4)**: **Project complete — v1.0.0.**
  `src/report.py` — `daily_summary` view (cases + deaths + case fatality
  rate) and a Markdown report (`--report`). 16 SQL statements in
  `sql_notes/analysis_queries.sql`, all verified against the live database.
  `demo.sh` + `DEMO.md`, `test_plan.md`, `CHANGELOG.md`, final README.
  **200 tests**, 100% coverage.

## Verified end-to-end (live data, 23 Oct 2026)

- `python -m src.run_pipeline --dataset all`: 330,327 rows in `daily_cases`
  and in `daily_deaths`, 201 countries, 2020-01-22 to 2023-03-09, about 10 s.
- Re-running leaves both tables at 330,327 rows (no duplication).
- Every case row has a matching deaths row (`daily_summary` has 330,327 rows).
- Latest worldwide totals: 676,570,149 confirmed, 6,881,802 deaths, 1.02%.
- The duplicate-key, negative-count and null-key checks all return zero rows.

## Possible next steps

- PostgreSQL as an alternative target (`INSERT ... ON CONFLICT DO UPDATE`).
- Schedule the run (cron or a timed GitHub Actions workflow).
- Chart the `daily_summary` view in the report.
