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

## Next

- Fri 23 Oct: report, SQL notes, docs, demo, release v1.0.0
