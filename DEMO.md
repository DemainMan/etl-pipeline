# Demo guide

A plan for a **7–8 minute demo** with a talk track, the files to open, and
answers to likely questions. Practise it out loud two or three times with
`./demo.sh` before the real thing.

---

## 0. Before the demo (5 minutes, the day before as well)

```bash
cd etl-pipeline
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt

python -m pytest                    # 200 passed
ruff check src tests                # All checks passed!
./demo.sh --offline --no-pause      # dry run, no internet needed
```

Checklist:
- [ ] Terminal font is large (Ctrl/Cmd +). Clear the screen: `clear`.
- [ ] Editor open with `src/` visible: `config.py`, `transform.py`, `load.py`.
- [ ] GitHub repo open in a browser tab, on the **Actions** page (green ticks).
- [ ] Internet works? If not, use `./demo.sh --offline`. Everything still runs.
- [ ] Delete old output: `rm -rf demo_output`.

---

## 1. The pitch (30 seconds)

> "This is an ETL pipeline in Python. It **extracts** COVID-19 data published
> by Johns Hopkins University, **transforms** it with pandas into a clean,
> tidy table, and **loads** it into SQLite so it can be analysed with SQL.
> It handles two datasets, confirmed cases and deaths, joins them, and
> produces a report. It's safe to re-run, has 200 tests at 100% coverage,
> and CI runs on every push."

Show the architecture line from the README:

```
CSV URL ──► extract.py ──► data/raw/ ──► transform.py ──► data/processed/ ──► load.py ──► SQLite
```

---

## 2. Run the guided demo

```bash
./demo.sh          # or ./demo.sh --offline
```

It stops before every step. Press **Enter** when you've said your line.

| Step | What appears | What to say |
|---|---|---|
| **1. Tests** | `200 passed` in ~3 s | "Every step is tested **offline**, against tiny CSV fixtures that contain every data problem I handle: blank provinces, missing coordinates, negative counts, blank countries, duplicates." |
| **2. Confirmed cases** | 289 raw rows → 330,327 clean rows in ~5 s | "Extract downloads with a timeout, checks the HTTP status and writes the file **atomically**, so a dropped connection can't leave a half-written file. The SHA-256 lets me prove which file I loaded." |
| **3. Wide → tidy** | raw has one column per day; clean has one row per day | "The source is **wide**: 1,143 date columns. I **melt** it to one row per place per day. That's what makes SQL like `GROUP BY month` possible." |
| **4. Idempotency** | row count before = after, two rows in `pipeline_runs` | "Running it twice doesn't duplicate anything. The table has a primary key on date, country and province, and I use `INSERT OR REPLACE`. Every run is also logged in an **audit table**." |
| **5. Deaths** | 330,327 rows into `daily_deaths` | "Adding a second dataset needed **no new logic**. In `config.py` a `Dataset` describes the URL, paths, table and column names, and the same functions handle both." |
| **6. SQL** | top 5 countries with fatality %, plus South Africa per year | "Once both are loaded, a `daily_summary` **view** joins them and adds a case fatality rate. A view stores no data, so it can never get out of sync." |
| **7. Report** | Markdown report with totals, top 10, PASS checks, runs | "This report re-checks the data-quality rules **inside the database**: no duplicate keys, no negative counts, no null keys. All PASS." |
| **8. Failing safely** | clear `ERROR` line, `exit code: 1` | "Bad input gives one clear error message and exit code 1, never a stack trace. That's what a scheduler or CI needs." |

---

## 3. Show the code (2 minutes, pick 2 or 3)

| Open | Point at | Say |
|---|---|---|
| `src/config.py` | `Dataset` and `DATASETS` | "Single source of truth. Re-pointing the pipeline means changing config, not logic." |
| `src/transform.py` | the body of `transform()` | "It reads like a checklist: rename, normalise, melt, parse dates, coerce numbers, drop invalid rows, de-duplicate, add the daily change, **validate**. If validation fails the pipeline stops rather than load bad data." |
| `src/load.py` | `load_to_sqlite()` | "Parameterised inserts in chunks of 5,000. Table names are checked against a regex because they can't be bound parameters, which blocks SQL injection." |
| `src/report.py` | `create_summary_view()` | "The join and the fatality rate are done in SQL, with `NULL` when there are no cases, to avoid dividing by zero." |
| `.github/workflows/ci.yml` + Actions tab | the matrix | "Lint, tests with coverage enforced at 100%, and real smoke runs, on four Python versions." |

