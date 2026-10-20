# etl-pipeline: fresh start, one folder per day
verification code: WTC-FHL8VAFY


```



etl-pipeline-fresh/
├── HOW_TO_USE.md            ← this file
├── copy_each_day/
│   ├── day1_tue_20_oct/     ← copy into your project on Tue 20 Oct (20 files)
│   ├── day2_wed_21_oct/     ← copy on Wed 21 Oct (5 files)
│   ├── day3_thu_22_oct/     ← copy on Thu 22 Oct (7 files)
│   └── day4_fri_23_oct/     ← copy on Fri 23 Oct (11 files)
└── full_project/
    └── etl-pipeline/        ← the finished project, for practising the demo
```

Each day folder holds **only the files that are new or changed that day**, already in the right
sub-folders. Copy the *contents* of the folder into the root of your real `etl-pipeline` project
and say yes to replacing files. Every day was tested on its own: ruff is clean, coverage is 100%,
and the CI steps pass on Python 3.10 and 3.13.

| Day | Tests after copying | What you can show that day |
|---|---|---|
| Tue 20 Oct | 28 | download a CSV safely (extract) |
| Wed 21 Oct | 84 | turn the wide CSV into a tidy one (transform) |
| Thu 22 Oct | 172 | the full pipeline from the command line, into SQLite |
| Fri 23 Oct | 200 | combined view, report, demo script, v1.0.0 |

> ⚠️ **Hidden files:** `.github/` and `.gitignore` start with a dot, so your file browser may hide them.
> Use the terminal commands below, or turn on hidden files (Windows Explorer: View → Show → Hidden items;
> Mac Finder: Cmd + Shift + .).

In the commands, replace `PATH/TO/etl-pipeline-fresh` with wherever you unzipped this.
Run everything in **PyCharm's Terminal**, inside your real `etl-pipeline` project.

---

## Day 1: Tuesday 20 October 2026: wipe and start again

### 1. Back up the old code (it stays on GitHub under a tag)
```bash
git pull
git tag backup-before-reset-2026-10-20
git push origin backup-before-reset-2026-10-20
```

### 2. Delete the old project, safely for PyCharm
```bash
git rm -r -q --cached .idea      # untrack PyCharm settings but KEEP them on disk
git rm -r -q .                   # remove every other tracked file
git checkout HEAD -- LICENSE     # keep the licence
```
If old untracked folders are still there (for example `data/`, `__pycache__/`, `.pytest_cache/`,
an old `pipeline.db`), delete them. **Do not delete `.idea/` or `venv/`/`.venv/`.**

### 3. Copy in day 1
macOS / Linux / Git Bash:
```bash
cp -r PATH/TO/etl-pipeline-fresh/copy_each_day/day1_tue_20_oct/. .
```
Windows (PowerShell or cmd):
```powershell
robocopy "PATH\TO\etl-pipeline-fresh\copy_each_day\day1_tue_20_oct" . /E
```

### 4. Install and check
```bash
pip install -r requirements-dev.txt
ruff check src tests             # All checks passed!
python -m pytest --cov=src       # 28 passed, 100%
```
Optional live check (needs internet):
```bash
python -c "from src import config; from src.extract import extract_from_url; print(extract_from_url(config.DATASETS['confirmed'].source_url, 'data/raw/covid19_confirmed_global.csv'))"
```
This should print `... (1,819,904 bytes, sha256=e6234a59eec4...)`.

### 5. Commit and push
```bash
git add -A
git status                       # .idea/, venv/ and data CSVs must NOT be listed as new
git commit -m "day1 (2026-10-20): fresh start — scaffold, config, extract step, tests, CI"
git push origin main
```
On GitHub, open **Actions** and check that 4 green ticks appear (Python 3.10–3.13).

**Files today:** `.github/workflows/ci.yml`, `.gitignore`, `README.md`, `PROGRESS.md`, `pyproject.toml`,
`pytest.ini`, `requirements.txt`, `requirements-dev.txt`, `data/raw/.gitkeep`, `data/processed/.gitkeep`,
`sql_notes/.gitkeep`, `src/__init__.py`, `src/config.py`, `src/extract.py`, `tests/__init__.py`,
`tests/conftest.py`, `tests/fixtures/sample_confirmed.csv`, `tests/fixtures/sample_deaths.csv`,
`tests/test_config.py`, `tests/test_extract.py`

