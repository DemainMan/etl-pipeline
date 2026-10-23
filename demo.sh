#!/usr/bin/env bash
# demo.sh — a guided, step-by-step demo of the ETL pipeline.
#
#   ./demo.sh             live data from GitHub (needs internet, ~30 s total)
#   ./demo.sh --offline   the small test fixtures, no internet needed
#   ./demo.sh --no-pause  run straight through without waiting for Enter
#
# Everything the demo creates goes into demo_output/ (gitignored), so it never
# touches your real pipeline.db or data/ folder. Delete demo_output/ to reset.
#
# On Windows, run it from Git Bash. Set PYTHON=python3 if `python` is not on
# your PATH.

set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python}"
OUT="demo_output"
DB="$OUT/pipeline.db"
OFFLINE=0
PAUSE=1

for arg in "$@"; do
  case "$arg" in
    --offline)  OFFLINE=1 ;;
    --no-pause) PAUSE=0 ;;
    -h|--help)  sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

bold=$(tput bold 2>/dev/null || true)
reset=$(tput sgr0 2>/dev/null || true)

step() {
  echo
  echo "${bold}=== $1 ===${reset}"
  [ -n "${2:-}" ] && echo "$2"
  if [ "$PAUSE" -eq 1 ]; then
    read -r -p "Press Enter to run it..." _ </dev/tty || true
  fi
}

run() {
  echo "${bold}\$ $*${reset}"
  "$@"
}

# Small helper: run one SQL query against the demo database and print a table.
sql() {
  "$PY" - "$DB" "$1" <<'PYEOF'
import sqlite3, sys
db, query = sys.argv[1], sys.argv[2]
with sqlite3.connect(db) as conn:
    cursor = conn.execute(query)
    headers = [d[0] for d in cursor.description]
    rows = [["" if v is None else str(v) for v in row] for row in cursor.fetchall()]
widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
          for i, h in enumerate(headers)]
print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
print("  ".join("-" * w for w in widths))
for row in rows:
    print("  ".join(v.ljust(w) for v, w in zip(row, widths)))
PYEOF
}

rm -rf "$OUT"
mkdir -p "$OUT"

if [ "$OFFLINE" -eq 1 ]; then
  CONFIRMED_SRC="file://$PWD/tests/fixtures/sample_confirmed.csv"
  DEATHS_SRC="file://$PWD/tests/fixtures/sample_deaths.csv"
  MODE="OFFLINE (test fixtures)"
else
  CONFIRMED_SRC=""
  DEATHS_SRC=""
  MODE="LIVE (Johns Hopkins data from GitHub)"
fi

echo "${bold}COVID-19 ETL pipeline — demo — mode: $MODE${reset}"
"$PY" -m src.run_pipeline --version

# 1 ---------------------------------------------------------------------------
step "1. The tests" \
  "Every step is tested offline against tiny fixture CSVs that contain every data problem."
run "$PY" -m pytest

# 2 ---------------------------------------------------------------------------
step "2. Extract -> Transform -> Load: confirmed cases" \
  "Download the wide CSV, melt it to one row per place per day, clean it, load it into SQLite."
SRC=()
[ -n "$CONFIRMED_SRC" ] && SRC=(--source "$CONFIRMED_SRC")
run "$PY" -m src.run_pipeline --dataset confirmed ${SRC[@]+"${SRC[@]}"} \
  --raw-path "$OUT/raw/confirmed.csv" \
  --processed-path "$OUT/processed/confirmed.csv" \
  --db "$DB"

# 3 ---------------------------------------------------------------------------
step "3. Wide -> tidy" "Raw file: one column per day. Clean file: one row per place per day."
echo "${bold}raw (first 3 lines, first 8 columns):${reset}"
head -n 3 "$OUT/raw/confirmed.csv" | cut -d, -f1-8
echo
echo "${bold}clean (first 5 lines):${reset}"
head -n 5 "$OUT/processed/confirmed.csv"

# 4 ---------------------------------------------------------------------------
step "4. Idempotency: run it again" \
  "INSERT OR REPLACE on the (date, country, province) primary key — the row count must not change."
sql "SELECT COUNT(*) AS rows_before FROM daily_cases"
run "$PY" -m src.run_pipeline --dataset confirmed --skip-extract --quiet \
  --raw-path "$OUT/raw/confirmed.csv" \
  --processed-path "$OUT/processed/confirmed.csv" \
  --db "$DB"
sql "SELECT COUNT(*) AS rows_after FROM daily_cases"
echo
echo "${bold}Audit trail (pipeline_runs):${reset}"
sql "SELECT run_id, substr(started_at,1,19) AS started_utc, source_table, rows_loaded, status FROM pipeline_runs"

# 5 ---------------------------------------------------------------------------
step "5. Second dataset: deaths" \
  "Same pipeline, different Dataset from config.py. Loading it also creates the daily_summary view."
SRC=()
[ -n "$DEATHS_SRC" ] && SRC=(--source "$DEATHS_SRC")
run "$PY" -m src.run_pipeline --dataset deaths ${SRC[@]+"${SRC[@]}"} \
  --raw-path "$OUT/raw/deaths.csv" \
  --processed-path "$OUT/processed/deaths.csv" \
  --db "$DB"

# 6 ---------------------------------------------------------------------------
step "6. Combined analysis with SQL" "Top 5 countries on the latest date, from the daily_summary view."
sql "SELECT country, SUM(confirmed) AS confirmed, SUM(deaths) AS deaths,
            ROUND(100.0 * SUM(deaths) / SUM(confirmed), 2) AS fatality_pct
     FROM daily_summary
     WHERE date = (SELECT MAX(date) FROM daily_summary)
     GROUP BY country ORDER BY SUM(confirmed) DESC LIMIT 5"
if [ "$OFFLINE" -eq 0 ]; then
  echo
  echo "${bold}South Africa at the end of each year:${reset}"
  sql "SELECT date, confirmed, deaths, case_fatality_pct FROM daily_summary
       WHERE country = 'South Africa'
         AND date IN ('2020-12-31','2021-12-31','2022-12-31','2023-03-09')"
fi

# 7 ---------------------------------------------------------------------------
step "7. The report" "A Markdown report of what is loaded, totals, top 10, quality checks and runs."
run "$PY" -m src.run_pipeline --dataset all --db "$DB" --summary --report "$OUT/report.md"
echo
cat "$OUT/report.md"

# 8 ---------------------------------------------------------------------------
step "8. Failing safely" "A bad source is reported clearly, with exit code 1 and no traceback."
set +e
"$PY" -m src.run_pipeline --source "file://$PWD/does_not_exist.csv" \
  --raw-path "$OUT/raw/bad.csv" --processed-path "$OUT/processed/bad.csv" --db "$DB"
code=$?
set -e
echo "exit code: $code"

echo
echo "${bold}Demo finished. Everything it created is in $OUT/ (safe to delete).${reset}"
