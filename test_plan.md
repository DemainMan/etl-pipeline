# Test Plan

How the pipeline is tested, and why. Run the suite with:

```bash
python -m pytest
python -m pytest --cov=src          # if pytest-cov is installed
```

## Principles

1. **No network in tests.** Every test runs against
   `tests/fixtures/sample_confirmed.csv` via a `file://` URL, so the suite is
   offline, fast (~2s) and deterministic. The HTTP path is covered by
   injecting a fake `requests.get`.
2. **No shared state.** Each test gets its own `tmp_path`; the real
   `data/` folder and `pipeline.db` are never touched.
3. **Test the data, not the implementation.** Assertions describe the output
   contract (columns, types, row counts, invariants) rather than which
   internal function produced them.
4. **Every data-quality rule has a test.** If `validate()` can reject
   something, a test proves it does.

## The fixture deliberately contains messy data

`tests/fixtures/sample_confirmed.csv` is 8 locations x 4 dates = 32 melted
rows. It contains the two problems the live dataset really has (blank
provinces, missing coordinates) plus three it does not currently have
(negative counts, blank countries, duplicate keys) — because the rules that
handle those three are the ones most likely to rot unnoticed if they are never
exercised.

| Problem in the raw file | Rows in the fixture | How the pipeline handles it | Covered by |
|---|---|---|---|
| Blank `Province/State` | 6 | Filled with `Unknown` | `TestNormaliseText`, `TestTransform::test_blank_province_becomes_unknown` |
| Whitespace around names | 1 | Stripped | `TestNormaliseText::test_whitespace_is_stripped_from_names` |
| Blank `Country/Region` | 4 (all dates) | Row dropped | `TestTransform::test_reports_what_was_dropped` |
| Negative case counts | 2 | Row dropped | `TestTransform::test_negative_rows_are_dropped`, `TestValidate::test_rejects_negative_counts` |
| Duplicate (date, country, province) | 4 | De-duplicated, last wins | `TestDropDuplicates`, `TestTransform::test_duplicate_row_kept_the_later_value` |
| Missing `Lat`/`Long` | 4 (all dates) | Kept, stored as `NULL` | `TestLoadToSqlite::test_missing_coordinates_are_stored_as_null` |

Net result: **22 clean rows** from 32 melted rows, asserted in
`TestTransform::test_writes_the_expected_row_count`.

## Coverage by module

### `src/extract.py` — `tests/test_extract.py`

- **Success path:** `file://` and `http(s)://` sources; creates missing parent
  directories; overwrites a stale file; returns size and SHA-256.
- **Failure paths:** HTTP error status, request timeout (message mentions the
  timeout value), empty body, blank body, unsupported URL scheme, missing
  local file.
- **Safety:** a failed download leaves the previous file untouched, and no
  `.part` temp file is left behind.
- **Metadata:** a timeout is always passed to `requests.get`; a custom
  `User-Agent` is sent.

### `src/transform.py` — `tests/test_transform.py`

- Each individual step is tested in isolation (`wide_to_long`, `parse_dates`,
  `coerce_numbers`, `drop_invalid_rows`, `drop_duplicates`, `add_new_cases`).
- `parse_dates` is parameterised over all three accepted formats plus junk.
- `validate` is tested against every rule it enforces, including that it
  *accepts* valid data.
- End-to-end `transform()`: exact row count, exact drop counts, column order
  and names, ISO-formatted dates, sort order, determinism, and the date-range
  filter (including that `end_date` is inclusive).
- `TransformError` for a missing file, missing columns, an empty file, and a
  file with no date columns.

### `src/load.py` — `tests/test_load.py`

- **Idempotency** (the most important property): loading the same file twice
  leaves the row count unchanged, and loading changed values with the same
  keys replaces rather than duplicates.
- **Value fidelity:** every column round-trips through SQLite unchanged.
- **SQL-injection safety:** table names must be plain identifiers; a name like
  `bad name; DROP TABLE x` is rejected before the database file is created.
- **Scale:** a 5,500-row file exercises the multi-chunk insert path.
- **Error paths:** missing CSV, CSV with the wrong columns, header-only CSV.
- **Audit trail:** `pipeline_runs` gains one `success` row per run.

### `src/run_pipeline.py` — `tests/test_pipeline.py`

- Full pipeline offline: all three artifacts created, data survives the
  round-trip, no negative counts stored.
- **Idempotency end-to-end:** two runs produce byte-identical table contents
  while the audit table records both.
- Options: `--skip-extract` (pointed at a missing source to prove nothing is
  downloaded), date range, custom table name.
- CLI: `main()` returns 0 on success, 1 on failure; `--summary` works; parser
  defaults point at the real project layout.

## Known gaps

- `load_to_sqlite` failure *recording* (the `status='failed'` branch) is not
  covered by a test, because provoking a real `sqlite3.Error` mid-insert
  needs a deliberately corrupted database file.
- Dates before 2020-01-22 are not tested; the source dataset does not contain
  any.