---

## Day 2: Wednesday 21 October 2026: transform

```bash
git pull
cp -r PATH/TO/etl-pipeline-fresh/copy_each_day/day2_wed_21_oct/. .
#   Windows: robocopy "PATH\TO\etl-pipeline-fresh\copy_each_day\day2_wed_21_oct" . /E

ruff check src tests
python -m pytest --cov=src       # 84 passed, 100%

git add -A
git commit -m "day2 (2026-10-21): transform step — melt, clean, validate"
git push origin main
```
Optional live check (after the day-1 download):
`python -c "from src.transform import transform; print(transform(dataset='confirmed'))"` should give **330,327 rows**.

**Files today:** NEW `src/transform.py`, `tests/test_transform.py`. REPLACE `README.md`, `PROGRESS.md`, `.github/workflows/ci.yml`

---

## Day 3: Thursday 22 October 2026: load and CLI

```bash
git pull
cp -r PATH/TO/etl-pipeline-fresh/copy_each_day/day3_thu_22_oct/. .
#   Windows: robocopy "PATH\TO\etl-pipeline-fresh\copy_each_day\day3_thu_22_oct" . /E

ruff check src tests
python -m pytest --cov=src       # 172 passed, 100%

git add -A
git commit -m "day3 (2026-10-22): load step and CLI — idempotent SQLite load, audit table, end-to-end tests"
git push origin main
```
Try it (needs internet):
```bash
python -m src.run_pipeline --dataset all             # 330,327 rows in daily_cases and daily_deaths
python -m src.run_pipeline --dataset all --summary
```
`pipeline.db` is gitignored, so it won't be committed.

**Files today:** NEW `src/load.py`, `src/run_pipeline.py`, `tests/test_load.py`, `tests/test_pipeline.py`. REPLACE `README.md`, `PROGRESS.md`, `.github/workflows/ci.yml`

---

## Day 4: Friday 23 October 2026: report, docs, demo and release (done by lunchtime)

```bash
git pull
cp -r PATH/TO/etl-pipeline-fresh/copy_each_day/day4_fri_23_oct/. .
#   Windows: robocopy "PATH\TO\etl-pipeline-fresh\copy_each_day\day4_fri_23_oct" . /E

ruff check src tests
python -m pytest --cov=src       # 200 passed, 100%
bash demo.sh --offline --no-pause

git add -A
git update-index --chmod=+x demo.sh          # so ./demo.sh works on Linux/Mac
git commit -m "day4 (2026-10-23): report, SQL notes, docs, demo — release v1.0.0"
git push origin main
git tag -a v1.0.0 -m "v1.0.0: COVID-19 ETL pipeline — confirmed + deaths, summary view, report"
git push origin v1.0.0
```

**Files today:** NEW `src/report.py`, `tests/test_report.py`, `sql_notes/analysis_queries.sql`, `demo.sh`, `DEMO.md`,
`test_plan.md`, `CHANGELOG.md`. REPLACE `src/run_pipeline.py`, `README.md`, `PROGRESS.md`, `.github/workflows/ci.yml`

---

## Practise the demo any time (use `full_project/`, not your real repo)

```bash
cd PATH/TO/etl-pipeline-fresh/full_project/etl-pipeline
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
bash demo.sh              # live data, pauses before each step
bash demo.sh --offline    # no internet needed
```
`DEMO.md` has the talk track, what to say at each step, and 10+ likely questions with answers.

## If something goes wrong

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: pandas` / `ruff: command not found` | `pip install -r requirements-dev.txt` in the activated venv |
| Tests fail after copying | Make sure you copied the folder's **contents** into the project root (so `src/` sits next to `README.md`), including `.github/` |
| `.idea` files show up in `git status` | Run `git rm -r --cached .idea`; `.gitignore` already ignores it |
| GitHub Actions red on the demo step | Use the day-4 `ci.yml` as given (it runs `bash demo.sh`) |
| Need the old code back | `git checkout backup-before-reset-2026-10-20 -- <file>` |