---

## 4. Close (20 seconds)

> "So: a tested, idempotent pipeline for two datasets with a combined view
> and a report. Next I'd add PostgreSQL as a target, schedule it with a
> timed GitHub Actions workflow, and add a chart to the report. Questions?"

---

## 5. Likely questions and answers

**Why SQLite and not PostgreSQL?**
It ships with Python, needs no server, and the whole database is one file,
which suits a portfolio project. The SQL I wrote is standard, so moving to
PostgreSQL mostly means changing the connection and the upsert syntax
(`INSERT ... ON CONFLICT DO UPDATE`).

**What does idempotent mean, and how do you prove it?**
Running it once or ten times gives the same result. The primary key is
`(date, country, province)` and rows are written with `INSERT OR REPLACE`.
There are tests (unit and end-to-end) and a CI step that runs the pipeline
twice and compares.

**Why melt the data?**
Wide data has a column per day, so every new day changes the schema and
you can't filter or group by date in SQL. Tidy data has a fixed schema:
one row per observation.

**`new_cases` can be negative. Is that a bug?**
No. The source sometimes revises earlier totals downwards. `confirmed`
(the cumulative count) is validated as never negative. `new_cases` is
the honest day-to-day difference. Query 8d in the SQL notes measures it:
362 of 330,327 rows (0.11%).

**What happens if the source changes its columns?**
`read_raw()` checks for the required columns and raises a clear
`TransformError` naming what's missing, so it fails loudly and nothing loads.

**What if the download fails halfway?**
The file is written to a temporary file and only renamed into place when
complete (an atomic write), so the previous good file is never corrupted.

**Why 100% coverage? Isn't that overkill?**
The code is small enough that it's cheap, and it forced me to test the
error paths: corrupt CSVs, read-only folders, a failure in the middle of an
insert. Those are where bugs hide. CI fails if coverage drops.

**How would it scale to much bigger data?**
Inserts are already chunked. For much bigger files I'd read the CSV in
chunks (`pd.read_csv(chunksize=...)`), move to PostgreSQL, and load
incrementally (only dates newer than `MAX(date)`).

**How would you run it every day?**
A cron job or a scheduled GitHub Actions workflow running
`python -m src.run_pipeline --dataset all --report report.md`. The exit codes
(0, 1, or 130 for Ctrl-C) let the scheduler know whether it worked.

**What was the hardest part?**
Pick a real one, for example: making the audit table honest when a load
fails. The "running" row is committed first, so a later failure can still
be recorded as `failed` even after a rollback.

**What's the data source, and is it still updated?**
The JHU CSSE COVID-19 repository. It stopped updating on 2023-03-10, so the
data ends 2023-03-09, which makes results reproducible.

---

## 6. If something goes wrong live

| Problem | Fix |
|---|---|
| No internet / GitHub slow | `Ctrl-C`, then `./demo.sh --offline` |
| `python: command not found` | `PYTHON=python3 ./demo.sh` |
| `Permission denied: ./demo.sh` | `chmod +x demo.sh` or `bash demo.sh` |
| `ModuleNotFoundError: pandas` | `source venv/bin/activate` then `pip install -r requirements-dev.txt` |
| Windows | Run `demo.sh` from **Git Bash**, or type the commands below by hand |

### The demo without the script

```bash
python -m pytest
python -m src.run_pipeline                          # confirmed cases
python -m src.run_pipeline --skip-extract           # again: same row count
python -m src.run_pipeline --dataset deaths         # deaths + daily_summary view
python -m src.run_pipeline --dataset all --summary --report report.md
python -m src.run_pipeline --source file:///nope.csv   # fails safely, exit 1
```
