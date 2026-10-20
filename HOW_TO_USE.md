# etl-pipeline: day folders tracked in the repo

Each day adds **one complete folder** to the repo (`day1_tue_20_oct/`, `day2_wed_21_oct/`, …).
Each folder is a standalone snapshot of the project at the end of that day.
The repo root holds `README.md` (verification code on line 2), `.gitignore`, `LICENSE` and **one** CI
workflow that tests every day folder on Python 3.10–3.13.

```
etl-pipeline/                 (your repo after Friday)
├── .github/workflows/ci.yml  ← root CI: checks every dayN_* folder
├── .gitignore                ← ignores .idea/, venv/, caches, databases
├── LICENSE
├── README.md                 ← line 2: verification code: WTC-FHL8VAFY
├── day1_tue_20_oct/          28 tests
├── day2_wed_21_oct/          84 tests
├── day3_thu_22_oct/          172 tests
└── day4_fri_23_oct/          200 tests, v1.0.0
```

In every step, copy the **contents** of `copy/dayN/` into the repo root (say yes to replacing `README.md`).
Run commands in PyCharm's Terminal from the repo root. Replace `PATH/TO` with where you unzipped this.

---

## Day 1: Tue 20 Oct (today): finish what you pushed

`day1_tue_20_oct/` is already on GitHub. Today you add the root files and remove the folder's own
`.github` (GitHub only runs workflows from the root):

```bash
git pull
cp -r PATH/TO/etl-pipeline-day-folders/copy/day1/. .
#   Windows: robocopy "PATH\TO\etl-pipeline-day-folders\copy\day1" . /E
git rm -r -q day1_tue_20_oct/.github

cd day1_tue_20_oct
ruff check src tests
python -m pytest --cov=src          # 28 passed, 100%
cd ..

git add -A
git status          # expect: A .github/workflows/ci.yml, A .gitignore, A README.md, D day1_tue_20_oct/.github/...
git commit -m "day1 (2026-10-20): add root README, .gitignore and CI for the day folders"
git push origin main

git tag backup-before-reset-2026-10-20 5286cec
git push origin backup-before-reset-2026-10-20
```

## Day 2: Wed 21 Oct

```bash
git pull
cp -r PATH/TO/etl-pipeline-day-folders/copy/day2/. .
#   Windows: robocopy "PATH\TO\etl-pipeline-day-folders\copy\day2" . /E
cd day2_wed_21_oct && ruff check src tests && python -m pytest --cov=src && cd ..     # 84 passed
git add -A
git commit -m "day2 (2026-10-21): transform step — melt, clean, validate"
git push origin main
```

## Day 3: Thu 22 Oct

```bash
git pull
cp -r PATH/TO/etl-pipeline-day-folders/copy/day3/. .
cd day3_thu_22_oct && ruff check src tests && python -m pytest --cov=src && cd ..     # 172 passed
git add -A
git commit -m "day3 (2026-10-22): load step and CLI — idempotent SQLite load, audit table, end-to-end tests"
git push origin main
```

## Day 4: Fri 23 Oct

```bash
git pull
cp -r PATH/TO/etl-pipeline-day-folders/copy/day4/. .
cd day4_fri_23_oct && ruff check src tests && python -m pytest --cov=src && bash demo.sh --offline --no-pause && cd ..   # 200 passed
git add -A
git update-index --chmod=+x day4_fri_23_oct/demo.sh
git commit -m "day4 (2026-10-23): report, SQL notes, docs, demo — release v1.0.0"
git push origin main
git tag -a v1.0.0 -m "v1.0.0: COVID-19 ETL pipeline" && git push origin v1.0.0
```

## Good to know
- **Always run Python commands inside a day folder.** Running `pytest` from the repo root would mix
  the four folders and fail.
- **PyCharm:** right-click the newest day folder → *Mark Directory as* → *Sources Root*, so imports
  like `from src import config` resolve in the editor.
- After each push, open **Actions** on GitHub: 4 green ticks (3.10–3.13), and each run checks every day folder.
- Never delete `.idea/` or `venv/`; the root `.gitignore` keeps them out of git.
