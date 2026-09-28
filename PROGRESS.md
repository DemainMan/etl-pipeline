# Progress Log

- **Aug 26 (Day 3)**: Repo scaffolded — folder skeleton, requirements, ETL module stubs.
- **Sep 3 (Day 3)**: README expanded with goal, architecture, folder map.
- **Sep 8 (Day 11)**: Roadmap reviewed — scaffold confirmed, ETL work starts Sep 13.
- **Sep 9 (Day 17)**: On schedule; extract step begins Sep 17.
- **Sep 28 (Day 37)**: **Project complete.** All three ETL steps implemented,
  tests written, docs finished.

## What was built (Sep 28)

- `src/config.py` — paths, source URL, column mappings and the output contract
  in one place.
- `src/extract.py` — download with a timeout and an HTTP status check, atomic
  write, SHA-256 checksum, `http(s)` and `file://` support.
- `src/transform.py` — wide → tidy reshape, 5 data-quality fixes, explicit
  validation that fails loudly.
- `src/load.py` — SQLite schema with a `(date, country, province)` primary key,
  `INSERT OR REPLACE` upserts for idempotency, and a `pipeline_runs` audit table.
- `src/run_pipeline.py` — argparse CLI with 10 options and a summary report.
- `tests/` — 143 tests, fully offline, running in ~3s. `test_plan.md` explains
  the coverage and the known gaps.
- `sql_notes/analysis_queries.sql` — 9 analysis queries and 4 data-quality
  checks, all verified to run against the loaded database.
- `.github/workflows/ci.yml` — pytest plus an offline end-to-end smoke test,
  including a double run to prove idempotency.

## Verified end-to-end

- Full run against the live JHU dataset: 289 raw rows → **330,327 clean rows**,
  201 countries, 2020-01-22 to 2023-03-09, in ~5.4s.
- Two consecutive runs leave the table at 330,327 rows (no duplication).
- All 12 SQL statements execute; the duplicate-key, negative-count and
  null-key spot checks each return zero rows.

## Next steps (optional)

- Point the pipeline at the deaths dataset to load a second table.
- Swap SQLite for PostgreSQL to practise parameterized inserts.
- Add `pytest-cov` and `ruff` to tighten quality gates.
